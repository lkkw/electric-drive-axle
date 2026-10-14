"""当前这台电驱桥的试车统计：随 MCU 反馈累计，操作员判定后清零。"""

import time
from datetime import UTC, datetime

from app.core.can.constants import MCU_FAULT_CODES
from app.schemas.test_records import TestSessionStats

_FAULT_CODE_NAMES = {item.raw_code: item.code for item in MCU_FAULT_CODES}


def fault_code_name(raw_code: int) -> str:
    """MCU_FltCode 原始值 → 仪表显示码（例如 64 → MCU_64）。"""
    return _FAULT_CODE_NAMES.get(raw_code, f"MCU_{raw_code}")


class TestSession:
    """从上次判定后第一次收到 MCU 反馈开始累计最大值与故障码。"""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._started_at: datetime | None = None
        self._started_mono: float | None = None
        self._max_speed_rpm: int | None = None
        self._max_torque_nm: float | None = None
        self._max_motor_temp_c: float | None = None
        self._max_controller_temp_c: float | None = None
        self._max_bus_current_a: float | None = None
        self._fault_codes: list[str] = []
        self._safety_trips = 0

    def _touch(self) -> None:
        if self._started_mono is None:
            self._started_mono = time.monotonic()
            self._started_at = datetime.now(UTC)

    @staticmethod
    def _max(current: float | None, value: float) -> float:
        return value if current is None else max(current, value)

    def on_mcu_1(self, *, bus_current_a: float, fault_code: int) -> None:
        self._touch()
        self._max_bus_current_a = self._max(self._max_bus_current_a, abs(bus_current_a))
        if fault_code:
            name = fault_code_name(fault_code)
            if name not in self._fault_codes:
                self._fault_codes.append(name)

    def on_mcu_2(self, *, speed_rpm: int, torque_nm: float) -> None:
        self._touch()
        self._max_speed_rpm = int(self._max(self._max_speed_rpm, abs(speed_rpm)))
        self._max_torque_nm = self._max(self._max_torque_nm, abs(torque_nm))

    def on_temperature(self, *, motor_temp_c: float, controller_temp_c: float) -> None:
        self._touch()
        self._max_motor_temp_c = self._max(self._max_motor_temp_c, motor_temp_c)
        self._max_controller_temp_c = self._max(self._max_controller_temp_c, controller_temp_c)

    def on_safety_trip(self) -> None:
        self._safety_trips += 1

    def snapshot(self) -> TestSessionStats:
        duration = (
            round(time.monotonic() - self._started_mono, 1)
            if self._started_mono is not None
            else None
        )
        return TestSessionStats(
            started_at=(
                self._started_at.isoformat(timespec="seconds") if self._started_at else None
            ),
            duration_s=duration,
            max_speed_rpm=self._max_speed_rpm,
            max_torque_nm=None if self._max_torque_nm is None else round(self._max_torque_nm, 1),
            max_motor_temp_c=self._max_motor_temp_c,
            max_controller_temp_c=self._max_controller_temp_c,
            max_bus_current_a=(
                None if self._max_bus_current_a is None else round(self._max_bus_current_a, 1)
            ),
            fault_codes=list(self._fault_codes),
            safety_trips=self._safety_trips,
        )
