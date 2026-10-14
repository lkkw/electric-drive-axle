"""试车记录：当前试车统计、操作员判定与历史查询导出。"""

from typing import Literal

from pydantic import BaseModel, Field

TestResult = Literal[1, 2]


class TestSessionStats(BaseModel):
    """当前这台电驱桥的试车统计：从上次判定后第一次收到 MCU 反馈开始累计。"""

    started_at: str | None = Field(
        default=None, description="开始时间 (ISO 8601, UTC)；尚未收到反馈时为空"
    )
    duration_s: float | None = Field(default=None, description="从开始到现在的时长 (s)")
    max_speed_rpm: int | None = Field(default=None, description="最高转速绝对值 (RPM)")
    max_torque_nm: float | None = Field(default=None, description="最大转矩绝对值 (Nm)")
    max_motor_temp_c: float | None = None
    max_controller_temp_c: float | None = None
    max_bus_current_a: float | None = Field(default=None, description="最大母线电流绝对值 (A)")
    fault_codes: list[str] = Field(default_factory=list, description="试车期间 MCU 上报过的故障码")
    safety_trips: int = Field(default=0, description="试车期间自动安全停机次数")


class TestRecordJudgeRequest(BaseModel):
    result: TestResult = Field(description="1=合格 2=NG")
    remark: str = Field(default="", max_length=200, description="备注，例如 NG 原因")


class TestRecord(BaseModel):
    """一条电驱桥下线试车记录。"""

    id: int
    timestamp: str = Field(description="判定时间 (ISO 8601, UTC)")
    sn: str | None = Field(default=None, description="PLC 回传的产品序列号")
    result: TestResult
    remark: str = ""
    started_at: str | None = None
    duration_s: float | None = None
    max_speed_rpm: int | None = None
    max_torque_nm: float | None = None
    max_motor_temp_c: float | None = None
    max_controller_temp_c: float | None = None
    max_bus_current_a: float | None = None
    fault_codes: str = Field(default="", description="故障码，逗号分隔")
    safety_trips: int = 0
    plc_result_written: bool = Field(default=False, description="判定结果是否已写入 PLC Result")


class TestRecordJudgeResponse(BaseModel):
    record: TestRecord
    message: str


class TestRecordExportResponse(BaseModel):
    path: str = Field(description="导出的 CSV 文件完整路径")
    count: int = Field(description="导出的记录条数")
