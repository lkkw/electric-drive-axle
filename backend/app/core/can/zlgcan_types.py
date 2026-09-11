"""Ctypes data structures and definitions for ZLG CAN (64-bit Windows).

Matches ZLG zlgcan.dll x64 ABI specifications.
"""

from ctypes import (
    POINTER,
    Structure,
    Union,
    c_ubyte,
    c_uint,
    c_ulonglong,
    c_ushort,
)

# ==============================================================================
# 状态常量与句柄定义
# ==============================================================================
ZCAN_STATUS_OK: int = 1
ZCAN_STATUS_ERR: int = 0
INVALID_DEVICE_HANDLE: int = 0
INVALID_CHANNEL_HANDLE: int = 0

ZCAN_TYPE_CAN: int = 0
ZCAN_TYPE_CANFD: int = 1


class ZCAN_DEVICE_INFO(Structure):
    """ZLG 设备信息结构体。"""

    _fields_ = [
        ("hw_Version", c_ushort),
        ("fw_Version", c_ushort),
        ("dr_Version", c_ushort),
        ("in_Version", c_ushort),
        ("irq_Num", c_ushort),
        ("can_Num", c_ubyte),
        ("str_Serial_Num", c_ubyte * 20),
        ("str_hw_Type", c_ubyte * 40),
        ("reserved", c_ushort * 4),
    ]

    @property
    def serial(self) -> str:
        """获取序列号字符串。"""
        return bytes(self.str_Serial_Num).decode("latin-1", errors="replace").split("\x00", 1)[0]

    @property
    def hw_type(self) -> str:
        """获取硬件型号字符串。"""
        return bytes(self.str_hw_Type).decode("latin-1", errors="replace").split("\x00", 1)[0]


class _ZCAN_CHANNEL_CAN_INIT_CONFIG(Structure):
    """标准 CAN 通道初始化参数配置。"""

    _fields_ = [
        ("acc_code", c_uint),
        ("acc_mask", c_uint),
        ("reserved", c_uint),
        ("filter", c_ubyte),
        ("timing0", c_ubyte),
        ("timing1", c_ubyte),
        ("mode", c_ubyte),  # 0 为正常模式，1 为只听模式
    ]


class _ZCAN_CHANNEL_CANFD_INIT_CONFIG(Structure):
    """CANFD 通道初始化参数配置。"""

    _fields_ = [
        ("acc_code", c_uint),
        ("acc_mask", c_uint),
        ("abit_timing", c_uint),
        ("dbit_timing", c_uint),
        ("brp", c_uint),
        ("filter", c_ubyte),
        ("mode", c_ubyte),
        ("pad", c_ushort),
        ("reserved", c_uint),
    ]


class _ZCAN_CHANNEL_INIT_CONFIG(Union):
    """通道配置联合体。"""

    _fields_ = [
        ("can", _ZCAN_CHANNEL_CAN_INIT_CONFIG),
        ("canfd", _ZCAN_CHANNEL_CANFD_INIT_CONFIG),
    ]


class ZCAN_CHANNEL_INIT_CONFIG(Structure):
    """通道初始化配置顶层结构体。"""

    _fields_ = [
        ("can_type", c_uint),
        ("config", _ZCAN_CHANNEL_INIT_CONFIG),
    ]


class ZCAN_CHANNEL_ERR_INFO(Structure):
    """通道错误信息。"""

    _fields_ = [
        ("error_code", c_uint),
        ("passive_ErrData", c_ubyte * 3),
        ("arLost_ErrData", c_ubyte),
    ]


class ZCAN_CAN_FRAME(Structure):
    """标准 CAN 2.0B 报文帧。"""

    _fields_ = [
        ("can_id", c_uint, 29),  # 29 位标识符 (标准帧只占低 11 位)
        ("err", c_uint, 1),  # 错误帧标志
        ("rtr", c_uint, 1),  # 远程帧标志 (0: 数据帧, 1: 远程帧)
        ("eff", c_uint, 1),  # 扩展帧标志 (0: 标准帧, 1: 扩展帧)
        ("can_dlc", c_ubyte),  # 数据长度 (0-8)
        ("__pad", c_ubyte),
        ("__res0", c_ubyte),
        ("__res1", c_ubyte),
        ("data", c_ubyte * 8),  # 报文有效载荷
    ]


class ZCAN_Transmit_Data(Structure):
    """CAN 发送数据单元。"""

    _fields_ = [
        ("frame", ZCAN_CAN_FRAME),
        ("transmit_type", c_uint),  # 0: 正常发送, 1: 单次发送, 2: 自发自收
    ]


class ZCAN_Receive_Data(Structure):
    """CAN 接收数据单元。"""

    _fields_ = [
        ("frame", ZCAN_CAN_FRAME),
        ("timestamp", c_ulonglong),  # 硬件接收微秒级时间戳
    ]


P_ZCAN_CHANNEL_INIT_CONFIG = POINTER(ZCAN_CHANNEL_INIT_CONFIG)
P_ZCAN_Transmit_Data = POINTER(ZCAN_Transmit_Data)
P_ZCAN_Receive_Data = POINTER(ZCAN_Receive_Data)
P_ZCAN_DEVICE_INFO = POINTER(ZCAN_DEVICE_INFO)
P_ZCAN_CHANNEL_ERR_INFO = POINTER(ZCAN_CHANNEL_ERR_INFO)
