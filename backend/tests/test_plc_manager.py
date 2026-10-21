"""PLC 自动上电 / 下电、Safe 联锁、心跳与电驱桥联动（使用仿真 PLC）。"""

import asyncio
import socket
import struct
import threading
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
import snap7
from snap7.type import Parameter

from app.core.plc.client import (
    PlcClientError,
    SimulatedStationClient,
    apply_io_timeout,
)
from app.core.plc.points import POWER_ON_BLOCK_SIZE
from app.schemas.axle import CanConnectRequest, VcuCommandUpdateRequest
from app.schemas.plc import PlcConfig
from app.services import plc_manager as plc_manager_module
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
    io_timeout_s: float = 2.0,
) -> tuple[PlcPowerManager, SimulatedStationClient, FakeAxle]:
    sim = sim or SimulatedStationClient(power_on_delay_s=0.05, power_off_delay_s=0.05)
    manager = PlcPowerManager(
        config_path=config_path,
        client_factory=lambda _config: sim,
        power_on_timeout_s=power_on_timeout_s,
        power_off_timeout_s=0.4,
        poll_interval_s=0.02,
        io_timeout_s=io_timeout_s,
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


def test_disconnect_refused_while_power_on_in_progress() -> None:
    async def run_test() -> None:
        sim = SimulatedStationClient(power_on_delay_s=5.0, power_off_delay_s=0.05)
        manager, _, _ = make_manager(sim, power_on_timeout_s=5.0)
        await manager.connect(SIM_CONFIG)
        try:
            on_task = asyncio.create_task(manager.power_on())
            await asyncio.sleep(0.01)  # 已写入上电请求，缓存反馈可能还没刷新
            with pytest.raises(PlcOperationError, match="正在执行上电"):
                await manager.disconnect()
            with pytest.raises(PlcOperationError, match="正在执行上电"):
                await manager.connect(SIM_CONFIG)
            assert manager.status().connected

            await manager.power_off()
            with pytest.raises(PlcOperationError):
                await on_task
            assert not request_power_bit(sim)
        finally:
            await manager.shutdown()

    asyncio.run(run_test())


def test_disconnect_allowed_after_communication_lost_while_powered() -> None:
    async def run_test() -> None:
        manager, sim, _ = make_manager()
        await manager.connect(SIM_CONFIG)
        try:
            await manager.power_on()

            def broken(*_args: object) -> bytearray:
                raise PlcClientError("模拟网线断开")

            sim.read_station = broken  # type: ignore[method-assign]
            sim.update = broken  # type: ignore[method-assign]
            await asyncio.sleep(1.2)  # 反馈过期
            assert not manager.status().communication_ok

            # 通讯中断时不能被“仍在供电”的旧反馈锁死，否则无法重连恢复监视
            await manager.disconnect()
            assert not manager.status().connected

            del sim.read_station, sim.update
            await manager.connect(SIM_CONFIG)
            assert manager.status().communication_ok
            assert manager.status().power_state == "powered"
        finally:
            await manager.power_off()
            await manager.shutdown()

    asyncio.run(run_test())


def test_power_off_reports_motor_still_spinning() -> None:
    async def run_test() -> None:
        manager, sim, fake = make_manager()

        async def still_spinning() -> str | None:
            return "等待 10 s 电机仍未停稳（800 rpm）"

        manager._before_power_off = still_spinning
        await manager.connect(SIM_CONFIG)
        try:
            await manager.power_on()
            result = await manager.power_off()
            assert result.status == "partial"
            assert "已下电" in result.message and "未停稳" in result.message
            assert not request_power_bit(sim)
        finally:
            await manager.shutdown()

    asyncio.run(run_test())


def test_axle_power_off_waits_for_motor_stop_without_blocking() -> None:
    async def run_test() -> None:
        axle = AxleManager(driver=create_mock_driver())
        await axle.connect(CanConnectRequest())
        try:
            # 没有转速反馈（控制器不在线）：不等待
            started = time.monotonic()
            assert await axle.disable_for_power_off(motor_stop_timeout_s=5.0) is None
            assert time.monotonic() - started < 1.0

            # 电机仍在转：等到超时后照常放行并给出提示
            axle._mcu_2.mcu_act_motor_spd = 800
            axle._mcu_2_last_rx_timestamp = time.time() + 10
            note = await axle.disable_for_power_off(motor_stop_timeout_s=0.2)
            assert note is not None and "800 rpm" in note

            # 停稳后立即放行
            axle._mcu_2.mcu_act_motor_spd = 0
            assert await axle.disable_for_power_off(motor_stop_timeout_s=5.0) is None
        finally:
            await axle.disconnect()

    asyncio.run(run_test())


# ----------------------------------------------------------------------
# PLC 调用超时：写入顺序、卡死时不堆积、snap7 收发超时
# ----------------------------------------------------------------------
async def wait_until(predicate: Callable[[], bool], timeout_s: float = 3.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not predicate():
        assert time.monotonic() < deadline, "等待条件超时"
        await asyncio.sleep(0.01)


async def drain_plc_thread(manager: PlcPowerManager) -> None:
    """PLC 线程按提交顺序执行：排一个空调用并等它完成，之前提交的调用都已结束。"""
    await manager._io(lambda: None, limit_seconds=5.0)


class StallingSim(SimulatedStationClient):
    """模拟 snap7 调用迟迟不返回：卡在拿到客户端锁之前，后续调用不会被这把锁排好序。"""

    def __init__(self) -> None:
        super().__init__(power_on_delay_s=0.05, power_off_delay_s=0.05)
        self.release = threading.Event()
        self.stall_power_on_write = False
        self.stall_reads = False
        self.read_calls = 0

    def update(self, offset, size, transform):  # noqa: ANN001, ANN201
        if self.stall_power_on_write and size == POWER_ON_BLOCK_SIZE:
            self.stall_power_on_write = False
            self.release.wait(5)
        super().update(offset, size, transform)

    def read_station(self) -> bytearray:
        if self.stall_reads:
            self.read_calls += 1
            self.release.wait(5)
        return super().read_station()


def test_timed_out_power_on_write_cannot_override_later_reset() -> None:
    """上电写入超时后仍会执行，但必须排在随后的复位之前，最终 Request_power=0。"""

    async def run_test() -> None:
        sim = StallingSim()
        manager, _, _ = make_manager(sim, io_timeout_s=0.1)
        await manager.connect(SIM_CONFIG)
        try:
            sim.stall_power_on_write = True
            with pytest.raises(PlcOperationError, match="上电请求写入失败"):
                await manager.power_on()

            sim.release.set()  # 卡住的上电写入此时才真正写进 PLC
            await drain_plc_thread(manager)
            assert manager._stalled_calls == 0
            assert not request_power_bit(sim)
        finally:
            sim.release.set()
            await manager.shutdown()

    asyncio.run(run_test())


def test_monitor_does_not_pile_up_reads_while_plc_call_stalled() -> None:
    async def run_test() -> None:
        sim = StallingSim()
        manager, _, _ = make_manager(sim, io_timeout_s=0.1)
        await manager.connect(SIM_CONFIG)
        try:
            sim.stall_reads = True
            await wait_until(lambda: manager._stalled_calls == 1)
            await asyncio.sleep(0.5)  # 约 25 个监视周期
            assert sim.read_calls == 1  # 只有卡住的那一次真正进了 PLC 线程
            assert manager._executor._work_queue.qsize() == 0  # 没有排队的读取

            sim.stall_reads = False
            sim.release.set()
            await wait_until(lambda: manager._stalled_calls == 0)
            await wait_until(lambda: manager.status().communication_ok)  # 监视恢复
        finally:
            sim.release.set()
            await manager.shutdown()

    asyncio.run(run_test())


def test_connect_timeout_queues_disconnect_after_late_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """连接超时后客户端仍可能在后台连上，随后排队的断开会把它关掉。"""

    class SlowClient:
        def __init__(self) -> None:
            self.release = threading.Event()
            self.calls: list[str] = []

        def connect(self) -> None:
            self.release.wait(5)
            self.calls.append("connect")

        def disconnect(self) -> None:
            self.calls.append("disconnect")

    async def run_test() -> None:
        slow = SlowClient()
        manager = PlcPowerManager(client_factory=lambda _config: slow)  # type: ignore[arg-type,return-value]
        monkeypatch.setattr(plc_manager_module, "CONNECT_TIMEOUT_SECONDS", 0.1)
        with pytest.raises(PlcOperationError, match="超时") as exc:
            await manager.connect(PlcConfig(ip="192.168.8.1"))
        assert exc.value.status_code == 502
        assert not manager.status().connected

        slow.release.set()
        await drain_plc_thread(manager)
        assert slow.calls == ["connect", "disconnect"]

    asyncio.run(run_test())


def test_apply_io_timeout_sets_param_and_socket_timeout() -> None:
    client = snap7.client.Client()
    sock = socket.socket()
    try:
        # snap7 3.x 纯 Python 实现：实际收发超时取连接对象的 socket 超时
        client.connection = SimpleNamespace(timeout=5.0, socket=sock)
        apply_io_timeout(client, 0.8)
        assert client.get_param(Parameter.RecvTimeout) == 800
        assert client.get_param(Parameter.SendTimeout) == 800
        assert client.connection.timeout == 0.8
        assert sock.gettimeout() == 0.8
    finally:
        sock.close()
