"""循环测试结束后的自动判定与自动下电（仿真 PLC + 模拟 CAN 驱动）。"""

# 业务类名以 Test 开头（TestRecordStore 等），按模块导入，避免被 pytest 当作测试类收集

import asyncio
import struct
import time
from pathlib import Path

from app.core.plc.client import SimulatedStationClient
from app.schemas import test_records as record_schemas
from app.schemas.axle import (
    CanConnectRequest,
    CycleTestStartRequest,
    CycleTestStatus,
    CycleTestStep,
)
from app.schemas.plc import PlcConfig
from app.services import test_records as record_store
from app.services.auto_judge import CycleAutoJudge, evaluate_cycle
from app.services.axle_manager import AxleManager
from app.services.plc_manager import PlcPowerManager
from tests.test_axle_manager import benign_mcu_2_frame, create_mock_driver

ONE_STEP_CYCLE = CycleTestStartRequest(
    steps=[CycleTestStep(id="s", name="短步骤", gear=1, target_speed=300, duration_seconds=1)]
)


class Bench:
    """电驱桥 + 仿真 PLC + 试车记录，按生产环境的方式联动。"""

    def __init__(self, tmp_path: Path) -> None:
        driver = create_mock_driver()
        # MCU 持续回传零转速 0x35B：满足反馈看门狗，且电机视为已停转
        driver.receive.side_effect = lambda **_: [benign_mcu_2_frame()]
        self.axle = AxleManager(driver=driver)
        self.sim = SimulatedStationClient(power_on_delay_s=0.05, power_off_delay_s=0.05)
        self.plc = PlcPowerManager(
            client_factory=lambda _config: self.sim,
            power_on_timeout_s=0.6,
            power_off_timeout_s=0.4,
            poll_interval_s=0.02,
        )
        self.plc.bind_axle(
            on_safety_trip=lambda reason: self.axle.external_safety_trip("plc_safe", reason),
            before_power_off=self.axle.disable_for_power_off,
            power_on_blocker=self.axle.power_on_blocker,
            mes_telemetry=self.axle.mes_telemetry,
        )
        self.axle.add_emergency_listener(self.plc.cut_power_for_emergency)
        self.store = record_store.TestRecordStore(tmp_path / "records.db", tmp_path / "exports")
        judge = CycleAutoJudge(
            axle=self.axle,
            plc=self.plc,
            store_factory=lambda: self.store,
            motor_stop_timeout_s=0.5,
        )
        self.axle.add_cycle_finished_listener(judge.on_cycle_finished)

    async def start(self) -> None:
        await self.axle.connect(CanConnectRequest())
        await self.plc.connect(PlcConfig(simulation=True))
        assert (await self.plc.power_on()).status == "success"

    async def close(self) -> None:
        await self.axle.disconnect()
        await self.plc.shutdown()

    def cycle(self) -> CycleTestStatus:
        return self.axle.get_telemetry().cycle_test

    async def wait_judged(self, timeout_s: float = 5.0) -> CycleTestStatus:
        deadline = time.monotonic() + timeout_s
        while self.cycle().auto_judge != "done":
            assert time.monotonic() < deadline, f"自动判定未完成: {self.cycle()}"
            await asyncio.sleep(0.05)
        return self.cycle()

    def plc_result(self) -> int:
        return struct.unpack_from(">h", self.sim.read_station(), 6)[0]


def test_completed_cycle_without_faults_is_ok_and_powers_off(tmp_path: Path) -> None:
    async def run_test() -> None:
        bench = Bench(tmp_path)
        await bench.start()
        try:
            # 循环前手动调试时的故障码不计入本轮
            bench.axle.test_session.on_mcu_1(bus_current_a=0.0, fault_code=64)
            await bench.axle.start_cycle_test(ONE_STEP_CYCLE)
            cycle = await bench.wait_judged()

            assert cycle.status == "completed"
            assert cycle.auto_judge_result == 1
            assert cycle.auto_judge_message is not None
            assert "自动下电" in cycle.auto_judge_message
            assert bench.plc_result() == 1
            status = bench.plc.status()
            assert not (status.request_power or status.power_on or status.contactor_closed)

            records = bench.store.query(record_store.TestRecordFilters())
            assert [r.result for r in records] == [1]
            assert records[0].remark.startswith("自动判定合格")
            assert records[0].plc_result_written is True
        finally:
            await bench.close()

    asyncio.run(run_test())


def test_fault_code_during_cycle_is_ng(tmp_path: Path) -> None:
    async def run_test() -> None:
        bench = Bench(tmp_path)
        await bench.start()
        try:
            await bench.axle.start_cycle_test(ONE_STEP_CYCLE)
            bench.axle.test_session.on_mcu_1(bus_current_a=0.0, fault_code=64)
            cycle = await bench.wait_judged()

            assert cycle.status == "completed"
            assert cycle.auto_judge_result == 2
            assert bench.plc_result() == 2
            records = bench.store.query(record_store.TestRecordFilters())
            assert records[0].result == 2
            assert "MCU_64" in records[0].remark
            assert not bench.plc.status().power_on
        finally:
            await bench.close()

    asyncio.run(run_test())


def test_emergency_stop_during_cycle_is_ng(tmp_path: Path) -> None:
    async def run_test() -> None:
        bench = Bench(tmp_path)
        await bench.start()
        try:
            await bench.axle.start_cycle_test(ONE_STEP_CYCLE)
            await bench.axle.emergency_stop()
            cycle = await bench.wait_judged()

            assert cycle.status == "stopped"
            assert cycle.auto_judge_result == 2
            records = bench.store.query(record_store.TestRecordFilters())
            assert records[0].result == 2
            assert "急停" in records[0].remark
            assert not bench.plc.status().power_on
        finally:
            await bench.close()

    asyncio.run(run_test())


def test_operator_stop_does_not_judge_or_power_off(tmp_path: Path) -> None:
    async def run_test() -> None:
        bench = Bench(tmp_path)
        await bench.start()
        try:
            await bench.axle.start_cycle_test(ONE_STEP_CYCLE)
            assert bench.axle.judge_blocker() is not None  # 循环中不允许手动判定
            await bench.axle.stop_cycle_test()
            await asyncio.sleep(0.3)

            assert bench.cycle().auto_judge == "none"
            assert bench.axle.judge_blocker() is None
            assert bench.store.query(record_store.TestRecordFilters()) == []
            assert bench.plc.status().power_on
        finally:
            await bench.close()

    asyncio.run(run_test())


def test_evaluate_cycle_rules() -> None:
    completed = CycleTestStatus(status="completed", total_loops=3)
    assert evaluate_cycle(completed, record_schemas.TestSessionStats())[0] == 1

    result, remark = evaluate_cycle(completed, record_schemas.TestSessionStats(safety_trips=1))
    assert result == 2 and "安全停机 1 次" in remark

    aborted = CycleTestStatus(status="error", last_error="CAN 链路故障")
    result, remark = evaluate_cycle(aborted, record_schemas.TestSessionStats())
    assert result == 2 and "CAN 链路故障" in remark
