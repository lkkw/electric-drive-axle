"""CAN protocol constants, message IDs, and signal enumeration definitions.

All names and values are strictly mapped to the DBC and Excel communication matrix:
- DFAC_Matrix_11898_CAN_DF_8_AMB2_V1.2_PCAN-0813_MCU.xlsx
- DFAC 控制器故障代码-AMB2(2).xlsx
"""

from dataclasses import dataclass
from enum import IntEnum

# ==============================================================================
# CAN 报文 ID 定义 (CAN Message Identifiers)
# ==============================================================================
# 上位机 (VCU) 发送给驱动电机控制器 (MCU) 的控制报文 (原 0x314，现更新为 0x258)
CAN_ID_VCU_11: int = 0x258  # 600, 周期 10ms, DLC 8

# 电机控制器 (MCU) 反馈给上位机的报文
CAN_ID_MCU_DRIVE_MOTOR_1: int = 0x35A  # 858, 周期 100ms, 母线电气与故障状态
CAN_ID_MCU_DRIVE_MOTOR_2: int = 0x35B  # 859, 周期 10ms, 转矩/转速核心动力反馈
CAN_ID_MCU_TBOX_DRIVE_MOTOR: int = 0x35C  # 860, 周期 100ms, 电机与控制器温度及状态

# 新协议补充报文
CAN_ID_MCU_SV: int = 0x5EF  # 1519, 周期 1000ms, 软件版本与标定版本反馈
CAN_ID_ONEBOX_ESC_TSC1: int = 0x251  # 593, 周期 10ms, Onebox ESC 牵引力控制
CAN_ID_ONEBOX_ESC_ENERGYRECOVERY: int = 0x254  # 596, 周期 20ms, 能量回收状态


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


class McmSlopeSts(IntEnum):
    """驻坡状态反馈 (MCM_Slope_Sts，在 MCU_Drive_motor_2 报文中)."""

    NO_SLOPE = 0  # 未驻坡
    SLOPE = 1  # 驻坡


class VcuHandBrkSts(IntEnum):
    """手刹状态 (VCU_HandBrkSts)."""

    INVALID = 0  # 无效
    VALID = 1  # 有效


class VcuBrkSts(IntEnum):
    """制动踏板状态 (VCU_BrkSts)."""

    INVALID = 0  # 无效
    VALID = 1  # 有效


class VcuAbsWorkSts(IntEnum):
    """ABS 工作状态 (VCU_ABSWorkSts)."""

    INACTIVE = 0  # 未激活
    ACTIVE = 1  # 激活
    IGNORE = 2  # 忽略
    RESERVED = 3  # 预留


# ==============================================================================
# MCU 故障代码表 (对应《DFAC 控制器故障代码-AMB2(2).xlsx》DEF 三列)
# D: DTC含义 (meaning)
# E: DisplayCode 仪表显示码 / 故障码 (code)
# F: FaultLevel 故障等级 (level)
# ==============================================================================
@dataclass(slots=True, frozen=True)
class McuFaultCodeItemDef:
    """MCU 故障码表单项定义。"""

    code: str  # DisplayCode 仪表显示码 (E列，例如 "MCU_64")
    meaning: str  # DTC 含义 (D列，例如 "VCE过流故障")
    level: str  # 故障等级 (F列，例如 "三级 (Fault)")
    raw_code: int  # 对应 CAN 信号 MCU_FltCode 报文传输数值


MCU_FAULT_CODES: list[McuFaultCodeItemDef] = [
    McuFaultCodeItemDef(code="MCU_64", meaning="VCE过流故障", level="三级 (Fault)", raw_code=64),
    McuFaultCodeItemDef(
        code="MCU_79", meaning="相电流值零漂故障", level="三级 (Fault)", raw_code=79
    ),
    McuFaultCodeItemDef(
        code="MCU_85", meaning="相电流值零漂故障", level="三级 (Fault)", raw_code=85
    ),
    McuFaultCodeItemDef(
        code="MCU_170", meaning="HVDC软件过压故障", level="三级 (Fault)", raw_code=170
    ),
    McuFaultCodeItemDef(code="MCU_135", meaning="HVDC欠压故障", level="三级 (Fault)", raw_code=135),
    McuFaultCodeItemDef(
        code="MCU_88", meaning="低压蓄电池过压故障", level="三级 (Fault)", raw_code=88
    ),
    McuFaultCodeItemDef(
        code="MCU_89", meaning="低压蓄电池欠压故障", level="三级 (Fault)", raw_code=89
    ),
    McuFaultCodeItemDef(
        code="MCU_73",
        meaning="IGBT模块温度检测电路输出电压高(断路)",
        level="二级 (Limp)",
        raw_code=73,
    ),
    McuFaultCodeItemDef(
        code="MCU_74",
        meaning="IGBT模块温度检测电路输出电压低(短路)",
        level="二级 (Limp)",
        raw_code=74,
    ),
    McuFaultCodeItemDef(
        code="MCU_72", meaning="IGBT采样温度过温故障", level="二级 (Limp)", raw_code=72
    ),
    McuFaultCodeItemDef(
        code="MCU_11", meaning="IGBT采样温度降额", level="二级 (Derat)", raw_code=11
    ),
    McuFaultCodeItemDef(
        code="MCU_106",
        meaning="电机定子温度传感器1电路输出电压低(短路)",
        level="二级 (Limp)",
        raw_code=106,
    ),
    McuFaultCodeItemDef(
        code="MCU_105",
        meaning="电机定子温度传感器1电路输出电压高(断路)",
        level="二级 (Limp)",
        raw_code=105,
    ),
    McuFaultCodeItemDef(
        code="MCU_31", meaning="L2电机定子温度过温", level="三级 (Fault)", raw_code=31
    ),
    McuFaultCodeItemDef(code="MCU_7", meaning="电机定子温度降额", level="二级 (Derat)", raw_code=7),
    McuFaultCodeItemDef(
        code="MCU_46", meaning="VCU节点丢失故障", level="三级 (Fault)", raw_code=46
    ),
    McuFaultCodeItemDef(code="MCU_104", meaning="电机超速故障", level="三级 (Fault)", raw_code=104),
    McuFaultCodeItemDef(
        code="MCU_144", meaning="控制器堵转过载降额", level="二级 (Derat)", raw_code=144
    ),
    McuFaultCodeItemDef(code="MCU_103", meaning="输出缺相故障", level="三级 (Fault)", raw_code=103),
    McuFaultCodeItemDef(
        code="MCU_139", meaning="HVDC过压降额故障", level="二级 (Derat)", raw_code=139
    ),
    McuFaultCodeItemDef(
        code="MCU_140", meaning="HVDC欠压降额故障", level="二级 (Derat)", raw_code=140
    ),
    McuFaultCodeItemDef(code="MCU_142", meaning="超速降额故障", level="二级 (Derat)", raw_code=142),
]

# 按 CAN 原始故障码数值索引的映射表
MCU_FAULT_MAP: dict[int, McuFaultCodeItemDef] = {item.raw_code: item for item in MCU_FAULT_CODES}
