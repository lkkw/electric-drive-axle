"""试车判定：操作员手动判定，以及循环测试结束后的自动判定与自动下电。

自动判定规则：循环正常跑完全部圈数，且本轮循环期间没有 MCU 故障码、没有触发急停 /
自动安全停机，判合格；否则判 NG。循环跑完或异常中断（急停、CAN 链路故障等）都会
自动判定并请求下电；操作员主动终止循环则不判定、不下电，交给操作员处理。
"""

import asyncio
import logging
from collections.abc import Callable

from app.core.logging_setup import EVENT_LOGGER_NAME
from app.schemas.axle import CycleTestStatus
from app.schemas.test_records import TestRecordJudgeResponse, TestResult, TestSessionStats
from app.services.axle_manager import AxleManager
from app.services.plc_manager import PlcOperationError, PlcPowerManager
from app.services.test_records import TestRecordStore

logger = logging.getLogger("app.auto_judge")
events = logging.getLogger(EVENT_LOGGER_NAME)

# 下电前等待电机停转的最长时间；超时仍下电（急停时高压已由联动切断）
MOTOR_STOP_TIMEOUT_SECONDS = 30.0


async def judge_test(
    *,
    result: TestResult,
    remark: str,
    axle: AxleManager,
    plc: PlcPowerManager,
    store: TestRecordStore,
) -> TestRecordJudgeResponse:
    """把结果写入 PLC Result 上传 MES，保存试车记录，并清零统计开始下一台。

    PLC 未连接或写入失败时仍保存记录（标记未写入 PLC），并在返回信息中提示。
    """
    session = axle.test_session.snapshot()
    label = "合格" if result == 1 else "NG"
    plc_written = False
    plc_issue: str | None = None
    try:
        await plc.write_result(result)
        plc_written = True
    except PlcOperationError as err:
        plc_issue = err.message

    record = await asyncio.to_thread(
        store.add,
        result=result,
        remark=remark,
        sn=plc.serial_number(),
        session=session,
        plc_result_written=plc_written,
    )
    axle.test_session.reset()

    message = f"已判定{label}并保存试车记录"
    if plc_written:
        message += "，结果已写入 PLC"
    else:
        message += f"；结果未写入 PLC（{plc_issue}）"
    return TestRecordJudgeResponse(record=record, message=message)


def evaluate_cycle(cycle: CycleTestStatus, session: TestSessionStats) -> tuple[TestResult, str]:
    """按自动判定规则得出结论与备注（备注写入试车记录）。"""
    reasons: list[str] = []
    if cycle.status != "completed":
        reasons.append(f"循环测试未正常完成（{cycle.last_error or '异常中断'}）")
    if session.fault_codes:
        reasons.append(f"出现故障码 {', '.join(session.fault_codes)}")
    if session.safety_trips:
        reasons.append(f"触发自动安全停机 {session.safety_trips} 次")
    if reasons:
        return 2, "自动判定 NG：" + "；".join(reasons)
    return 1, f"自动判定合格：循环测试 {cycle.total_loops} 圈正常完成，无故障码、无急停"


class CycleAutoJudge:
    """循环测试结束联动：等待电机停转 → 自动判定 → 自动请求下电 → 回写结论到界面。"""

    def __init__(
        self,
        *,
        axle: AxleManager,
        plc: PlcPowerManager,
        store_factory: Callable[[], TestRecordStore],
        motor_stop_timeout_s: float = MOTOR_STOP_TIMEOUT_SECONDS,
    ) -> None:
        self._axle = axle
        self._plc = plc
        self._store_factory = store_factory
        self._motor_stop_timeout_s = motor_stop_timeout_s

    async def on_cycle_finished(self, cycle: CycleTestStatus) -> None:
        notes: list[str] = []
        result: TestResult | None = None
        try:
            # 停转后再判定：减速过程中上报的故障码也计入本轮
            if not await self._axle.wait_motor_stopped(self._motor_stop_timeout_s):
                notes.append("未确认电机已停转")

            result, remark = evaluate_cycle(cycle, self._axle.test_session.snapshot())
            response = await judge_test(
                result=result,
                remark=remark,
                axle=self._axle,
                plc=self._plc,
                store=self._store_factory(),
            )
            events.info("循环测试自动判定: %s", remark)
            notes.insert(0, f"{remark}。{response.message}")
        except Exception as err:
            logger.exception("循环测试自动判定失败: %s", err)
            events.error("循环测试自动判定失败: %s", err)
            notes.insert(0, f"自动判定失败（{err}），请手动判定")

        notes.append(await self._power_off())
        await self._axle.report_auto_judge(result, "；".join(notes))

    async def _power_off(self) -> str:
        status = self._plc.status()
        if not status.connected:
            return "PLC 未连接，未自动下电"
        if not (status.request_power or status.power_on or status.contactor_closed):
            return "台架未通电，无需下电"
        try:
            response = await self._plc.power_off()
        except PlcOperationError as err:
            events.error("循环测试结束自动下电失败: %s", err.message)
            return f"自动下电失败：{err.message}"
        except Exception as err:
            logger.exception("循环测试结束自动下电失败: %s", err)
            return f"自动下电失败：{err}"
        events.info("循环测试结束自动下电: %s", response.message)
        return f"自动下电：{response.message}"
