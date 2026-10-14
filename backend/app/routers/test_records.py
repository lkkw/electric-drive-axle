"""试车记录：当前试车统计、操作员判定（写入 PLC Result）、历史查询与 CSV 导出。"""

import asyncio
import logging
import os
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.schemas.test_records import (
    TestRecord,
    TestRecordExportResponse,
    TestRecordJudgeRequest,
    TestRecordJudgeResponse,
    TestSessionStats,
)
from app.services.axle_manager import AxleManager, get_axle_manager
from app.services.plc_manager import PlcOperationError, PlcPowerManager, get_plc_manager
from app.services.test_records import TestRecordFilters, TestRecordStore, get_test_record_store

logger = logging.getLogger("app.test_records")

router = APIRouter(prefix="/test-records", tags=["Test Records"])

AxleManagerDep = Annotated[AxleManager, Depends(get_axle_manager)]
PlcManagerDep = Annotated[PlcPowerManager, Depends(get_plc_manager)]
StoreDep = Annotated[TestRecordStore, Depends(get_test_record_store)]
DateFromQuery = Annotated[date | None, Query(description="起始日期（本地，含）")]
DateToQuery = Annotated[date | None, Query(description="结束日期（本地，含）")]
SnQuery = Annotated[str | None, Query(description="序列号（包含匹配）")]
ResultQuery = Annotated[int | None, Query(ge=1, le=2, description="1=合格 2=NG")]


@router.get("/session", response_model=TestSessionStats, summary="当前这台电驱桥的试车统计")
async def get_test_session(axle: AxleManagerDep) -> TestSessionStats:
    return axle.test_session.snapshot()


@router.post("/judge", response_model=TestRecordJudgeResponse, summary="试车判定（合格 / NG）")
async def judge_test(
    request: TestRecordJudgeRequest,
    axle: AxleManagerDep,
    plc: PlcManagerDep,
    store: StoreDep,
) -> TestRecordJudgeResponse:
    """把结果写入 PLC Result 上传 MES，保存试车记录，并清零统计开始下一台。

    PLC 未连接或写入失败时仍保存记录（标记未写入 PLC），并在返回信息中提示。
    """
    session = axle.test_session.snapshot()
    label = "合格" if request.result == 1 else "NG"
    plc_written = False
    plc_issue: str | None = None
    try:
        await plc.write_result(request.result)
        plc_written = True
    except PlcOperationError as err:
        plc_issue = err.message

    record = await asyncio.to_thread(
        store.add,
        result=request.result,
        remark=request.remark,
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


def _filters(
    date_from: date | None, date_to: date | None, sn: str | None, result: int | None
) -> TestRecordFilters:
    return TestRecordFilters(date_from=date_from, date_to=date_to, sn=sn or None, result=result)


@router.get("", response_model=list[TestRecord], summary="查询试车记录（最新在前）")
async def list_test_records(
    store: StoreDep,
    date_from: DateFromQuery = None,
    date_to: DateToQuery = None,
    sn: SnQuery = None,
    result: ResultQuery = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> list[TestRecord]:
    return await asyncio.to_thread(store.query, _filters(date_from, date_to, sn, result), limit)


@router.post("/export", response_model=TestRecordExportResponse, summary="导出试车记录 CSV")
async def export_test_records(
    store: StoreDep,
    date_from: DateFromQuery = None,
    date_to: DateToQuery = None,
    sn: SnQuery = None,
    result: ResultQuery = None,
    open_folder: Annotated[bool, Query(description="导出后在资源管理器中打开所在文件夹")] = False,
) -> TestRecordExportResponse:
    """按筛选条件导出为 CSV（保存在数据目录的 exports 文件夹，可直接用 Excel 打开）。"""
    records = await asyncio.to_thread(
        store.query, _filters(date_from, date_to, sn, result), 100_000
    )
    path = await asyncio.to_thread(store.export_csv, records)
    if open_folder and hasattr(os, "startfile"):
        try:
            os.startfile(str(path.parent))  # 上位机界面与后端在同一台电脑上
        except OSError as err:
            logger.warning("打开导出文件夹失败: %s", err)
    return TestRecordExportResponse(path=str(path), count=len(records))
