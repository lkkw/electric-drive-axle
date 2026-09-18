"""Pydantic v2 schemas for Electric Drive Axle control and telemetry."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CanConnectRequest(BaseModel):
    """USBCAN 硬件连接请求参数。"""

    model_config = ConfigDict(extra="forbid")

    device_type: int = Field(
        default=4,
        description="周立功设备型号 (3: USBCAN1, 4: USBCAN2, 21: USBCAN_2E_U)",
    )
    device_index: int = Field(default=0, ge=0, description="设备卡索引")
    channel: int = Field(default=0, ge=-1, le=1, description="CAN 通道号")
    baud_rate: int = Field(default=500000, description="通信波特率 (bps)")


class VcuCommandUpdateRequest(BaseModel):
    """上位机 (VCU) 控制设定值更新请求。"""

    model_config = ConfigDict(extra="forbid")

    torque_req: float | None = Field(
        default=None,
        ge=-3000.0,
        le=3000.0,
        description="电机目标转矩 (Nm)，分辨率 0.1",
    )
    speed_req: int | None = Field(
        default=None,
        ge=-12000,
        le=12000,
        description="电机目标转速 (RPM)，分辨率 1",
    )
    acc_position: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="加速踏板开度 (%)，分辨率 0.1",
    )
    work_mode_req: int | None = Field(
        default=None,
        ge=0,
        le=7,
        description="电机工作模式 (1: 扭矩模式, 3: 速度模式, 0: 关闭)",
    )
    mcu_en_cmd: int | None = Field(
        default=None,
        ge=0,
        le=1,
        description="MCU 使能命令 (0: 未使能, 1: 使能)",
    )
    hand_brk_sts: int | None = Field(
        default=None,
        ge=0,
        le=1,
        description="手刹状态 (0: 无效, 1: 有效)",
    )
    brk_sts: int | None = Field(
        default=None,
        ge=0,
        le=1,
        description="制动状态 (0: 无效, 1: 有效)",
    )
    abs_work_sts: int | None = Field(
        default=None,
        ge=0,
        le=3,
        description="ABS工作状态 (0: 未激活, 1: 激活, 2: 忽略, 3: 预留)",
    )
    gear_sts: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="档位状态 (1: D, 2: R, 3: N, 4: L, 5: P)",
    )
    active_discharge: int | None = Field(
        default=None,
        ge=0,
        le=1,
        description="主动放电命令 (0: 无效, 1: 有效)",
    )


class VcuCommandState(BaseModel):
    """VCU 当前控制指令输出状态。"""

    torque_req: float = 0.0
    speed_req: int = 0
    acc_position: float = 0.0  # 加速踏板开度 (%)
    work_mode_req: int = 3  # 默认速度模式
    mcu_en_cmd: int = 0  # 默认未使能
    hand_brk_sts: int = 0  # 手刹状态 (0: 无效, 1: 有效)
    brk_sts: int = 0  # 制动状态 (0: 无效, 1: 有效)
    abs_work_sts: int = 0  # ABS状态 (0: 未激活, 1: 激活, 2: 忽略, 3: 预留)
    gear_sts: int = 3  # 默认空挡 N
    active_discharge: int = 0  # 默认不放电
    life: int = 0  # 循环计数器 (0~15)


class CycleTestStep(BaseModel):
    """后端循环测试中的单个工况步骤。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    gear: Literal[1, 2, 3]
    target_speed: int = Field(ge=-12000, le=12000)
    duration_seconds: int = Field(ge=1, le=3600)

    @model_validator(mode="after")
    def validate_gear_speed_direction(self) -> "CycleTestStep":
        """D 挡与 R 挡反转运行均应输入正转速（方向由挡位决定），N 挡只允许零转速。"""
        if self.gear == 1 and self.target_speed < 0:
            raise ValueError("D 挡目标转速不能为负数。")
        if self.gear == 2 and self.target_speed < 0:
            raise ValueError("R 挡反转运行目标转速不能为负数（由 R 挡请求控制方向，给定正转速）。")
        if self.gear == 3 and self.target_speed != 0:
            raise ValueError("N 挡目标转速必须为 0。")
        return self


class CycleTestStartRequest(BaseModel):
    """启动循环测试时提交的完整、不可变工况快照。"""

    model_config = ConfigDict(extra="forbid")

    steps: list[CycleTestStep] = Field(min_length=1, max_length=100)
    total_loops: int = Field(default=1, ge=1, le=999)

    @model_validator(mode="after")
    def validate_direction_changes_have_neutral_buffer(self) -> "CycleTestStartRequest":
        """正反转切换必须经过独立 N 挡步骤，包括跨圈边界。"""
        adjacent_pairs = list(zip(self.steps, self.steps[1:], strict=False))
        if self.total_loops > 1 and len(self.steps) > 1:
            adjacent_pairs.append((self.steps[-1], self.steps[0]))
        for previous, current in adjacent_pairs:
            if {previous.gear, current.gear} == {1, 2}:
                raise ValueError("正反转切换之间必须配置 N 挡缓冲步骤。")
        return self


class CycleTestStatus(BaseModel):
    """由后端维护并通过 REST/SSE 对外发布的循环测试状态。"""

    status: Literal["idle", "running", "paused", "stopped", "completed", "error"] = "idle"
    control_owner: Literal["none", "cycle"] = "none"
    total_loops: int = 1
    current_loop: int = 1
    current_step_index: int = 0
    total_steps: int = 0
    current_step_name: str = ""
    current_step_gear: Literal[1, 2, 3] = 3
    current_step_target_speed: int = 0
    current_step_duration_seconds: int = 0
    planned_total_seconds: int = 0
    step_remaining_seconds: int = 0
    total_elapsed_seconds: int = 0
    last_error: str | None = None


class McuDriveMotor1Telemetry(BaseModel):
    """MCU_Drive_motor_1 (0x35A) 遥测数据。"""

    mcu_dc_main_wire_volt: float = 0.0  # 母线电压 (V)
    mcu_dc_main_wire_curr: float = 0.0  # 母线电流 (A)
    mcu_integ_ctr_flt_num: int = 0  # 故障个数
    mcu_flt_code: int = 0  # 故障代码
    mcu_flt_levl: int = 0  # 故障等级
    mcu_life_1: int = 0  # 循环计数器
    mcu_tbox_flt_levl: int = 0  # 温度故障等级


class McuDriveMotor2Telemetry(BaseModel):
    """MCU_Drive_motor_2 (0x35B) 遥测数据。"""

    mcu_motor_tor_max: float = 0.0  # 电机最大可用转矩 (Nm)
    mcu_act_motor_spd: int = 0  # 电机转速 (RPM)
    mcu_act_motor_tq: float = 0.0  # 电机实际转矩 (Nm)
    mcu_active_dischrg_sts: int = 3  # 主动放电状态
    mcu_motor_work_mod: int = 0  # 电机工作模式反馈
    mcu_lv_sts: int = 0  # MCU低压上电状态
    mcu_en_sts: int = 0  # MCU使能状态
    mcu_motor_temp_extre_over: int = 0  # 驱动电机过温故障
    mcu_mcu_temp_extre_over: int = 0  # MCU控制器过温故障
    mcm_slope_sts: int = 0  # 驻坡状态反馈 (0: 未驻坡, 1: 驻坡)
    mcu_life_2: int = 0  # 循环计数器


class McuTboxTelemetry(BaseModel):
    """MCU_Tbox_Drive_motor (0x35C) 遥测数据。"""

    num_mtr: int = 1  # 电机个数
    num_mtr_srl: int = 1  # 电机序号
    st_mtr: int = 3  # 驱动电机状态 (3: 关闭)
    mcu_motor_temp: int = 25  # 驱动电机温度 (℃)
    mcu_ctller_temp: int = 25  # MCU控制器温度 (℃)
    mcu_tbox_life: int = 0  # 循环计数器


class AxleSafetyConfig(BaseModel):
    """上位机自动紧急停机阈值。

    数值边界来自当前 DBC 信号量程，而非 MCU 的标定或硬件保护参数。
    默认开启，实时反馈越限时会触发软件急停。
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    max_motor_speed_rpm: int = Field(
        default=3000,
        gt=0,
        le=12000,
        description="电机绝对转速自动停机阈值 (RPM)",
    )
    max_motor_torque_nm: float = Field(
        default=10.0,
        gt=0.0,
        le=3000.0,
        description="电机绝对转矩自动停机阈值 (Nm)",
    )
    max_motor_temp_c: float = Field(
        default=150.0,
        gt=0.0,
        le=210.0,
        description="电机温度自动停机阈值 (℃)",
    )


class AxleSafetyTrip(BaseModel):
    """一次由上位机安全策略触发的急停事件。"""

    trip_id: int
    metric: Literal["motor_speed", "motor_torque", "motor_temperature"]
    actual_value: float
    threshold: float
    unit: Literal["RPM", "Nm", "℃"]
    message: str
    triggered_at: str


class AxleSafetyStatus(BaseModel):
    """安全配置及最近一次自动停机事件。"""

    config: AxleSafetyConfig = Field(default_factory=AxleSafetyConfig)
    last_trip: AxleSafetyTrip | None = None


class CanFrameItem(BaseModel):
    """单条 CAN 报文记录（用于原始报文监视与总线诊断）。"""

    sequence: int = Field(ge=1, description="进程内单调递增的报文序号")
    timestamp: str = Field(description="时间戳 (HH:MM:SS.mmm)")
    direction: str = Field(description="传输方向 (TX 发送 / RX 接收)")
    can_id: int = Field(description="CAN ID 整数值")
    can_id_hex: str = Field(description="CAN ID 十六进制表示，如 0x258")
    dlc: int = Field(default=8, description="数据长度 DLC")
    data_hex: str = Field(description="16 进制报文内容，空格分隔")
    name: str = Field(default="", description="报文名称，如 VCU_11")


class CanSendRawFrameRequest(BaseModel):
    """手动下发单帧 CAN 原始测试报文请求。"""

    model_config = ConfigDict(extra="forbid")

    can_id: int = Field(ge=0, le=0x1FFFFFFF, description="CAN 报文 ID")
    data_hex: str = Field(
        default="00 00 00 00 00 00 00 00",
        description="16进制数据，空格分隔，例如 '01 02 03 04 05 06 07 08'",
    )
    is_extended: bool = Field(default=False, description="是否为 29 位扩展帧")
    is_remote: bool = Field(default=False, description="是否为远程帧")


class AxleTelemetry(BaseModel):
    """电驱桥完整实时遥测与通信监控数据包。"""

    connected: bool = False
    is_transmitting: bool = False
    is_emergency_locked: bool = False
    device_type: int = 4
    device_index: int = 0
    channel: int = 0
    baud_rate: int = 500000
    command: VcuCommandState = Field(default_factory=VcuCommandState)
    cycle_test: CycleTestStatus = Field(default_factory=CycleTestStatus)
    mcu_1: McuDriveMotor1Telemetry = Field(default_factory=McuDriveMotor1Telemetry)
    # 仅在成功解码 0x35A 后更新，用于判断 MCU 故障反馈是否新鲜。
    mcu_1_last_rx_timestamp: float | None = None
    mcu_2: McuDriveMotor2Telemetry = Field(default_factory=McuDriveMotor2Telemetry)
    # 仅在成功解码 0x35B 后更新，用于区分“未使能/未上电”和“未收到反馈”。
    mcu_2_last_rx_timestamp: float | None = None
    mcu_tbox: McuTboxTelemetry = Field(default_factory=McuTboxTelemetry)
    # 仅在成功解码 0x35C 后更新，自动温度保护不使用陈旧温度值。
    mcu_tbox_last_rx_timestamp: float | None = None
    safety: AxleSafetyStatus = Field(default_factory=AxleSafetyStatus)
    tx_frame_count: int = 0
    rx_frame_count: int = 0
    tx_error_count: int = 0
    last_rx_timestamp: float | None = None
    recent_frames: list[CanFrameItem] = Field(default_factory=list)
    updated_at: str = ""


class AxleActionResponse(BaseModel):
    """通用动作响应。"""

    success: bool
    message: str
    data: dict[str, str | int | float | bool] | None = None


class McuFaultCodeItem(BaseModel):
    """MCU 故障代码表单项模型 (DEF 三列：故障码、含义、故障级别)。"""

    code: str = Field(description="DisplayCode 仪表显示码 / 故障码 (列 E，例如 'MCU_64')")
    meaning: str = Field(description="DTC 含义 (列 D，例如 'VCE过流故障')")
    level: str = Field(description="FaultLevel 故障等级 (列 F，例如 '三级 (Fault)')")
    raw_code: int = Field(description="CAN 信号 MCU_FltCode 对应原始数值")
