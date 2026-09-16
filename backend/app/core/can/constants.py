"""CAN protocol constants, message IDs, and signal enumeration definitions.

All names and values are strictly mapped to the DBC and Excel communication matrix:
- 东风无人车.dbc
- DFAC_Matrix_11898_CAN_台架_V0.9-0130_MCU(1).xlsx
"""

from enum import IntEnum

# ==============================================================================
# CAN 报文 ID 定义 (CAN Message Identifiers)
# ==============================================================================
# 上位机 (VCU) 发送给驱动电机控制器 (MCU) 的控制报文
CAN_ID_VCU_11: int = 0x314  # 788, 周期 10ms, DLC 8

# 电机控制器 (MCU) 反馈给上位机的报文
CAN_ID_MCU_DRIVE_MOTOR_1: int = 0x35A  # 858, 周期 100ms, 母线电气与故障状态
CAN_ID_MCU_DRIVE_MOTOR_2: int = 0x35B  # 859, 周期 10ms, 转矩/转速核心动力反馈
CAN_ID_MCU_TBOX_DRIVE_MOTOR: int = 0x35C  # 860, 周期 100ms, 电机与控制器温度及状态


# ==============================================================================
# 周立功 ZLG CAN 设备类型常量
# ==============================================================================
class ZcanDeviceType(IntEnum):
    """周立功 USBCAN 设备类型枚举值。"""

    USBCAN1 = 3
    USBCAN2 = 4
    USBCAN_E_U = 20
    USBCAN_2E_U = 21


# ==============================================================================
# 经典版 CAN 设备波特率与 SJA1000 (Timing0, Timing1) 寄存器映射表
# 保持与用户其他项目 (如 usb_can_app) 的硬件参数一致
# ==============================================================================
BAUDRATE_TIMINGS: dict[int, tuple[int, int]] = {
    10000: (0x31, 0x1C),
    20000: (0x18, 0x1C),
    50000: (0x09, 0x1C),
    100000: (0x04, 0x1C),
    125000: (0x03, 0x1C),
    250000: (0x01, 0x1C),
    500000: (0x00, 0x1C),
    800000: (0x00, 0x16),
    1000000: (0x00, 0x14),
}


# ==============================================================================
# 信号枚举定义 (Signal Enumerations)
# ==============================================================================
class VcuWorkModeReq(IntEnum):
    """VCU 电机工作模式控制 (VCU_MotorWorkModReq)."""

    CLOSE = 0  # 关闭（保留，默认扭矩控制）
    TORQUE = 1  # 扭矩模式
    ZERO_TORQUE = 2  # 零扭矩模式
    SPEED = 3  # 速度模式
    BRAKE = 4  # 制动模式（保留）
    FORWARD = 5  # 前进模式（保留）
    REVERSE = 6  # 倒车模式（保留）


class VcuMcuEnCmd(IntEnum):
    """VCU MCU 使能命令 (VCU_MCUEnCmd)."""

    DISABLE = 0  # 未使能
    ENABLE = 1  # 使能


class VcuGearStatus(IntEnum):
    """VCU 档位状态 (VCU_GearSts)."""

    D = 1  # 前进挡 (Drive)
    R = 2  # 后退挡 (Reverse)
    N = 3  # 空挡 (Neutral)
    L = 4  # 爬坡挡 (Low)
    P = 5  # 驻车挡 (Park)


class VcuActiveDischarge(IntEnum):
    """VCU 主动放电命令 (VCU_ActiveDischg)."""

    INACTIVE = 0  # 无效/不放电
    ACTIVE = 1  # 有效/请求放电


class McuMotorWorkMode(IntEnum):
    """MCU 电机工作模式反馈 (MCU_MotorWorkMod)."""

    NO_OPERATION = 0  # 无操作
    TORQUE = 1  # 扭矩模式
    ZERO_TORQUE = 2  # 零扭矩模式
    SPEED = 3  # 速度模式
    BRAKE = 4  # 制动模式
    FORWARD = 5  # 前进模式
    REVERSE = 6  # 倒车模式


class McuActiveDischargeStatus(IntEnum):
    """MCU 主动放电状态 (MCU_ActiveDischrgSts)."""

    DISCHARGING = 0  # 放电中
    FINISHED = 1  # 放电完成
    FAILED = 2  # 放电失败
    INVALID = 3  # 无效


class McuFaultLevel(IntEnum):
    """MCU 故障等级 (MCU_FltLevl)."""

    NO_FAULT = 0  # 无故障
    LEVEL_1 = 1  # 一级故障（最轻微）
    LEVEL_2 = 2  # 二级故障
    LEVEL_3 = 3  # 三级故障
    LEVEL_4 = 4  # 四级故障（最严重）


class McuTboxFaultLevel(IntEnum):
    """MCU 温度故障等级 (MCU_TBOX_FltLevl)."""

    NO_FAULT = 0  # 无故障
    LEVEL_1 = 1  # 一级故障（最轻微）
    LEVEL_2_POWER_LIMIT = 2  # 二级故障（限功）
    LEVEL_3_HIGH_VOLTAGE_OFF = 3  # 三级故障（下高压）


class MotorState(IntEnum):
    """驱动电机运行状态 (stMtr)."""

    CONSUMING = 1  # 耗电驱动
    GENERATING = 2  # 发电制动
    OFF = 3  # 关闭状态
    READY = 4  # 准备状态
    INVALID = 255  # 无效
