"""Unit tests for AxleManager state management and coordination."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.can.constants import (
    VcuGearStatus,
    VcuMcuEnCmd,
    VcuWorkModeReq,
)
from app.core.can.driver import CanRawFrame, ZlgCanDriver
from app.schemas.axle import (
    AxleSafetyConfig,
    CanConnectRequest,
    VcuCommandUpdateRequest,
)
from app.services.axle_manager import AxleManager


def create_mock_driver() -> MagicMock:
    """创建模拟的 ZlgCanDriver 实例。"""
    driver = MagicMock(spec=ZlgCanDriver)
    driver.open_device = AsyncMock()
    driver.open_channel = AsyncMock()
    driver.transmit = AsyncMock(return_value=True)
    driver.receive = AsyncMock(return_value=[])
    driver.close_channel = AsyncMock()
    driver.close_device = AsyncMock()
    driver.is_device_open = True
    driver.is_channel_open.return_value = True
    return driver


def test_axle_manager_initial_state() -> None:
    """测试管理器初始状态。"""
    driver = create_mock_driver()
    manager = AxleManager(driver=driver)
    assert not manager.is_connected
    assert not manager.is_transmitting

    telemetry = manager.get_telemetry()
    assert not telemetry.connected
    assert telemetry.command.mcu_en_cmd == 0
    assert telemetry.command.gear_sts == VcuGearStatus.N
    assert telemetry.mcu_1_last_rx_timestamp is None
    assert telemetry.mcu_2_last_rx_timestamp is None
    assert telemetry.mcu_tbox_last_rx_timestamp is None
    assert telemetry.safety.config.enabled is True
    assert telemetry.safety.config.max_motor_speed_rpm == 3000
    assert telemetry.safety.config.max_motor_torque_nm == 10.0
    assert telemetry.safety.config.max_motor_temp_c == 150.0


def test_axle_manager_update_command() -> None:
    """测试更新控制命令。"""

    async def run_test() -> None:
        driver = create_mock_driver()
        manager = AxleManager(driver=driver)
        update = VcuCommandUpdateRequest(
            torque_req=250.0,
            speed_req=3000,
            work_mode_req=VcuWorkModeReq.TORQUE,
            mcu_en_cmd=VcuMcuEnCmd.ENABLE,
            gear_sts=VcuGearStatus.D,
        )
        cmd = await manager.update_command(update)
        assert cmd.torque_req == 250.0
        assert cmd.speed_req == 3000
        assert cmd.work_mode_req == VcuWorkModeReq.TORQUE
        assert cmd.mcu_en_cmd == VcuMcuEnCmd.ENABLE
        assert cmd.gear_sts == VcuGearStatus.D

    asyncio.run(run_test())


def test_axle_manager_emergency_stop() -> None:
    """测试紧急停机安全联锁逻辑。"""

    async def run_test() -> None:
        driver = create_mock_driver()
        manager = AxleManager(driver=driver)
        # 先设置运行状态
        await manager.update_command(
            VcuCommandUpdateRequest(
                torque_req=500.0,
                speed_req=4000,
                mcu_en_cmd=VcuMcuEnCmd.ENABLE,
                gear_sts=VcuGearStatus.D,
            )
        )

        # 触发急停
        cmd = await manager.emergency_stop()
        assert cmd.mcu_en_cmd == VcuMcuEnCmd.DISABLE
        assert cmd.torque_req == 0.0
        assert cmd.speed_req == 0
        assert cmd.gear_sts == VcuGearStatus.N

    asyncio.run(run_test())


def test_axle_manager_connect_and_disconnect() -> None:
    """测试连接和断开生命周期。"""

    async def run_test() -> None:
        driver = create_mock_driver()
        manager = AxleManager(driver=driver)
        config = CanConnectRequest(
            device_type=4,
            device_index=0,
            channel=0,
            baud_rate=250000,
        )

        await manager.connect(config)
        assert manager.is_connected
        assert manager.is_transmitting
        driver.open_device.assert_awaited_once_with(device_type=4, device_index=0)
        driver.open_channel.assert_awaited_once_with(channel=0, baud_rate=250000)

        # 稍微休眠以便验证任务运行
        await asyncio.sleep(0.02)

        await manager.disconnect()
        assert not manager.is_connected
        assert not manager.is_transmitting
        driver.close_channel.assert_awaited_once_with(0)
        driver.close_device.assert_awaited_once()

    asyncio.run(run_test())


def test_axle_manager_sse_subscription() -> None:
    """测试 SSE 队列订阅与数据分发。"""

    async def run_test() -> None:
        driver = create_mock_driver()
        manager = AxleManager(driver=driver)
        queue = manager.subscribe()

        assert queue in manager._subscribers
        manager._broadcast_telemetry()

        # 验证收到遥测快照
        telemetry = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert telemetry.command.gear_sts == VcuGearStatus.N

        manager.unsubscribe(queue)
        assert queue not in manager._subscribers

    asyncio.run(run_test())


def test_axle_manager_connect_rollback_on_failure() -> None:
    """测试当通道初始化失败时，必须自动回滚并关闭已打开的设备句柄。"""

    async def run_test() -> None:
        driver = create_mock_driver()
        driver.open_channel.side_effect = RuntimeError("硬件通道占用或故障")
        manager = AxleManager(driver=driver)

        config = CanConnectRequest(
            device_type=4,
            device_index=0,
            channel=0,
            baud_rate=250000,
        )

        with pytest.raises(RuntimeError, match="硬件通道占用或故障"):
            await manager.connect(config)

        # 验证设备打开后遭遇通道异常时，触发了 close_device 回滚清理
        driver.open_device.assert_awaited_once_with(device_type=4, device_index=0)
        driver.close_device.assert_awaited_once()
        assert not manager.is_connected
        assert not manager.is_transmitting

    asyncio.run(run_test())


def test_axle_manager_rx_loop_corrupted_frame_resilience() -> None:
    """测试接收到坏帧或解码异常时，接收循环具备容错性且不崩溃终止。"""

    async def run_test() -> None:
        from app.core.can.driver import CanRawFrame

        driver = create_mock_driver()
        # 模拟先收到一帧长度不足8字节的帧，再收到有效 0x35A 报文
        corrupted_frame = CanRawFrame(
            can_id=0x35A,
            data=bytes([0x01, 0x02]),  # 不足 8 字节
            is_extended=False,
            is_remote=False,
            timestamp=1000,
        )
        valid_frame = CanRawFrame(
            can_id=0x35A,
            data=bytes([0x15, 0x1D, 0x2B, 0xF6, 0x00, 0x00, 0x00, 0x00]),
            is_extended=False,
            is_remote=False,
            timestamp=2000,
        )
        driver.receive.side_effect = [
            [corrupted_frame],
            [valid_frame],
            [],
        ]

        manager = AxleManager(driver=driver)
        config = CanConnectRequest(device_type=4, channel=0, baud_rate=250000)
        await manager.connect(config)

        # 等待接收循环执行一轮
        await asyncio.sleep(0.03)

        telemetry = manager.get_telemetry()
        # 验证有效帧正常解码 (540.5 V)
        assert telemetry.mcu_1.mcu_dc_main_wire_volt == 540.5
        assert telemetry.mcu_1_last_rx_timestamp is not None
        assert manager.is_transmitting

        await manager.disconnect()

    asyncio.run(run_test())


def test_axle_manager_tracks_mcu_2_feedback_freshness() -> None:
    """0x35B 成功解码后应标记反馈时间，断开后必须失效。"""

    async def run_test() -> None:
        from app.core.can.driver import CanRawFrame

        driver = create_mock_driver()
        mcu_2_frame = CanRawFrame(
            can_id=0x35B,
            data=bytes([0x86, 0xC4, 0x3B, 0x60, 0x7C, 0x3D, 0x65, 0x1C]),
            is_extended=False,
            is_remote=False,
            timestamp=1000,
        )
        has_returned_frame = False

        async def receive_once(**_: object) -> list[CanRawFrame]:
            nonlocal has_returned_frame
            if has_returned_frame:
                return []
            has_returned_frame = True
            return [mcu_2_frame]

        driver.receive.side_effect = receive_once
        manager = AxleManager(driver=driver)
        config = CanConnectRequest(device_type=4, channel=0, baud_rate=250000)

        await manager.connect(config)
        await asyncio.sleep(0.03)

        telemetry = manager.get_telemetry()
        assert telemetry.mcu_2.mcu_en_sts == 1
        assert telemetry.mcu_2.mcu_lv_sts == 1
        assert telemetry.mcu_2_last_rx_timestamp is not None

        await manager.disconnect()
        assert manager.get_telemetry().mcu_2_last_rx_timestamp is None

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("frame", "config", "expected_metric", "expected_value"),
    [
        (
            CanRawFrame(
                can_id=0x35B,
                # 3200 RPM / 0 Nm，验证实际转速越限。
                data=bytes([0x75, 0x30, 0x3B, 0x60, 0x75, 0x30, 0x00, 0x00]),
                is_extended=False,
                is_remote=False,
                timestamp=1000,
            ),
            AxleSafetyConfig(
                enabled=True,
                max_motor_speed_rpm=3000,
                max_motor_torque_nm=3000.0,
                max_motor_temp_c=210.0,
            ),
            "motor_speed",
            3200.0,
        ),
        (
            CanRawFrame(
                can_id=0x35B,
                # 0 RPM / -150 Nm，验证回馈方向转矩同样按绝对值保护。
                data=bytes([0x75, 0x30, 0x2E, 0xE0, 0x6F, 0x54, 0x00, 0x00]),
                is_extended=False,
                is_remote=False,
                timestamp=1000,
            ),
            AxleSafetyConfig(
                enabled=True,
                max_motor_speed_rpm=12000,
                max_motor_torque_nm=100.0,
                max_motor_temp_c=210.0,
            ),
            "motor_torque",
            150.0,
        ),
        (
            CanRawFrame(
                can_id=0x35C,
                # 电机温度 100 ℃ (原始值 140，偏移 -40)。
                data=bytes([0x01, 0x01, 0x03, 0x00, 0x00, 0x8C, 0x41, 0x00]),
                is_extended=False,
                is_remote=False,
                timestamp=1000,
            ),
            AxleSafetyConfig(
                enabled=True,
                max_motor_speed_rpm=12000,
                max_motor_torque_nm=3000.0,
                max_motor_temp_c=80.0,
            ),
            "motor_temperature",
            100.0,
        ),
    ],
)
def test_axle_manager_auto_stops_on_fresh_safety_violation(
    frame: CanRawFrame,
    config: AxleSafetyConfig,
    expected_metric: str,
    expected_value: float,
) -> None:
    """速度、转矩或电机温度越限时，必须走既有急停互锁路径。"""

    async def run_test() -> None:
        driver = create_mock_driver()
        has_returned_frame = False

        async def receive_once(**_: object) -> list[CanRawFrame]:
            nonlocal has_returned_frame
            if has_returned_frame:
                return []
            has_returned_frame = True
            return [frame]

        driver.receive.side_effect = receive_once
        manager = AxleManager(driver=driver)
        await manager.update_safety_config(config)
        await manager.connect(CanConnectRequest(device_type=4, channel=0, baud_rate=250000))

        try:
            await asyncio.sleep(0.05)
            telemetry = manager.get_telemetry()

            assert manager.is_emergency_locked
            assert telemetry.command.mcu_en_cmd == VcuMcuEnCmd.DISABLE
            assert telemetry.command.torque_req == 0.0
            assert telemetry.command.speed_req == 0
            assert telemetry.command.gear_sts == VcuGearStatus.N
            assert telemetry.safety.last_trip is not None
            assert telemetry.safety.last_trip.metric == expected_metric
            assert telemetry.safety.last_trip.actual_value == expected_value
        finally:
            await manager.disconnect()

    asyncio.run(run_test())


def test_axle_manager_safety_does_not_use_default_or_stale_values() -> None:
    """未收到新鲜反馈时，不能因遥测默认值或历史值触发急停。"""

    async def run_test() -> None:
        driver = create_mock_driver()
        manager = AxleManager(driver=driver)
        await manager.update_safety_config(
            AxleSafetyConfig(
                enabled=True,
                max_motor_speed_rpm=1,
                max_motor_torque_nm=0.1,
                max_motor_temp_c=1.0,
            )
        )
        await manager.connect(CanConnectRequest(device_type=4, channel=0, baud_rate=250000))

        try:
            await asyncio.sleep(0.03)
            telemetry = manager.get_telemetry()
            assert not manager.is_emergency_locked
            assert telemetry.safety.last_trip is None
        finally:
            await manager.disconnect()

    asyncio.run(run_test())


def test_axle_manager_shutdown() -> None:
    """测试 manager.shutdown() 能够关闭连接并清理底层线程池。"""

    async def run_test() -> None:
        driver = create_mock_driver()
        driver.shutdown_executor = MagicMock()
        manager = AxleManager(driver=driver)

        config = CanConnectRequest(device_type=4, channel=0, baud_rate=250000)
        await manager.connect(config)

        await manager.shutdown()
        assert not manager.is_connected
        driver.close_device.assert_awaited()
        driver.shutdown_executor.assert_called_once()

    asyncio.run(run_test())
