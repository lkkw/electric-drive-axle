"""Unit tests for Electric Drive Axle CAN bitwise encoder and decoder."""

import pytest

from app.core.can.codec import (
    decode_mcu_motor_1,
    decode_mcu_motor_2,
    decode_mcu_tbox_motor,
    encode_vcu_11,
)
from app.core.can.constants import (
    McuActiveDischargeStatus,
    McuFaultLevel,
    McuMotorWorkMode,
    McuTboxFaultLevel,
    MotorState,
    VcuActiveDischarge,
    VcuGearStatus,
    VcuMcuEnCmd,
    VcuWorkModeReq,
)


def test_encode_vcu_11_zero_setpoints() -> None:
    """测试 VCU_11 零位默认状态编码。"""
    payload = encode_vcu_11(
        torque_req=0.0,
        speed_req=0,
        work_mode_req=VcuWorkModeReq.CLOSE,
        mcu_en_cmd=VcuMcuEnCmd.DISABLE,
        gear_sts=VcuGearStatus.N,
        active_discharge=VcuActiveDischarge.INACTIVE,
        life=0,
    )

    assert len(payload) == 8
    # 0.0 Nm -> raw = (0.0 + 3000.0) / 0.1 = 30000 = 0x7530
    assert payload[0] == 0x75
    assert payload[1] == 0x30

    # 0 rpm -> raw = 0 + 12000 = 12000 = 0x2EE0
    assert payload[2] == 0x2E
    assert payload[3] == 0xE0

    # 保留位 Byte 4, 5
    assert payload[4] == 0x00
    assert payload[5] == 0x00

    # Byte 6: mode=0, en=0
    assert payload[6] == 0x00

    # Byte 7: gear=N(3), dischg=0, life=0 -> (0<<4) | (0<<3) | 3 = 0x03
    assert payload[7] == 0x03


def test_encode_vcu_11_active_drive_setpoints() -> None:
    """测试 VCU_11 动力驱动工况编码。"""
    # 设定: 转矩 +150.0 Nm, 转速 +2500 RPM, 使能=1, 模式=转矩模式(1), 挂 D 挡(1), 放电=0, life=9
    payload = encode_vcu_11(
        torque_req=150.0,
        speed_req=2500,
        work_mode_req=VcuWorkModeReq.TORQUE,
        mcu_en_cmd=VcuMcuEnCmd.ENABLE,
        gear_sts=VcuGearStatus.D,
        active_discharge=VcuActiveDischarge.INACTIVE,
        life=9,
    )

    # raw_tq = (150.0 + 3000.0) / 0.1 = 31500 = 0x7B0C
    assert payload[0] == 0x7B
    assert payload[1] == 0x0C

    # raw_spd = 2500 + 12000 = 14500 = 0x38A4
    assert payload[2] == 0x38
    assert payload[3] == 0xA4

    # Byte 6: mode=1 (bits 0..2), en=1 (bit 3) -> (1 << 3) | 1 = 0x09
    assert payload[6] == 0x09

    # Byte 7: gear=1 (bits 0..2), dischg=0 (bit 3), life=9 (bits 4..7)
    # 1 | (0 << 3) | (9 << 4) = 1 | 0x90 = 0x91
    assert payload[7] == 0x91


def test_encode_vcu_11_boundary_clamping() -> None:
    """测试超出物理范围时的限幅保护。"""
    # 传入超上限与超下限数值
    payload = encode_vcu_11(
        torque_req=9999.0,
        speed_req=-99999,
        work_mode_req=15,  # 溢出掩码
        mcu_en_cmd=5,
        gear_sts=15,
        active_discharge=3,
        life=31,
    )

    # 转矩限幅为 3000.0 Nm -> raw = 60000 = 0xEA60
    assert (payload[0] << 8) | payload[1] == 0xEA60

    # 转速限幅为 -12000 RPM -> raw = 0 = 0x0000
    assert (payload[2] << 8) | payload[3] == 0x0000

    # 掩码测试: mode 只取低 3 位 (15 & 7 = 7), en 只取低 1 位 (5 & 1 = 1) -> (1<<3)|7 = 0x0F
    assert payload[6] == 0x0F


def test_decode_mcu_motor_1() -> None:
    """测试 MCU_Drive_motor_1 (0x35A) 解码。"""
    # 构造原始报文:
    # 电压 540.5 V -> raw = 5405 = 0x151D
    # 电流 +125.4 A -> raw = (125.4 + 1000) / 0.1 = 11254 = 0x2BF6
    # 故障个数 2, 故障代码 10
    # Byte 6: flt_levl = 2 (bits 0..2), life_1 = 5 (bits 3..6) -> 2 | (5 << 3) = 2 | 40 = 42 = 0x2A
    # Byte 7: tbox_flt_levl = 1 (bits 0..1) -> 0x01
    raw_data = bytes(
        [
            0x15,
            0x1D,  # Volt: 540.5 V
            0x2B,
            0xF6,  # Curr: 125.4 A
            0x02,  # Fault Num: 2
            0x0A,  # Fault Code: 10
            0x2A,  # flt_levl: 2, life_1: 5
            0x01,  # tbox_flt_levl: 1
        ]
    )

    decoded = decode_mcu_motor_1(raw_data)
    assert decoded.mcu_dc_main_wire_volt == 540.5
    assert decoded.mcu_dc_main_wire_curr == 125.4
    assert decoded.mcu_integ_ctr_flt_num == 2
    assert decoded.mcu_flt_code == 10
    assert decoded.mcu_flt_levl == McuFaultLevel.LEVEL_2
    assert decoded.mcu_life_1 == 5
    assert decoded.mcu_tbox_flt_levl == McuTboxFaultLevel.LEVEL_1


def test_decode_mcu_motor_2() -> None:
    """测试 MCU_Drive_motor_2 (0x35B) 解码。"""
    # 构造原始报文:
    # 最大转矩 450.0 Nm -> raw = (450.0 + 3000) / 0.1 = 34500 = 0x86C4
    # 实际转速 3200 RPM -> raw = 3200 + 12000 = 15200 = 0x3B60
    # 实际转矩 180.5 Nm -> raw = (180.5 + 3000) / 0.1 = 31805 = 0x7C3D
    # Byte 6:
    #   active_dischg = 1 (bits 0..1)
    #   work_mod = 1 (bits 2..4 -> 1 << 2 = 4)
    #   lv_sts = 1 (bit 5 -> 1 << 5 = 32)
    #   en_sts = 1 (bit 6 -> 1 << 6 = 64)
    #   motor_temp_over = 0 (bit 7)
    #   byte6 = 1 | 4 | 32 | 64 = 101 = 0x65
    # Byte 7:
    #   mcu_temp_over = 0 (bit 0)
    #   life_2 = 7 (bits 2..5 -> 7 << 2 = 28 = 0x1C)
    #   byte7 = 0x1C
    raw_data = bytes(
        [
            0x86,
            0xC4,
            0x3B,
            0x60,
            0x7C,
            0x3D,
            0x65,
            0x1C,
        ]
    )

    decoded = decode_mcu_motor_2(raw_data)
    assert decoded.mcu_motor_tor_max == 450.0
    assert decoded.mcu_act_motor_spd == 3200
    assert decoded.mcu_act_motor_tq == 180.5
    assert decoded.mcu_active_dischrg_sts == McuActiveDischargeStatus.FINISHED
    assert decoded.mcu_motor_work_mod == McuMotorWorkMode.TORQUE
    assert decoded.mcu_lv_sts == 1
    assert decoded.mcu_en_sts == 1
    assert decoded.mcu_motor_temp_extre_over == 0
    assert decoded.mcu_mcu_temp_extre_over == 0
    assert decoded.mcu_life_2 == 7


def test_decode_mcu_tbox_motor() -> None:
    """测试 MCU_Tbox_Drive_motor (0x35C) 解码。"""
    # 构造原始报文:
    # num_mtr = 1, num_mtr_srl = 1
    # st_mtr = 1 (耗电)
    # motor_temp = 72 ℃ -> raw = 72 + 40 = 112 = 0x70
    # ctller_temp = 55 ℃ -> raw = 55 + 40 = 95 = 0x5F
    # tbox_life = 11 -> byte7 = 11 = 0x0B
    raw_data = bytes(
        [
            0x01,  # num_mtr
            0x01,  # num_mtr_srl
            0x01,  # st_mtr: 1 (耗电)
            0x00,  # res
            0x00,  # res
            0x70,  # motor_temp: 112 - 40 = 72
            0x5F,  # ctller_temp: 95 - 40 = 55
            0x0B,  # tbox_life: 11
        ]
    )

    decoded = decode_mcu_tbox_motor(raw_data)
    assert decoded.num_mtr == 1
    assert decoded.num_mtr_srl == 1
    assert decoded.st_mtr == MotorState.CONSUMING
    assert decoded.mcu_motor_temp == 72
    assert decoded.mcu_ctller_temp == 55
    assert decoded.mcu_tbox_life == 11


def test_decode_length_validation() -> None:
    """测试当数据长度不足 8 字节时抛出 ValueError。"""
    short_data = bytes([0x01, 0x02, 0x03])
    with pytest.raises(ValueError, match="数据长度不足 8 字节"):
        decode_mcu_motor_1(short_data)

    with pytest.raises(ValueError, match="数据长度不足 8 字节"):
        decode_mcu_motor_2(short_data)

    with pytest.raises(ValueError, match="数据长度不足 8 字节"):
        decode_mcu_tbox_motor(short_data)


def test_encode_vcu_11_acc_brake_abs() -> None:
    """测试 VCU_11 加速踏板开度、手刹、制动与 ABS 标志位编码。"""
    payload = encode_vcu_11(
        torque_req=200.0,
        speed_req=1000,
        acc_position=50.0,  # 50.0% -> raw = 500 = 0x01F4
        work_mode_req=VcuWorkModeReq.TORQUE,  # 1
        mcu_en_cmd=VcuMcuEnCmd.ENABLE,  # 1
        hand_brk_sts=1,  # 1 -> bit 4
        brk_sts=1,  # 1 -> bit 5
        abs_work_sts=2,  # 2 (忽略) -> bits 6..7
        gear_sts=VcuGearStatus.D,  # 1
        active_discharge=0,
        life=3,
    )

    # raw_acc = 500 = 0x01F4
    assert payload[4] == 0x01
    assert payload[5] == 0xF4

    # Byte 6: 1 (mode) | (1<<3) | (1<<4) | (1<<5) | (2<<6) = 1 | 8 | 16 | 32 | 128 = 185 = 0xB9
    assert payload[6] == 0xB9

    # Byte 7: 1 (gear) | (0<<3) | (3<<4) = 1 | 48 = 49 = 0x31
    assert payload[7] == 0x31


def test_decode_mcu_motor_2_slope_sts() -> None:
    """测试 MCU_Drive_motor_2 (0x35B) 驻坡状态反馈解码。"""
    # Byte 7:
    # bit 0: mcu_temp_over = 0
    # bit 1: mcm_slope_sts = 1 (驻坡) -> 1 << 1 = 2
    # bit 2..5: life_2 = 4 -> 4 << 2 = 16
    # byte7 = 2 | 16 = 18 = 0x12
    raw_data = bytes([0x75, 0x30, 0x2E, 0xE0, 0x75, 0x30, 0x00, 0x12])
    decoded = decode_mcu_motor_2(raw_data)
    assert decoded.mcm_slope_sts == 1
    assert decoded.mcu_life_2 == 4

    # 测试未驻坡 (bit 1 = 0)
    raw_data_no_slope = bytes([0x75, 0x30, 0x2E, 0xE0, 0x75, 0x30, 0x00, 0x10])
    decoded_no_slope = decode_mcu_motor_2(raw_data_no_slope)
    assert decoded_no_slope.mcm_slope_sts == 0


def test_mcu_fault_codes_completeness() -> None:
    """测试 MCU 故障代码表 (DEF 三列) 包含全部 22 个定义项且映射唯一。"""
    from app.core.can.constants import MCU_FAULT_CODES, MCU_FAULT_MAP

    assert len(MCU_FAULT_CODES) == 22
    assert len(MCU_FAULT_MAP) == 22

    # 验证关键故障码
    assert MCU_FAULT_MAP[64].code == "MCU_64"
    assert MCU_FAULT_MAP[64].meaning == "VCE过流故障"
    assert "三级" in MCU_FAULT_MAP[64].level

    assert MCU_FAULT_MAP[170].code == "MCU_170"
    assert MCU_FAULT_MAP[170].meaning == "HVDC软件过压故障"

    assert MCU_FAULT_MAP[11].code == "MCU_11"
    assert MCU_FAULT_MAP[11].meaning == "IGBT采样温度降额"
    assert "二级" in MCU_FAULT_MAP[11].level
