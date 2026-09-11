"""CAN communication package for Electric Drive Axle system."""

from app.core.can.constants import (
    CAN_ID_MCU_DRIVE_MOTOR_1,
    CAN_ID_MCU_DRIVE_MOTOR_2,
    CAN_ID_MCU_TBOX_DRIVE_MOTOR,
    CAN_ID_VCU_11,
    McuActiveDischargeStatus,
    McuFaultLevel,
    McuMotorWorkMode,
    McuTboxFaultLevel,
    MotorState,
    VcuActiveDischarge,
    VcuGearStatus,
    VcuMcuEnCmd,
    VcuWorkModeReq,
    ZcanDeviceType,
)
from app.core.can.driver import (
    CanDriverError,
    CanRawFrame,
    ZlgCanDriver,
)

__all__ = [
    "CAN_ID_MCU_DRIVE_MOTOR_1",
    "CAN_ID_MCU_DRIVE_MOTOR_2",
    "CAN_ID_MCU_TBOX_DRIVE_MOTOR",
    "CAN_ID_VCU_11",
    "CanDriverError",
    "CanRawFrame",
    "McuActiveDischargeStatus",
    "McuFaultLevel",
    "McuMotorWorkMode",
    "McuTboxFaultLevel",
    "MotorState",
    "VcuActiveDischarge",
    "VcuGearStatus",
    "VcuMcuEnCmd",
    "VcuWorkModeReq",
    "ZcanDeviceType",
    "ZlgCanDriver",
]
