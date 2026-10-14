"""平稳停机：目标归零 → 等待减速 → 自动关闭使能并切 N 挡。"""

import asyncio

import pytest

from app.core.can.driver import CanDriverError, CanRawFrame
from app.schemas.axle import (
    AxleSafetyConfig,
    CanConnectRequest,
    CycleTestStartRequest,
    CycleTestStep,
    VcuCommandUpdateRequest,
)
from app.services import axle_manager as axle_manager_module
from app.services.axle_manager import AxleManager
from tests.test_axle_manager import create_mock_driver


def mcu_2_frame(speed_rpm: int) -> CanRawFrame:
    """构造指定实际转速、已使能的 0x35B 帧（转矩 0）。"""
    raw_speed = speed_rpm + 12000
    return CanRawFrame(
        can_id=0x35B,
        data=bytes([0x75, 0x30, raw_speed >> 8, raw_speed & 0xFF, 0x75, 0x30, 0x4C, 0x00]),
        is_extended=False,
        is_remote=False,
        timestamp=0,
    )


async def connect_enabled_manager(feedback: dict[str, int]) -> AxleManager:
    """连接并使能；MCU 反馈的实际转速取自 feedback["speed"]。"""
    driver = create_mock_driver()
    driver.receive.side_effect = lambda **_: [mcu_2_frame(feedback["speed"])]
    manager = AxleManager(driver=driver)
    # 关闭越限判定，避免测试转速触发自动急停；反馈看门狗由持续 0x35B 满足。
    await manager.update_safety_config(AxleSafetyConfig(max_motor_speed_rpm=12000))
    await manager.connect(CanConnectRequest())
    await manager.update_command(
        VcuCommandUpdateRequest(mcu_en_cmd=1, work_mode_req=3, speed_req=1000, gear_sts=1)
    )
    return manager


def test_soft_stop_zeroes_target_then_disables_after_speed_drops() -> None:
    async def run_test() -> None:
        feedback = {"speed": 1000}
        manager = await connect_enabled_manager(feedback)
        try:
            command = await manager.soft_stop()
            assert command.speed_req == 0
            assert command.torque_req == 0
            assert command.mcu_en_cmd == 1  # 减速期间保持使能，由控制器主动制动
            assert manager.get_telemetry().soft_stopping

            await asyncio.sleep(0.15)
            assert manager.get_telemetry().command.mcu_en_cmd == 1

            feedback["speed"] = 10  # 降到阈值内
            await asyncio.sleep(0.2)
            telemetry = manager.get_telemetry()
            assert not telemetry.soft_stopping
            assert telemetry.command.mcu_en_cmd == 0
            assert telemetry.command.gear_sts == 3
            assert not manager.is_emergency_locked  # 不进入急停互锁
        finally:
            await manager.disconnect()

    asyncio.run(run_test())


def test_soft_stop_forces_disable_after_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(axle_manager_module, "SOFT_STOP_TIMEOUT_SECONDS", 0.2)

    async def run_test() -> None:
        manager = await connect_enabled_manager({"speed": 1000})
        try:
            await manager.soft_stop()
            await asyncio.sleep(0.4)
            telemetry = manager.get_telemetry()
            assert not telemetry.soft_stopping
            assert telemetry.command.mcu_en_cmd == 0
        finally:
            await manager.disconnect()

    asyncio.run(run_test())


def test_new_command_overrides_soft_stop() -> None:
    async def run_test() -> None:
        feedback = {"speed": 1000}
        manager = await connect_enabled_manager(feedback)
        try:
            await manager.soft_stop()
            await manager.update_command(VcuCommandUpdateRequest(speed_req=500))
            assert not manager.get_telemetry().soft_stopping

            feedback["speed"] = 0
            await asyncio.sleep(0.2)
            command = manager.get_telemetry().command
            assert command.mcu_en_cmd == 1  # 停机已被新指令取消，不会再自动关闭使能
            assert command.speed_req == 500
        finally:
            await manager.disconnect()

    asyncio.run(run_test())


def test_soft_stop_when_disabled_switches_to_neutral_immediately() -> None:
    async def run_test() -> None:
        manager = AxleManager(driver=create_mock_driver())
        await manager.connect(CanConnectRequest())
        try:
            await manager.update_command(VcuCommandUpdateRequest(gear_sts=1, speed_req=300))
            command = await manager.soft_stop()
            assert command.gear_sts == 3
            assert command.speed_req == 0
            assert not manager.get_telemetry().soft_stopping
        finally:
            await manager.disconnect()

    asyncio.run(run_test())


def test_soft_stop_rejected_while_disconnected_or_cycle_running() -> None:
    async def run_test() -> None:
        manager = AxleManager(driver=create_mock_driver())
        with pytest.raises(CanDriverError, match="未连接"):
            await manager.soft_stop()

        manager = await connect_enabled_manager({"speed": 1000})
        try:
            await manager.update_command(VcuCommandUpdateRequest(mcu_en_cmd=0))
            await manager.start_cycle_test(
                CycleTestStartRequest(
                    steps=[
                        CycleTestStep(
                            id="s", name="正转", gear=1, target_speed=500, duration_seconds=10
                        )
                    ]
                )
            )
            with pytest.raises(CanDriverError, match="终止并归零"):
                await manager.soft_stop()
        finally:
            await manager.disconnect()

    asyncio.run(run_test())
