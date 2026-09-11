"""Unit tests for AxleManager state management and coordination."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.can.constants import (
    VcuGearStatus,
    VcuMcuEnCmd,
    VcuWorkModeReq,
)
from app.core.can.driver import ZlgCanDriver
from app.schemas.axle import CanConnectRequest, VcuCommandUpdateRequest
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
        assert manager.is_transmitting

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
