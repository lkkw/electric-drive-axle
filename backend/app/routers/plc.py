"""PLC 连接与自动上电 / 下电接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.plc import (
    PlcActionResponse,
    PlcConfig,
    PlcSimulationSafeRequest,
    PlcStatus,
    PlcTrafficLogResponse,
    PlcTrafficSnapshot,
)
from app.services.plc_manager import PlcOperationError, PlcPowerManager, get_plc_manager

router = APIRouter(prefix="/plc", tags=["PLC Power"])

PlcManagerDep = Annotated[PlcPowerManager, Depends(get_plc_manager)]


def _http_error(err: PlcOperationError) -> HTTPException:
    return HTTPException(status_code=err.status_code, detail=err.message)


@router.get("/status", response_model=PlcStatus, summary="PLC 连接与台架供电状态")
async def get_plc_status(manager: PlcManagerDep) -> PlcStatus:
    """内存快照，由后台每 0.2 s 刷新，读取本接口不产生 PLC 通讯。"""
    return manager.status()


@router.get("/config", response_model=PlcConfig, summary="上次保存的 PLC 连接参数")
async def get_plc_config(manager: PlcManagerDep) -> PlcConfig:
    return manager.config


@router.post("/connect", response_model=PlcStatus, summary="连接 PLC（参数会被保存）")
async def connect_plc(config: PlcConfig, manager: PlcManagerDep) -> PlcStatus:
    try:
        return await manager.connect(config)
    except PlcOperationError as err:
        raise _http_error(err) from err


@router.post("/disconnect", response_model=PlcStatus, summary="断开 PLC")
async def disconnect_plc(manager: PlcManagerDep) -> PlcStatus:
    """台架仍在供电时拒绝断开（断开后将失去 Safe 联锁）。"""
    try:
        return await manager.disconnect()
    except PlcOperationError as err:
        raise _http_error(err) from err


@router.post("/power-on", response_model=PlcActionResponse, summary="PLC 自动上电（340 V）")
async def power_on(manager: PlcManagerDep) -> PlcActionResponse:
    """确认 Safe=1 后请求上电，最长等待 30 s 收到上电完成与主接触器吸合。"""
    try:
        return await manager.power_on()
    except PlcOperationError as err:
        raise _http_error(err) from err


@router.post("/power-off", response_model=PlcActionResponse, summary="PLC 下电")
async def power_off(manager: PlcManagerDep) -> PlcActionResponse:
    """先关闭电机使能，再复位上电请求，最长 5 s 确认主接触器断开。"""
    try:
        return await manager.power_off()
    except PlcOperationError as err:
        raise _http_error(err) from err


@router.post(
    "/simulation/safe",
    response_model=PlcStatus,
    summary="仿真模式下模拟安全回路闭合 / 断开",
)
async def set_simulated_safe(
    request: PlcSimulationSafeRequest, manager: PlcManagerDep
) -> PlcStatus:
    try:
        return manager.set_simulated_safe(request.safe)
    except PlcOperationError as err:
        raise _http_error(err) from err


@router.get(
    "/traffic/snapshot",
    response_model=PlcTrafficSnapshot,
    summary="PLC 通信监视：1 号工位全部点位的最新值",
)
async def get_traffic_snapshot(manager: PlcManagerDep) -> PlcTrafficSnapshot:
    """常驻监视每 0.2 s 读取一次工位时更新，读取本接口不产生 PLC 通讯。"""
    return PlcTrafficSnapshot.model_validate(manager.traffic.snapshot())


@router.get(
    "/traffic/log",
    response_model=PlcTrafficLogResponse,
    summary="PLC 通信记录：上位机每次写入与 PLC 反馈变化",
)
async def get_traffic_log(
    manager: PlcManagerDep,
    after_seq: int = Query(0, ge=0, description="只返回序号大于该值的记录"),
) -> PlcTrafficLogResponse:
    return PlcTrafficLogResponse.model_validate(manager.traffic.entries(after_seq))


@router.delete("/traffic/log", summary="清空 PLC 通信记录")
async def clear_traffic_log(manager: PlcManagerDep) -> dict[str, str]:
    manager.traffic.clear()
    return {"status": "success", "message": "通信记录已清空"}
