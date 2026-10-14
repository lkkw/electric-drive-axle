"""PLC 上电控制点表（西门子 S7-1500，dbPC [DB40]）。

点表来自 PLC 工程师提供的 dbPC [DB40]：DB40 只有一个 Station（udtPC，基址 0），
共 124 字节，布局与 magmit 项目《高机点表(3)》的单个工位相同。DB40 内偏移：

- ``+0 ~ +61``  上位机 → PLC（PcToPlc 写区）
- ``+62 ~ +123`` PLC → 上位机（PlcToPc 读区）

| 方向 | 点位            | 偏移   | 类型        | 说明                                   |
|------|-----------------|--------|-------------|----------------------------------------|
| 写   | Heart           | +0.0   | BOOL        | 上位机心跳，每秒翻转                   |
| 写   | Request_power   | +0.1   | BOOL        | 1 请求上电 / 0 掉电（异常时都要复位）  |
| 写   | Put_ProductType | +2     | INT         | 交互产品编号（本台架固定 1）           |
| 写   | Request_voltage | +4     | INT         | 产品电压（本台架 340 V）               |
| 写   | Result          | +6     | INT         | 测试结果（本项目不使用，上电时清零）   |
| 写   | Speed / Temp    | +14/18 | REAL        | 实时转速 (rpm) / 电机温度 (℃)，上传 MES |
| 读   | Heart           | +62.0  | BOOL        | PLC 心跳                               |
| 读   | Safe            | +62.1  | BOOL        | 安全条件满足                           |
| 读   | Power_on        | +62.2  | BOOL        | 上电完成                               |
| 读   | Connect         | +62.3  | BOOL        | 主接触器已吸合                         |
| 读   | Get_ProductType | +64    | INT         | Put_ProductType 的回传                 |
| 读   | Out_voltage     | +66    | INT         | 电源实时输出电压 (V)                   |
| 读   | Out_current     | +68    | INT         | 电源实时输出电流（单位待 PLC 确认）    |
| 读   | Sn              | +92    | STRING[30]  | 产品序列号                             |

S7 的 INT 为 16 位有符号大端，REAL 为 32 位大端浮点，STRING 为
“最大长度 + 实际长度 + 字符”格式。
"""

import struct
from dataclasses import dataclass

DB_NUMBER = 40
STATION_NO = 1
STATION_BLOCK_SIZE = 124
STATION_BASE = (STATION_NO - 1) * STATION_BLOCK_SIZE

# 本台架只有一款控制器、一款电机
PRODUCT_TYPE_CODE = 1
TARGET_VOLTAGE_V = 340

# ── PcToPlc 写区（相对工位基址）──
OFFSET_PC_STATUS = 0
BIT_PC_HEART = 0
BIT_REQUEST_POWER = 1
OFFSET_PUT_PRODUCT_TYPE = 2
OFFSET_REQUEST_VOLTAGE = 4
OFFSET_RESULT = 6
OFFSET_SPEED = 14
OFFSET_TEMP = 18
# 上电时一次写入的控制区长度：+0 ~ +13（Heart/Request_power ~ 未定义字节）；
# Speed / Temp 由常驻监视持续上传 MES，上电时不覆盖
POWER_ON_BLOCK_SIZE = 14
MES_BLOCK_SIZE = 8

# ── PlcToPc 读区（相对工位基址）──
OFFSET_PLC_STATUS = 62
BIT_PLC_HEART = 0
BIT_SAFE = 1
BIT_POWER_ON = 2
BIT_CONNECT = 3
OFFSET_GET_PRODUCT_TYPE = 64
OFFSET_OUT_VOLTAGE = 66
OFFSET_OUT_CURRENT = 68
OFFSET_SN = 92
SN_MAX_LENGTH = 30


def _bit(byte: int, bit: int) -> bool:
    return bool(byte & (1 << bit))


def _int16(block: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from(">h", block, offset)[0]


def _real(block: bytes | bytearray, offset: int) -> float:
    return struct.unpack_from(">f", block, offset)[0]


def _s7_string(block: bytes | bytearray, offset: int, max_length: int) -> str:
    """解码 S7 STRING：首字节最大长度、次字节实际长度，之后是字符。"""
    if len(block) < offset + 2:
        return ""
    actual = min(block[offset + 1], max_length, len(block) - offset - 2)
    raw = bytes(block[offset + 2 : offset + 2 + actual])
    return raw.decode("latin-1", errors="replace").strip("\x00 ").strip()


@dataclass(frozen=True, slots=True)
class StationFeedback:
    """一次读取的 1 号工位完整状态（写区回读 + PLC 反馈）。"""

    pc_heart: bool
    request_power: bool
    put_product_type: int
    request_voltage: int
    speed: float
    temp: float
    plc_heart: bool
    safe: bool
    power_on: bool
    connect: bool
    get_product_type: int
    out_voltage: int
    out_current: int
    serial_number: str

    @property
    def supply_active(self) -> bool:
        """已请求上电、已上电或接触器吸合中的任一项成立，即视为台架处于供电相关状态。"""
        return self.request_power or self.power_on or self.connect


def decode_station(block: bytes | bytearray) -> StationFeedback:
    """把工位 124 字节解码为结构化状态。"""
    if len(block) < STATION_BLOCK_SIZE:
        raise ValueError(f"工位数据长度不足 {STATION_BLOCK_SIZE} 字节: 实际 {len(block)}")
    pc_status = block[OFFSET_PC_STATUS]
    plc_status = block[OFFSET_PLC_STATUS]
    return StationFeedback(
        pc_heart=_bit(pc_status, BIT_PC_HEART),
        request_power=_bit(pc_status, BIT_REQUEST_POWER),
        put_product_type=_int16(block, OFFSET_PUT_PRODUCT_TYPE),
        request_voltage=_int16(block, OFFSET_REQUEST_VOLTAGE),
        speed=_real(block, OFFSET_SPEED),
        temp=_real(block, OFFSET_TEMP),
        plc_heart=_bit(plc_status, BIT_PLC_HEART),
        safe=_bit(plc_status, BIT_SAFE),
        power_on=_bit(plc_status, BIT_POWER_ON),
        connect=_bit(plc_status, BIT_CONNECT),
        get_product_type=_int16(block, OFFSET_GET_PRODUCT_TYPE),
        out_voltage=_int16(block, OFFSET_OUT_VOLTAGE),
        out_current=_int16(block, OFFSET_OUT_CURRENT),
        serial_number=_s7_string(block, OFFSET_SN, SN_MAX_LENGTH),
    )


def set_bit(byte: int, bit: int, value: bool) -> int:
    """返回置位/清零指定位后的字节值。"""
    return (byte | (1 << bit)) if value else (byte & ~(1 << bit) & 0xFF)


def build_power_on_block(current_status_byte: int) -> bytearray:
    """构造上电时一次写入的 14 字节控制区（+0 ~ +13）。

    - 字节 0：保留上位机心跳位，置位 Request_power，其余未定义位清零；
    - Put_ProductType = 1，Request_voltage = 340；
    - Result、未定义字节 8~13 清零；Speed / Temp 由 MES 上传负责，不在此覆盖。
    """
    block = bytearray(POWER_ON_BLOCK_SIZE)
    block[OFFSET_PC_STATUS] = (current_status_byte & (1 << BIT_PC_HEART)) | (1 << BIT_REQUEST_POWER)
    struct.pack_into(">h", block, OFFSET_PUT_PRODUCT_TYPE, PRODUCT_TYPE_CODE)
    struct.pack_into(">h", block, OFFSET_REQUEST_VOLTAGE, TARGET_VOLTAGE_V)
    struct.pack_into(">h", block, OFFSET_RESULT, 0)
    return block


def build_mes_block(speed_rpm: float, temp_c: float) -> bytearray:
    """构造上传 MES 的 8 字节（+14 Speed、+18 Temp，均为 REAL）。"""
    block = bytearray(MES_BLOCK_SIZE)
    struct.pack_into(">ff", block, 0, speed_rpm, temp_c)
    return block
