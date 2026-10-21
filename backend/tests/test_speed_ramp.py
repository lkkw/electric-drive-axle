"""速度斜坡：实际下发转速以限定速率逼近目标，减少急减速时的回馈能量（防母线过压 MCU_139）。"""

import time
from unittest.mock import MagicMock

from app.schemas.axle import McuDriveMotor2Telemetry
from app.services.axle_manager import (
    SPEED_RAMP_ACCEL_RPM_PER_S,
    SPEED_RAMP_DECEL_RPM_PER_S,
    AxleManager,
)

TICK = 0.01  # 10 ms 发送周期
D, R, N = 1, 2, 3
SPEED_MODE, TORQUE_MODE = 3, 1


def make_manager() -> AxleManager:
    return AxleManager(driver=MagicMock())


def run(manager: AxleManager, speed: int, gear: int, seconds: float) -> list[tuple[int, int]]:
    """按 10 ms 节拍连续调用斜坡，返回每拍实际下发的 (转速, 挡位)。"""
    ticks = round(seconds / TICK)
    return [manager._slew_speed_locked(speed, gear, SPEED_MODE, 1, TICK) for _ in range(ticks)]


def signed(sent: tuple[int, int]) -> int:
    speed, gear = sent
    return speed if gear == D else -speed if gear == R else 0


def test_decel_to_neutral_is_rate_limited_and_keeps_drive_gear_until_stopped() -> None:
    manager = make_manager()
    manager._ramp_speed = 1000.0

    frames = run(manager, 0, N, 6.0)

    # 每拍降速不超过限值
    per_tick = SPEED_RAMP_DECEL_RPM_PER_S * TICK
    speeds = [1000] + [signed(f) for f in frames]
    assert all(prev - now <= per_tick + 1 for prev, now in zip(speeds, speeds[1:], strict=False))
    # 电机仍在转时保持 D 挡，降到 0 后才发 N 挡
    assert frames[0] == (998, D)
    assert all(gear == D for speed, gear in frames if speed > 0)
    stop_tick = next(i for i, (speed, _) in enumerate(frames) if speed == 0)
    assert abs(stop_tick * TICK - 1000 / SPEED_RAMP_DECEL_RPM_PER_S) < 0.05
    assert frames[-1] == (0, N)


def test_reversal_ramps_down_to_zero_before_accelerating_in_reverse() -> None:
    manager = make_manager()
    manager._ramp_speed = 1000.0

    frames = run(manager, 1000, R, 10.0)
    values = [signed(f) for f in frames]

    first_reverse = next(i for i, v in enumerate(values) if v < 0)
    # 越过 0 之前一直在减速、保持 D 挡
    assert all(v >= 0 for v in values[:first_reverse])
    assert values[first_reverse - 1] == 0
    # 反向加速按加速速率
    assert values[first_reverse] == -round(SPEED_RAMP_ACCEL_RPM_PER_S * TICK)
    assert frames[-1] == (1000, R)


def test_enable_from_rest_accelerates_at_accel_rate() -> None:
    manager = make_manager()
    first = manager._slew_speed_locked(1000, D, SPEED_MODE, 1, TICK)
    assert first == (round(SPEED_RAMP_ACCEL_RPM_PER_S * TICK), D)


def test_engaging_while_coasting_starts_from_actual_speed() -> None:
    """电机仍在反向滑行时使能正转：从实际转速起步先减速，不在使能瞬间急刹。"""
    manager = make_manager()
    manager._mcu_2 = McuDriveMotor2Telemetry(mcu_act_motor_spd=-800)
    manager._mcu_2_last_rx_timestamp = time.time()

    first = manager._slew_speed_locked(1000, D, SPEED_MODE, 1, TICK)
    assert first == (800 - round(SPEED_RAMP_DECEL_RPM_PER_S * TICK), R)


def test_disabled_or_torque_mode_passes_through_and_resets_ramp() -> None:
    manager = make_manager()
    manager._ramp_speed = 1500.0

    assert manager._slew_speed_locked(0, N, SPEED_MODE, 0, TICK) == (0, N)
    assert manager._ramp_speed is None

    manager._ramp_speed = 1500.0
    assert manager._slew_speed_locked(0, N, TORQUE_MODE, 1, TICK) == (0, N)
    assert manager._ramp_speed is None


def test_long_tick_is_clamped() -> None:
    """发送循环卡顿 1 s 也只按最长步长前进，不会一次跳到目标。"""
    manager = make_manager()
    manager._ramp_speed = 3000.0
    speed, gear = manager._slew_speed_locked(0, N, SPEED_MODE, 1, 1.0)
    assert gear == D
    assert speed >= 3000 - SPEED_RAMP_DECEL_RPM_PER_S * 0.05 - 1
