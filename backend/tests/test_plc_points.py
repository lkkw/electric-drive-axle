"""DB40（dbPC）点表编解码（与 magmit《高机点表(3)》一致）。"""

import struct

import pytest

from app.core.plc.points import (
    POWER_ON_BLOCK_SIZE,
    STATION_BASE,
    STATION_BLOCK_SIZE,
    build_mes_block,
    build_power_on_block,
    decode_station,
    set_bit,
)


def test_station_one_uses_base_zero() -> None:
    assert STATION_BASE == 0
    assert STATION_BLOCK_SIZE == 124


@pytest.mark.parametrize("heart", [0, 1])
def test_power_on_block_layout(heart: int) -> None:
    # 字节 0 其余位（未定义）为 1，验证会被清零，只保留心跳位
    block = build_power_on_block(0b1111_1100 | heart)

    assert len(block) == POWER_ON_BLOCK_SIZE == 14
    assert block[0] == (heart | 0b10)  # 保留心跳，Request_power=1
    assert struct.unpack_from(">h", block, 2)[0] == 1  # Put_ProductType
    assert struct.unpack_from(">h", block, 4)[0] == 340  # Request_voltage
    assert struct.unpack_from(">h", block, 6)[0] == 0  # Result
    assert block[8:14] == bytes(6)  # 点表未定义



def test_mes_block_layout() -> None:
    block = build_mes_block(-1500.0, 65.5)
    assert len(block) == 8
    assert struct.unpack(">ff", block) == (-1500.0, 65.5)  # Speed +14、Temp +18

def test_decode_station_reads_all_points() -> None:
    block = bytearray(STATION_BLOCK_SIZE)
    block[0] = 0b11  # Heart=1, Request_power=1
    struct.pack_into(">h", block, 2, 1)
    struct.pack_into(">h", block, 4, 340)
    struct.pack_into(">ff", block, 14, 1500.0, 65.5)
    block[62] = 0b1111  # Heart, Safe, Power_on, Connect
    struct.pack_into(">h", block, 64, 1)
    struct.pack_into(">h", block, 66, 281)
    struct.pack_into(">h", block, 68, -12)
    sn = b"ZC25T-0001"
    block[92] = 30
    block[93] = len(sn)
    block[94 : 94 + len(sn)] = sn

    fb = decode_station(block)
    assert fb.pc_heart and fb.request_power
    assert fb.put_product_type == 1 and fb.request_voltage == 340
    assert fb.speed == 1500.0 and fb.temp == 65.5
    assert fb.plc_heart and fb.safe and fb.power_on and fb.connect
    assert fb.get_product_type == 1
    assert fb.out_voltage == 281
    assert fb.out_current == -12  # INT 为有符号
    assert fb.serial_number == "ZC25T-0001"
    assert fb.supply_active


def test_decode_station_rejects_short_block() -> None:
    with pytest.raises(ValueError, match="124"):
        decode_station(bytearray(100))


def test_set_bit() -> None:
    assert set_bit(0b0000, 1, True) == 0b0010
    assert set_bit(0b1111, 1, False) == 0b1101
    assert set_bit(0xFF, 7, False) == 0x7F
