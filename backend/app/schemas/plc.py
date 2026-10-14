"""PLC 自动上电 / 下电相关的数据模型。"""

import ipaddress
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.plc.points import PRODUCT_TYPE_CODE, TARGET_VOLTAGE_V

PowerState = Literal["idle", "powering_on", "powered", "powering_off", "fault"]


class PlcConfig(BaseModel):
    """PLC 连接参数（保存在数据目录，下次启动沿用）。"""

    model_config = ConfigDict(extra="forbid")

    ip: str = Field(default="192.168.8.1", description="PLC IP 地址")
    rack: int = Field(default=0, ge=0, le=7, description="机架号")
    slot: int = Field(default=1, ge=0, le=31, description="CPU 槽号（S7-1500 通常为 1）")
    simulation: bool = Field(default=False, description="本地仿真（不连接真实 PLC）")

    @field_validator("ip")
    @classmethod
    def validate_ip(cls, value: str) -> str:
        value = value.strip()
        try:
            ipaddress.IPv4Address(value)
        except ValueError as err:
            raise ValueError("请输入有效的 IPv4 地址，例如 192.168.8.1") from err
        return value


class PlcStatus(BaseModel):
    """PLC 连接与 1 号工位供电状态快照。"""

    connected: bool = False
    simulation: bool = False
    ip: str = "192.168.8.1"
    rack: int = 0
    slot: int = 1
    # 最近 1 s 内成功读到过 PLC 反馈
    communication_ok: bool = False
    communication_error: str | None = None
    # 仅用于显示，不参与任何放行或停机判断
    plc_heartbeat_alive: bool = False

    safe: bool = False
    request_power: bool = False
    power_on: bool = False
    contactor_closed: bool = False

    product_type_expected: int = PRODUCT_TYPE_CODE
    product_type_feedback: int = 0
    target_voltage: int = TARGET_VOLTAGE_V
    output_voltage: int = 0
    output_current: int = 0
    serial_number: str = ""

    power_state: PowerState = "idle"
    fault_reason: str | None = None
    last_message: str | None = None


class PlcActionResponse(BaseModel):
    """上电 / 下电操作结果。partial 表示指令已发出但部分步骤未确认。"""

    status: Literal["success", "partial"]
    message: str
    plc: PlcStatus


class PlcSimulationSafeRequest(BaseModel):
    """仿真模式下模拟安全回路闭合 / 断开（用于联调演练）。"""

    model_config = ConfigDict(extra="forbid")

    safe: bool


TrafficValue = int | float | str | None


class PlcTrafficPoint(BaseModel):
    """通信监视点表中的一个点位及其最新值。"""

    name: str
    label: str
    address: str
    value: TrafficValue = None


class PlcTrafficSnapshot(BaseModel):
    """1 号工位全部点位的最新值；PLC 未连接时 updated_at 为空。"""

    updated_at: str | None = None
    write: list[PlcTrafficPoint]
    read: list[PlcTrafficPoint]


class PlcTrafficEntry(BaseModel):
    """一条通信记录：上位机写入，或 PLC 反馈值的一次变化。"""

    seq: int
    time: str
    direction: Literal["write", "read"]
    name: str
    label: str
    address: str
    value: TrafficValue = None
    previous: TrafficValue = None
    source: str = ""
    frequent: bool = False


class PlcTrafficLogResponse(BaseModel):
    latest_seq: int
    entries: list[PlcTrafficEntry]
