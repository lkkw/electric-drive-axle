"""PLC 自动上电 / 下电、Safe 联锁、心跳与电驱桥联动（使用仿真 PLC）。"""

import asyncio
import struct
from pathlib import Path

import pytest

from app.core.plc.client import SimulatedStationClient
from app.schemas.axle import CanConnectRequest, VcuCommandUpdateRequest
from app.schemas.plc import PlcConfig
from app.services.axle_manager import AxleManager
from app.services.plc_manager import PlcOperationError, PlcPowerManager
from tests.test_axle_manager import create_mock_driver

SIM_CONFIG = PlcConfig(simulation=True)


class FakeAxle:
    """记录 PLC 管理器对电驱桥的回调顺序。"""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.block_reason: str | None = None
        self.mes = (0.0, 0.0)

    async def on_safety_trip(self, reason: str) -> None:
        self.calls.append(f"trip:{reason}")

    async def before_power_off(self) -> None:
        self.calls.append("disable")

    def power_on_blocker(self) -> str | None:
        return self.block_reason

    def mes_telemetry(self) -> tuple[float, float]:
        return self.mes


def make_manager(
    sim: SimulatedStationClient | None = None,
    *,
    config_path: Path | None = None,
    power_on_timeout_s: float = 0.6,
) -> tuple[PlcPowerManager, SimulatedStationClient, FakeAxle]:
    sim = sim or SimulatedStationClient(power_on_delay_s=0.05, power_off_delay_s=0.05)
    manager = PlcPowerManager(
        config_path=config_path,
        client_factory=lambda _config: sim,
        power_on_timeout_s=power_on_timeout_s,
        power_off_timeout_s=0.4,
        poll_interval_s=0.02,
    )
    axle = FakeAxle()
    manager.bind_axle(
        on_safety_trip=axle.on_safety_trip,
        before_power_off=axle.before_power_off,
        power_on_blocker=axle.power_on_blocker,
        mes_telemetry=axle.mes_telemetry,
    )
    return manager, sim, axle


def request_power_bit(sim: SimulatedStationClient) -> bool:
    return bool(sim.read_station()[0] & 0b10)


def test_power_on_and_off_cycle() -> None:
    async def run_test() -> None:
        manager, sim, axle = make_manager()
        await manager.connect(SIM_CONFIG)
        try:
            result = await manager.power_on()
            assert result.status == "success"
            assert "340 V" in result.message
            assert result.plc.power_state == "powered"  # 返回的快照即最终状态
            status = manager.status()
            assert status.power_state == "powered"
            assert status.contactor_closed and status.power_on
            assert status.product_type_feedback == 1
            assert status.output_voltage == 340

            result = await manager.power_off()
            assert result.status == "success"
            assert result.plc.power_state == "idle"
            assert axle.calls == ["disable"]  # 下电前先关闭电机使能
            assert not request_power_bit(sim)
            status = manager.status()
            assert status.power_state == "idle"
            assert not status.contactor_closed
        finally:
            await manager.shutdown()

    asyncio.run(run_test())


def test_power_on_rejected_when_safe_open() -> None:
    async def run_test() -> None:
        manager, sim, _ = make_manager()
        await manager.connect(SIM_CONFIG)
        try:
            sim.safe = False
            with pytest.raises(PlcOperationError, match="Safe=0") as exc:
                await manager.power_on()
            assert exc.value.status_code == 409
            assert not request_power_bit(sim)
        finally:
            await manager.shutdown()

    asyncio.run(run_test())


def test_power_on_rejected_by_axle_state() -> None:
    async def run_test() -> None:
        manager, sim, axle = make_manager()
        await manager.connect(SIM_CONFIG)
        try:
            axle.block_reason = "电机仍处于使能状态，请先停机并关闭使能"
            with pytest.raises(PlcOperationError, match="使能状态"):
                await manager.power_on()
            assert not request_power_bit(sim)
        finally:
            await manager.shutdown()

    asyncio.run(run_test())


def test_power_on_requires_connection() -> None:
    async def run_test() -> None:
        manager, _, _ = make_manager()
        with pytest.raises(PlcOperationError, match="未连接"):
            await manager.power_on()

    asyncio.run(run_test())


def test_power_on_timeout_resets_request() -> None:
    async def run_test() -> None:
        manager, sim, _ = make_manager(power_on_timeout_s=0.2)
        await manager.connect(SIM_CONFIG)
        try:
            sim.responsive = False  # PLC 不响应上电
            with pytest.raises(PlcOperationError, match="上电超时") as exc:
                await manager.power_on()
            assert exc.value.status_code == 504
            assert not request_power_bit(sim)  # 后端自己复位了上电请求
        finally:
            await manager.shutdown()

    asyncio.run(run_test())


def test_power_off_aborts_power_on_in_progress() -> None:
    async def run_test() -> None:
        sim = SimulatedStationClient(power_on_delay_s=5.0, power_off_delay_s=0.05)
        manager, _, _ = make_manager(sim, power_on_timeout_s=5.0)
        await manager.connect(SIM_CONFIG)
        try:
            on_task = asyncio.create_task(manager.power_on())
            await asyncio.sleep(0.1)
            off_result = await manager.power_off()
            assert off_result.status == "success"
            with pytest.raises(PlcOperationError, match="上电已中止"):
                await on_task
            assert not request_power_bit(sim)
        finally:
            await manager.shutdown()

    asyncio.run(run_test())


def test_safe_open_while_powered_resets_request_and_trips_once() -> None:
    async def run_test() -> None:
        manager, sim, axle = make_manager()
        await manager.connect(SIM_CONFIG)
        try:
            await manager.power_on()
            sim.safe = False
            await asyncio.sleep(0.15)
            trips = [c for c in axle.calls if c.startswith("trip:")]
            assert len(trips) == 1  # 去重：持续断开只停机一次
            assert "Safe=0" in trips[0]
            assert not request_power_bit(sim)
            assert manager.status().power_state in {"fault", "idle"}

            # 恢复后再次上电、再次断开，必须再次停机
            sim.safe = True
            await asyncio.sleep(0.05)
            await manager.power_on()
            sim.safe = False
            await asyncio.sleep(0.15)
            assert len([c for c in axle.calls if c.startswith("trip:")]) == 2
        finally:
            await manager.shutdown()

    asyncio.run(run_test())


def test_emergency_cut_resets_request_power() -> None:
    async def run_test() -> None:
        manager, sim, _ = make_manager()
        await manager.connect(SIM_CONFIG)
        try:
            await manager.power_on()
            await manager.cut_power_for_emergency("操作员手动急停")
            assert not request_power_bit(sim)
            assert "急停联动" in (manager.status().last_message or "")
        finally:
            await manager.shutdown()

    asyncio.run(run_test())


def test_disconnect_refused_while_powered_and_shutdown_cuts_power() -> None:
    async def run_test() -> None:
        manager, sim, _ = make_manager()
        await manager.connect(SIM_CONFIG)
        await manager.power_on()
        with pytest.raises(PlcOperationError, match="请先下电"):
            await manager.disconnect()

        await manager.shutdown()
        sim.connect()  # 重新打开仿真内存查看最终状态
        assert not request_power_bit(sim)
        assert not manager.status().connected

    asyncio.run(run_test())


def test_heartbeat_toggles_and_detects_plc_heart() -> None:
    async def run_test() -> None:
        clock = {"now": 0.0}
        sim = SimulatedStationClient(clock=lambda: clock["now"])
        manager, _, _ = make_manager(sim)
        await manager.connect(SIM_CONFIG)
        try:
            seen_pc_heart = set()
            for step in range(6):
                clock["now"] = step * 1.0  # PLC 心跳每秒翻转
                await manager._monitor_step()
                seen_pc_heart.add(bool(sim.read_station()[0] & 0b1))
                await asyncio.sleep(1.05 if step == 0 else 0)
            assert manager.status().plc_heartbeat_alive
            assert True in seen_pc_heart
        finally:
            await manager.shutdown()

    asyncio.run(run_test())


def test_speed_and_temp_uploaded_for_mes() -> None:
    """实际转速、电机温度写入 Speed / Temp；值不变不重复写，上电不覆盖。"""

    def mes_writes(manager: PlcPowerManager) -> int:
        entries = manager.traffic.entries()["entries"]
        return sum(1 for e in entries if e["source"] == "MES 上传")

    async def run_test() -> None:
        manager, sim, axle = make_manager()
        await manager.connect(SIM_CONFIG)
        try:
            axle.mes = (-1500.0, 65.5)
            await manager._monitor_step()
            block = sim.read_station()
            assert struct.unpack_from(">ff", block, 14) == (-1500.0, 65.5)
            assert mes_writes(manager) >= 2  # Speed、Temp 各记一条（后台监视也可能写）

            written = mes_writes(manager)
            await manager._monitor_step()
            assert mes_writes(manager) == written  # 值未变化，不再写

            await manager.power_on()
            assert struct.unpack_from(">ff", sim.read_station(), 14) == (-1500.0, 65.5)

            axle.mes = (0.0, 0.0)  # CAN 断开 / 反馈过期
            await manager._monitor_step()
            assert struct.unpack_from(">ff", sim.read_station(), 14) == (0.0, 0.0)
        finally:
            await manager.shutdown()

    asyncio.run(run_test())

def test_config_is_persisted(tmp_path: Path) -> None:
    config_path = tmp_path / "plc_config.json"

    async def run_test() -> None:
        manager, _, _ = make_manager(config_path=config_path)
        await manager.connect(PlcConfig(ip="192.168.0.10", rack=0, slot=2, simulation=True))
        await manager.shutdown()

    asyncio.run(run_test())
    restored = PlcPowerManager(config_path=config_path).config
    assert restored.ip == "192.168.0.10"
    assert restored.slot == 2
    assert restored.simulation is False  # 本地仿真不随配置记忆，重启后默认关闭


def test_invalid_ip_rejected() -> None:
    with pytest.raises(ValueError, match="IPv4"):
        PlcConfig(ip="10.30.73")


# ----------------------------------------------------------------------
# 与真实 AxleManager 的联动
# ----------------------------------------------------------------------
def bind_real_axle(manager: PlcPowerManager, axle: AxleManager) -> None:
    manager.bind_axle(
        on_safety_trip=lambda reason: axle.external_safety_trip("plc_safe", reason),
        before_power_off=axle.disable_for_power_off,
        power_on_blocker=axle.power_on_blocker,
    )
    axle.add_emergency_listener(manager.cut_power_for_emergency)


def test_axle_emergency_stop_cuts_high_voltage() -> None:
    async def run_test() -> None:
        manager, sim, _ = make_manager()
        axle = AxleManager(driver=create_mock_driver())
        bind_real_axle(manager, axle)
        await manager.connect(SIM_CONFIG)
        try:
            await manager.power_on()
            await axle.emergency_stop()
            await asyncio.sleep(0.05)  # 联动在后台任务中执行
            assert not request_power_bit(sim)
        finally:
            await manager.shutdown()

    asyncio.run(run_test())


def test_plc_safe_trip_locks_axle_and_records_trip() -> None:
    async def run_test() -> None:
        manager, sim, _ = make_manager()
        axle = AxleManager(driver=create_mock_driver())
        bind_real_axle(manager, axle)
        await manager.connect(SIM_CONFIG)
        try:
            await manager.power_on()
            sim.safe = False
            await asyncio.sleep(0.15)
            telemetry = axle.get_telemetry()
            assert axle.is_emergency_locked
            assert telemetry.safety.last_trip is not None
            assert telemetry.safety.last_trip.metric == "plc_safe"
            assert "Safe=0" in telemetry.safety.last_trip.message
            await asyncio.sleep(0.05)  # 等急停联动执行完
            # 急停联动不应覆盖更准确的 Safe 断开原因
            assert manager.status().last_message == "PLC 安全回路断开 (Safe=0)，已复位上电请求"
        finally:
            await manager.shutdown()

    asyncio.run(run_test())


def test_power_on_blocked_while_motor_enabled_and_power_off_disables_first() -> None:
    async def run_test() -> None:
        manager, sim, _ = make_manager()
        axle = AxleManager(driver=create_mock_driver())
        bind_real_axle(manager, axle)
        await manager.connect(SIM_CONFIG)
        await axle.connect(CanConnectRequest())
        try:
            await manager.power_on()
            # 关闭越限与看门狗（模拟总线上没有 MCU 反馈），只验证下电顺序
            await axle.update_safety_config(
                axle.get_safety_config().model_copy(update={"enabled": False})
            )
            await axle.update_command(VcuCommandUpdateRequest(mcu_en_cmd=1, speed_req=500))

            await manager.power_off()
            assert axle.get_telemetry().command.mcu_en_cmd == 0
            assert not request_power_bit(sim)

            await axle.update_command(VcuCommandUpdateRequest(mcu_en_cmd=1))
            with pytest.raises(PlcOperationError, match="使能状态"):
                await manager.power_on()
        finally:
            await axle.disconnect()
            await manager.shutdown()

    asyncio.run(run_test())
