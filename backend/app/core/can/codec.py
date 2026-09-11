"""Pure Python CAN bitwise encoder and decoder for Electric Drive Axle.

Strictly follows:
- DBC: 东风无人车.dbc
- Communication Matrix: DFAC_Matrix_11898_CAN_台架_V0.9-0130_MCU(1).xlsx

Endianness:
- All signals follow Motorola LSB (大端高位在前，低位在后)
"""

from dataclasses import dataclass


def clamp_val(val: float | int, min_val: float | int, max_val: float | int) -> float | int:
    """限制数值在 [min_val, max_val] 区间内，防止溢出。"""
    return max(min_val, min(val, max_val))


@dataclass(slots=True, frozen=True)
class McuDriveMotor1Data:
    """MCU_Drive_motor_1 (0x35A, 周期 100ms) 解码数据结构。

    母线高压、电流及整车控制器故障诊断报文。
    """

    mcu_dc_main_wire_volt: float  # MCU母线电压 (V), 分辨率 0.1, 范围 [0, 1000]
    mcu_dc_main_wire_curr: float  # MCU母线电流 (A), 分辨率 0.1, 偏移 -1000, 范围 [-1000, 1000]
    mcu_integ_ctr_flt_num: int  # MCU故障个数, 范围 [0, 250]
    mcu_flt_code: int  # MCU故障代码, 范围 [0, 250]
    mcu_flt_levl: int  # MCU故障等级 (0: 无故障, 1~4: 一至四级故障)
    mcu_life_1: int  # MCU_Life_1 循环计数器 [0, 15]
    mcu_tbox_flt_levl: int  # MCU温度故障等级 (0: 正常, 1: 一级, 2: 二级限功, 3: 三级下高压)


@dataclass(slots=True, frozen=True)
class McuDriveMotor2Data:
    """MCU_Drive_motor_2 (0x35B, 周期 10ms) 解码数据结构。

    电驱桥动力反馈核心高频报文（转速、转矩、状态）。
    """

    mcu_motor_tor_max: float  # 电机最大可用转矩 (Nm), 分辨率 0.1, 偏移 -3000, 范围 [-3000, 3000]
    mcu_act_motor_spd: int  # 电机实际转速 (RPM), 分辨率 1, 偏移 -12000, 范围 [-12000, 12000]
    mcu_act_motor_tq: float  # 电机实际转矩 (Nm), 分辨率 0.1, 偏移 -3000, 范围 [-3000, 3000]
    mcu_active_dischrg_sts: int  # 主动放电状态 (0: 放电中, 1: 完成, 2: 失败, 3: 无效)
    mcu_motor_work_mod: int  # 电机工作模式反馈 (0: 无操作, 1: 转矩模式, 3: 转速模式...)
    mcu_lv_sts: int  # MCU低压上电状态 (0: 无效, 1: 有效)
    mcu_en_sts: int  # MCU使能状态 (0: 未使能, 1: 已使能)
    mcu_motor_temp_extre_over: int  # 驱动电机过温故障 (0: 正常, 1: 故障)
    mcu_mcu_temp_extre_over: int  # MCU控制器过温故障 (0: 正常, 1: 故障)
    mcu_life_2: int  # MCU_Life_2 循环计数器 [0, 15]


@dataclass(slots=True, frozen=True)
class McuTboxDriveMotorData:
    """MCU_Tbox_Drive_motor (0x35C, 周期 100ms) 解码数据结构。

    电机本体及控制器温度、电机状态信息。
    """

    num_mtr: int  # 驱动电机个数
    num_mtr_srl: int  # 驱动电机序号
    st_mtr: int  # 驱动电机状态 (1: 耗电, 2: 发电, 3: 关闭, 4: 准备, 255: 无效)
    mcu_motor_temp: int  # 驱动电机温度 (℃), 分辨率 1, 偏移 -40, 范围 [-40, 210]
    mcu_ctller_temp: int  # MCU控制器温度 (℃), 分辨率 1, 偏移 -40, 范围 [-40, 210]
    mcu_tbox_life: int  # MCU_Tbox_Life 循环计数器 [0, 15]


# ==============================================================================
# 编码函数: VCU_11 (上位机发送给 MCU)
# ==============================================================================
def encode_vcu_11(
    *,
    torque_req: float = 0.0,
    speed_req: int = 0,
    work_mode_req: int = 1,
    mcu_en_cmd: int = 0,
    gear_sts: int = 3,
    active_discharge: int = 0,
    life: int = 0,
) -> bytes:
    """将上位机控制信号编码为 8 字节 CAN 报文载荷 (VCU_11, ID 0x314)。

    位映射说明 (Motorola LSB 格式):
    - Byte 0..1: VCU_MotorTorReq (16 bit)
        物理值范围 [-3000.0, 3000.0] Nm，精度 0.1，偏移量 -3000.0
        Raw = round((Torque + 3000.0) / 0.1)
        Byte 0 为高 8 位 (MSB)，Byte 1 为低 8 位 (LSB)
    - Byte 2..3: VCU_MotorSpdReq (16 bit)
        物理值范围 [-12000, 12000] RPM，精度 1，偏移量 -12000
        Raw = Speed + 12000
        Byte 2 为高 8 位 (MSB)，Byte 3 为低 8 位 (LSB)
    - Byte 4..5: 保留未分配 (0x00, 0x00)
    - Byte 6:
        Bit 0..2 (3 bit): VCU_MotorWorkModReq (模式控制: 0~7)
        Bit 3 (1 bit): VCU_MCUEnCmd (使能命令: 0=未使能, 1=使能)
        Bit 4..7: 保留 (0)
    - Byte 7:
        Bit 0..2 (3 bit): VCU_GearSts (档位状态: 1=D, 2=R, 3=N, 4=L, 5=P)
        Bit 3 (1 bit): VCU_ActiveDischg (主动放电: 0=无效, 1=有效)
        Bit 4..7 (4 bit): VCU_Life (循环计数器: 0~15)
    """
    # 1. 转矩原始值计算与范围限制
    clamped_tq = float(clamp_val(torque_req, -3000.0, 3000.0))
    raw_tq = int(round((clamped_tq + 3000.0) / 0.1))
    raw_tq = int(clamp_val(raw_tq, 0, 65535))

    # 2. 转速原始值计算与范围限制
    clamped_spd = int(clamp_val(speed_req, -12000, 12000))
    raw_spd = clamped_spd + 12000
    raw_spd = int(clamp_val(raw_spd, 0, 65535))

    # 3. 模式与使能位组合 (Byte 6)
    mode_val = int(work_mode_req) & 0x07
    en_val = (int(mcu_en_cmd) & 0x01) << 3
    byte6 = mode_val | en_val

    # 4. 档位、放电与生命计数器组合 (Byte 7)
    gear_val = int(gear_sts) & 0x07
    dischg_val = (int(active_discharge) & 0x01) << 3
    life_val = (int(life) & 0x0F) << 4
    byte7 = gear_val | dischg_val | life_val

    payload = bytearray(8)
    payload[0] = (raw_tq >> 8) & 0xFF
    payload[1] = raw_tq & 0xFF
    payload[2] = (raw_spd >> 8) & 0xFF
    payload[3] = raw_spd & 0xFF
    payload[4] = 0x00
    payload[5] = 0x00
    payload[6] = byte6
    payload[7] = byte7

    return bytes(payload)


# ==============================================================================
# 解码函数: MCU_Drive_motor_1 (ID 0x35A, 100ms)
# ==============================================================================
def decode_mcu_motor_1(data: bytes | bytearray | list[int]) -> McuDriveMotor1Data:
    """解码 MCU_Drive_motor_1 报文 (0x35A)。"""
    if len(data) < 8:
        raise ValueError(f"MCU_Drive_motor_1 数据长度不足 8 字节: 实际 {len(data)}")

    # Byte 0..1: 母线电压 (16 bit, res 0.1, offset 0)
    raw_volt = (data[0] << 8) | data[1]
    volt = round(raw_volt * 0.1, 1)

    # Byte 2..3: 母线电流 (16 bit, res 0.1, offset -1000)
    raw_curr = (data[2] << 8) | data[3]
    curr = round(raw_curr * 0.1 - 1000.0, 1)

    # Byte 4: 故障个数
    integ_flt_num = data[4]

    # Byte 5: 故障代码
    flt_code = data[5]

    # Byte 6: 故障等级 (bits 0..2), Life_1 (bits 3..6)
    flt_levl = data[6] & 0x07
    life_1 = (data[6] >> 3) & 0x0F

    # Byte 7: TBOX故障等级 (bits 0..1)
    tbox_flt_levl = data[7] & 0x03

    return McuDriveMotor1Data(
        mcu_dc_main_wire_volt=volt,
        mcu_dc_main_wire_curr=curr,
        mcu_integ_ctr_flt_num=integ_flt_num,
        mcu_flt_code=flt_code,
        mcu_flt_levl=flt_levl,
        mcu_life_1=life_1,
        mcu_tbox_flt_levl=tbox_flt_levl,
    )


# ==============================================================================
# 解码函数: MCU_Drive_motor_2 (ID 0x35B, 10ms)
# ==============================================================================
def decode_mcu_motor_2(data: bytes | bytearray | list[int]) -> McuDriveMotor2Data:
    """解码 MCU_Drive_motor_2 报文 (0x35B)。"""
    if len(data) < 8:
        raise ValueError(f"MCU_Drive_motor_2 数据长度不足 8 字节: 实际 {len(data)}")

    # Byte 0..1: 电机最大可用转矩 (16 bit, res 0.1, offset -3000)
    raw_tor_max = (data[0] << 8) | data[1]
    tor_max = round(raw_tor_max * 0.1 - 3000.0, 1)

    # Byte 2..3: 电机转速 (16 bit, res 1, offset -12000)
    raw_spd = (data[2] << 8) | data[3]
    spd = raw_spd - 12000

    # Byte 4..5: 电机实际转矩 (16 bit, res 0.1, offset -3000)
    raw_act_tq = (data[4] << 8) | data[5]
    act_tq = round(raw_act_tq * 0.1 - 3000.0, 1)

    # Byte 6: 状态标志位解析
    # bit 0..1: 主动放电状态 (MCU_ActiveDischrgSts)
    active_dischg_sts = data[6] & 0x03
    # bit 2..4: 电机工作模式反馈 (MCU_MotorWorkMod)
    work_mod = (data[6] >> 2) & 0x07
    # bit 5: MCU低压上电状态 (MCU_LVSts)
    lv_sts = (data[6] >> 5) & 0x01
    # bit 6: MCU使能状态 (MCU_EnSts)
    en_sts = (data[6] >> 6) & 0x01
    # bit 7: 驱动电机过温故障 (MCU_MotorTempExtreOver)
    motor_temp_over = (data[6] >> 7) & 0x01

    # Byte 7:
    # bit 0: MCU过温故障 (MCU_MCUTempExtreOver)
    mcu_temp_over = data[7] & 0x01
    # bit 2..5: MCU_Life_2 循环计数器
    life_2 = (data[7] >> 2) & 0x0F

    return McuDriveMotor2Data(
        mcu_motor_tor_max=tor_max,
        mcu_act_motor_spd=spd,
        mcu_act_motor_tq=act_tq,
        mcu_active_dischrg_sts=active_dischg_sts,
        mcu_motor_work_mod=work_mod,
        mcu_lv_sts=lv_sts,
        mcu_en_sts=en_sts,
        mcu_motor_temp_extre_over=motor_temp_over,
        mcu_mcu_temp_extre_over=mcu_temp_over,
        mcu_life_2=life_2,
    )


# ==============================================================================
# 解码函数: MCU_Tbox_Drive_motor (ID 0x35C, 100ms)
# ==============================================================================
def decode_mcu_tbox_motor(data: bytes | bytearray | list[int]) -> McuTboxDriveMotorData:
    """解码 MCU_Tbox_Drive_motor 报文 (0x35C)。"""
    if len(data) < 8:
        raise ValueError(f"MCU_Tbox_Drive_motor 数据长度不足 8 字节: 实际 {len(data)}")

    # Byte 0: 驱动电机个数
    num_mtr = data[0]

    # Byte 1: 驱动电机序号
    num_mtr_srl = data[1]

    # Byte 2: 驱动电机状态 (stMtr)
    st_mtr = data[2]

    # Byte 3..4: 保留

    # Byte 5: 驱动电机温度 (8 bit, res 1, offset -40)
    motor_temp = data[5] - 40

    # Byte 6: MCU控制器温度 (8 bit, res 1, offset -40)
    ctller_temp = data[6] - 40

    # Byte 7: bits 0..3: MCU_Tbox_Life
    tbox_life = data[7] & 0x0F

    return McuTboxDriveMotorData(
        num_mtr=num_mtr,
        num_mtr_srl=num_mtr_srl,
        st_mtr=st_mtr,
        mcu_motor_temp=motor_temp,
        mcu_ctller_temp=ctller_temp,
        mcu_tbox_life=tbox_life,
    )
