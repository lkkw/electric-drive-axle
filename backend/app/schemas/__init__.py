"""Pydantic request and response models."""

from app.schemas.axle import (
    AxleActionResponse,
    AxleTelemetry,
    CanConnectRequest,
    CanFrameItem,
    CanSendRawFrameRequest,
    McuDriveMotor1Telemetry,
    McuDriveMotor2Telemetry,
    McuTboxTelemetry,
    VcuCommandState,
    VcuCommandUpdateRequest,
)

__all__ = [
    "AxleActionResponse",
    "AxleTelemetry",
    "CanConnectRequest",
    "CanFrameItem",
    "CanSendRawFrameRequest",
    "McuDriveMotor1Telemetry",
    "McuDriveMotor2Telemetry",
    "McuTboxTelemetry",
    "VcuCommandState",
    "VcuCommandUpdateRequest",
]
