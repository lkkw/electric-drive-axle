"""FastAPI router for Electric Drive Axle control and real-time SSE streaming."""

import asyncio
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.core.can.constants import MCU_FAULT_CODES
from app.core.can.driver import CanDriverError
from app.dependencies import AxleManagerDep
from app.schemas.axle import (
    AxleActionResponse,
    AxleSafetyConfig,
    AxleTelemetry,
    CanConnectRequest,
    CanSendRawFrameRequest,
    McuFaultCodeItem,
    VcuCommandState,
    VcuCommandUpdateRequest,
)
from app.services.axle_manager import STREAM_FRAME_LIMIT

logger = logging.getLogger("app.routers.axle")

router = APIRouter(prefix="/axle", tags=["Electric Drive Axle"])


@router.get(
    "/fault-codes",
    response_model=list[McuFaultCodeItem],
    summary="获取电驱桥 MCU 故障代码表 (DEF 三列)",
)
async def get_fault_codes() -> list[McuFaultCodeItem]:
    """获取所有 MCU 故障代码表。

    包含故障码 (DisplayCode)、含义 (DTC Meaning) 与故障级别 (FaultLevel)。
    """
    return [
        McuFaultCodeItem(
            code=item.code,
            meaning=item.meaning,
            level=item.level,
            raw_code=item.raw_code,
        )
        for item in MCU_FAULT_CODES
    ]


@router.post(
    "/can/send",
    response_model=AxleActionResponse,
    summary="手动下发单帧 CAN 原始测试或诊断报文",
)
async def send_raw_frame(
    request: CanSendRawFrameRequest,
    manager: AxleManagerDep,
) -> AxleActionResponse:
    """向下位机或总线手动下发单帧 CAN 测试或诊断报文。"""
    try:
        success = await manager.send_raw_frame(request)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="CAN 控制器硬件发送失败，请检查总线物理连接与终端电阻。",
            )
        return AxleActionResponse(
            success=True,
            message=f"CAN 报文已成功发送 (ID=0x{request.can_id:X})",
            data={
                "can_id": request.can_id,
                "can_id_hex": f"0x{request.can_id:X}",
                "data_hex": request.data_hex,
            },
        )
    except CanDriverError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(err),
        ) from err


@router.post(
    "/can/clear-frames",
    response_model=AxleActionResponse,
    summary="清空最近 CAN 报文监视缓冲区",
)
async def clear_can_frames(
    manager: AxleManagerDep,
) -> AxleActionResponse:
    """清空上位机内存中缓存的最近原始 CAN 报文记录。"""
    manager.clear_frames()
    return AxleActionResponse(
        success=True,
        message="报文监视缓冲区已清空。",
    )


@router.post(
    "/connect",
    response_model=AxleActionResponse,
    summary="连接周立功 USBCAN 硬件并启动控制循环",
)
async def connect_can(
    config: CanConnectRequest,
    manager: AxleManagerDep,
) -> AxleActionResponse:
    """打开指定类型的周立功 USBCAN 硬件设备，初始化通道波特率并开启 10ms VCU_11 发送循环。"""
    try:
        await manager.connect(config)
        return AxleActionResponse(
            success=True,
            message="USBCAN 设备已成功连接，10ms 控制循环已启动。",
            data={
                "device_type": config.device_type,
                "device_index": config.device_index,
                "channel": config.channel,
                "baud_rate": config.baud_rate,
            },
        )
    except CanDriverError as err:
        logger.error("CAN 驱动层连接失败: %s", err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"USBCAN 设备连接失败: {err}",
        ) from err
    except Exception as err:
        logger.exception("连接 USBCAN 设备时发生未知错误")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"连接异常: {err}",
        ) from err


@router.post(
    "/disconnect",
    response_model=AxleActionResponse,
    summary="安全停止控制循环并断开 USBCAN 设备",
)
async def disconnect_can(
    manager: AxleManagerDep,
) -> AxleActionResponse:
    """下发停机安全指令，停止 10ms 循环，关闭 CAN 通道并释放硬件资源。"""
    try:
        await manager.disconnect()
        return AxleActionResponse(
            success=True,
            message="USBCAN 设备已安全断开连接。",
        )
    except Exception as err:
        logger.error("断开 CAN 连接异常: %s", err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"断开设备异常: {err}",
        ) from err


@router.post(
    "/command",
    response_model=VcuCommandState,
    summary="更新上位机控制设定值 (转矩/转速/模式/使能/档位)",
)
async def update_command(
    update: VcuCommandUpdateRequest,
    manager: AxleManagerDep,
) -> VcuCommandState:
    """更新上位机发送给 MCU 的目标控制参数，参数在下一次 10ms 周期立即生效。"""
    return await manager.update_command(update)


@router.get(
    "/safety/config",
    response_model=AxleSafetyConfig,
    summary="获取上位机自动紧急停机阈值",
)
async def get_safety_config(
    manager: AxleManagerDep,
) -> AxleSafetyConfig:
    """获取当前自动停机开关及速度、转矩、电机温度阈值。"""
    return manager.get_safety_config()


@router.put(
    "/safety/config",
    response_model=AxleSafetyConfig,
    summary="更新上位机自动紧急停机阈值",
)
async def update_safety_config(
    config: AxleSafetyConfig,
    manager: AxleManagerDep,
) -> AxleSafetyConfig:
    """保存自动停机配置；仅后续新鲜 MCU 反馈会参与越限判定。"""
    return await manager.update_safety_config(config)


@router.post(
    "/emergency-stop",
    response_model=VcuCommandState,
    summary="一键紧急停机",
)
async def emergency_stop(
    manager: AxleManagerDep,
) -> VcuCommandState:
    """最高优先级紧急停机：使能拉低置 0，转矩与转速归零，挂空挡，并立即强制同步下发停机帧。"""
    return await manager.emergency_stop()


@router.post(
    "/emergency-reset",
    summary="复位急停互锁",
)
async def emergency_reset(
    manager: AxleManagerDep,
) -> VcuCommandState:
    """解除急停锁定，允许后续正常控制指令。"""
    return await manager.emergency_reset()


@router.get(
    "/status",
    response_model=AxleTelemetry,
    summary="获取电驱桥系统最新遥测快照",
)
async def get_axle_status(
    manager: AxleManagerDep,
) -> AxleTelemetry:
    """获取当前电驱桥通信状态、最新遥测数据包及统计计数器。"""
    return manager.get_telemetry()


async def _telemetry_event_stream(
    request: Request,
    manager: AxleManagerDep,
    *,
    include_frames: bool,
) -> AsyncGenerator[str, None]:
    """SSE 遥测事件生成器。

    订阅 AxleManager 的广播队列，以低延迟将电驱桥遥测数据推送至前端。
    """
    queue = manager.subscribe(include_frames=include_frames)

    # 首次连接立即推送当前最新快照
    initial_snapshot = manager.get_telemetry(
        include_frames=include_frames,
        frame_limit=STREAM_FRAME_LIMIT if include_frames else None,
    )
    initial_json = initial_snapshot.model_dump_json()
    yield f"event: telemetry\ndata: {initial_json}\n\n"

    try:
        while True:
            if await request.is_disconnected():
                break

            try:
                # 阻塞等待新遥测推送，带 1.0s 超时保活心跳
                telemetry = await asyncio.wait_for(queue.get(), timeout=1.0)
                payload_json = telemetry.model_dump_json()
                yield f"event: telemetry\ndata: {payload_json}\n\n"
            except TimeoutError:
                # 定期心跳包防止反向代理超时切断 SSE 连接
                yield ": keep-alive\n\n"

    except asyncio.CancelledError:
        pass
    finally:
        manager.unsubscribe(queue)


@router.get(
    "/stream",
    summary="订阅电驱桥实时遥测 SSE 数据流",
)
async def stream_telemetry(
    request: Request,
    manager: AxleManagerDep,
    include_frames: bool = False,
) -> StreamingResponse:
    """建立 Server-Sent Events (SSE) 长连接，持续推送电驱桥各控制器遥测数据。"""
    return StreamingResponse(
        _telemetry_event_stream(
            request,
            manager,
            include_frames=include_frames,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
