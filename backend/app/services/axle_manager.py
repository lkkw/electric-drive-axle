"""Electric Drive Axle State Manager and Communication Coordinator.

Manages:
- CAN hardware lifecycle (connect, disconnect, channel setup, link-failure auto stop).
- Real-time 10ms high-precision transmission task (VCU_11, ID 0x258).
- Real-time high-throughput receive task and bitwise decoding (0x35A, 0x35B, 0x35C).
- Safety supervision (threshold trips and MCU feedback watchdog).
- Thread-safe state synchronization and SSE subscription broadcast.
"""

import asyncio
import logging
import math
import time
from collections import deque
from collections.abc import Awaitable, Callable, Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

from app.core.can.codec import (
    decode_mcu_motor_1,
    decode_mcu_motor_2,
    decode_mcu_tbox_motor,
    encode_vcu_11,
)
from app.core.can.constants import (
    CAN_ID_VCU_11,
    ZcanDeviceType,
)
from app.core.can.driver import (
    CanDriverError,
    CanRawFrame,
    UnavailableCanDriver,
    ZlgCanDriver,
    windows_high_resolution_timer,
)
from app.core.config import get_settings
from app.core.logging_setup import EVENT_LOGGER_NAME
from app.schemas.axle import (
    AxleSafetyConfig,
    AxleSafetyStatus,
    AxleSafetyTrip,
    AxleTelemetry,
    CanConnectRequest,
    CanFrameItem,
    CanSendRawFrameRequest,
    CycleTestStartRequest,
    CycleTestStatus,
    McuDriveMotor1Telemetry,
    McuDriveMotor2Telemetry,
    McuTboxTelemetry,
    SafetyMetric,
    SafetyUnit,
    VcuCommandState,
    VcuCommandUpdateRequest,
)
from app.services.safety_store import load_safety_config, save_safety_config
from app.services.test_session import TestSession

logger = logging.getLogger("app.axle_manager")
# 关键操作与安全事件单独落盘 (events.log)，用于产线追溯。
events = logging.getLogger(EVENT_LOGGER_NAME)

# 自动停机只接受近期成功解码的反馈，避免使用断线前残留的遥测值。
MCU_2_SAFETY_FRESHNESS_SECONDS = 0.5
MCU_TBOX_SAFETY_FRESHNESS_SECONDS = 1.0
# 上传 MES 的转速 / 温度超过该时长未更新即视为过期，改传 0
MES_FEEDBACK_STALE_SECONDS = 2.0
SHUTDOWN_FRAME_COUNT = 2
SHUTDOWN_FRAME_TIMEOUT_SECONDS = 0.2
STREAM_FRAME_LIMIT = 200
RECENT_FRAME_CAPACITY = 500

# 10ms 控制周期。
TX_INTERVAL_SECONDS = 0.010
# 接收轮询间隔。
RX_POLL_INTERVAL_SECONDS = 0.005
# SSE 推送节拍：无论总线上有无报文都按此频率推送，保证计数器与状态实时可见。
BROADCAST_INTERVAL_SECONDS = 0.050

# 同一收发源连续驱动异常达到任一条件即判定硬件链路失效并自动停止通信。
LINK_FAILURE_ERROR_COUNT = 10
LINK_FAILURE_SECONDS = 1.0
# 空闲时（未使能、无循环测试）驱动异常只提示不断开：控制器未上电时总线上无节点应答，
# USBCAN 反复重发会让发送调用超时，这不是 USBCAN 掉线。
BUS_NO_RESPONSE_WARNING = (
    "CAN 总线无应答：请确认控制器已上电、CAN 线束已连接；若控制器已上电仍持续出现，"
    "请检查 USBCAN 连接。控制器恢复通信后自动消除。"
)
# 同类高频告警日志的最小输出间隔，避免 10ms 循环刷屏。
LOG_THROTTLE_SECONDS = 1.0

# 平稳停机：实际转速降到该值以内即认为已停稳，随后关闭使能并切 N 挡。
SOFT_STOP_SPEED_THRESHOLD_RPM = 30
# 平稳停机最长等待时间；超时仍强制关闭使能（电机随后自由滑行）。
SOFT_STOP_TIMEOUT_SECONDS = 30.0
SOFT_STOP_POLL_SECONDS = 0.05
# 手动下电前，电机仍在转时等待停稳的最长时间；超时照常下电并在结果中提示。
POWER_OFF_MOTOR_STOP_TIMEOUT_SECONDS = 10.0

SAFETY_METRIC_LABELS: dict[SafetyMetric, str] = {
    "motor_speed": "实际转速",
    "motor_torque": "实际转矩",
    "motor_temperature": "电机温度",
    "feedback_timeout": "MCU_2 反馈中断",
    "plc_safe": "PLC 安全回路",
}

# 急停 / 链路故障时的外部联动（如 PLC 复位上电请求切断高压），参数为原因
EmergencyListener = Callable[[str], Awaitable[None]]
# 循环测试跑完或异常中断后的联动（自动判定、自动下电），参数为结束时的循环状态
CycleFinishedListener = Callable[[CycleTestStatus], Awaitable[None]]


class _FrameRecord(NamedTuple):
    """报文监视缓冲区内的轻量记录，仅在生成快照时才转换为 Pydantic 模型。"""

    sequence: int
    wall_time: float
    direction: str
    can_id: int
    data: bytes
    name: str


class _SafetyViolation(NamedTuple):
    metric: SafetyMetric
    actual_value: float
    threshold: float
    unit: SafetyUnit


class AxleManager:
    """电驱桥上位机系统核心管理器 (单例生命周期)。"""

    def __init__(
        self,
        driver: ZlgCanDriver | None = None,
        *,
        safety_config_path: Path | None = None,
    ) -> None:
        """初始化管理器。

        :param driver: CAN 驱动实例，缺省时加载周立功动态库
        :param safety_config_path: 自动停机阈值持久化文件；为 None 时仅保存在内存
        """
        # 动态库加载失败时程序仍需启动，以便在界面上展示原因而不是让所有接口报 500。
        self._driver_error: str | None = None
        if driver is None:
            try:
                driver = ZlgCanDriver()
            except (CanDriverError, FileNotFoundError, RuntimeError) as err:
                self._driver_error = str(err)
                logger.error("CAN 驱动加载失败: %s", err)
                driver = UnavailableCanDriver(str(err))
        self._driver = driver
        self._lock = asyncio.Lock()
        self._lifecycle_lock = asyncio.Lock()

        # 通信配置
        self._device_type: int = ZcanDeviceType.USBCAN2
        self._device_index: int = 0
        self._channel: int = 0
        self._baud_rate: int = 500000

        # 控制指令状态 (VCU_11 发送内容)
        self._command = VcuCommandState()
        self._cycle_status = CycleTestStatus()
        self._cycle_config: CycleTestStartRequest | None = None
        self._cycle_task: asyncio.Task[None] | None = None
        self._cycle_generation = 0
        self._cycle_step_remaining = 0.0
        self._cycle_elapsed = 0.0

        # 遥测反馈状态
        self._mcu_1 = McuDriveMotor1Telemetry()
        self._mcu_2 = McuDriveMotor2Telemetry()
        self._mcu_tbox = McuTboxTelemetry()
        # 当前这台电驱桥的试车统计（试车记录用），操作员判定后清零
        self.test_session = TestSession()
        self._manual_judging = False  # 操作员手动判定进行中：期间不允许启动循环测试

        # 通信统计
        self._connected: bool = False
        self._is_transmitting: bool = False
        self._is_emergency_locked: bool = False  # 急停互锁标志：触发后拒绝一切使能/驱动指令
        self._tx_frame_count: int = 0
        self._rx_frame_count: int = 0
        self._tx_error_count: int = 0
        self._last_rx_timestamp: float | None = None
        self._mcu_1_last_rx_timestamp: float | None = None
        self._mcu_2_last_rx_timestamp: float | None = None
        self._mcu_tbox_last_rx_timestamp: float | None = None
        self._recent_frames: deque[_FrameRecord] = deque(maxlen=RECENT_FRAME_CAPACITY)
        self._frame_sequence: int = 0

        # 上位机自动停机策略。阈值持久化在本地文件，进程启动时恢复。
        self._safety_config_path = safety_config_path
        self._safety_config = load_safety_config(safety_config_path)
        self._safety_last_trip: AxleSafetyTrip | None = None
        self._safety_trip_id = 0
        # 使能指令生效时刻：反馈看门狗以“使能时刻”和“最近一次 0x35B”中较晚者为基准。
        self._enable_since: float | None = None

        # 硬件链路健康：按收发源统计连续异常 (次数, 首次异常单调时间)。
        self._driver_error_streaks: dict[str, tuple[int, float]] = {}
        self._link_error: str | None = None
        self._bus_warning: str | None = None
        self._link_failure_task: asyncio.Task[None] | None = None
        self._soft_stop_task: asyncio.Task[None] | None = None
        self._emergency_listeners: list[EmergencyListener] = []
        self._cycle_finished_listeners: list[CycleFinishedListener] = []
        self._listener_tasks: set[asyncio.Task[None]] = set()
        self._log_throttle: dict[str, tuple[float, int]] = {}

        # 异步循环任务句柄
        self._tx_task: asyncio.Task[None] | None = None
        self._rx_task: asyncio.Task[None] | None = None
        self._disconnecting: bool = False
        self._shutdown_frames_remaining: int = 0
        self._shutdown_frames_sent = asyncio.Event()

        # SSE 事件分发队列集合
        self._subscribers: dict[asyncio.Queue[AxleTelemetry], bool] = {}

    @property
    def is_connected(self) -> bool:
        """硬件连接状态。"""
        return self._connected

    @property
    def is_transmitting(self) -> bool:
        """报文发送循环状态。"""
        return self._is_transmitting

    @property
    def requires_close_confirmation(self) -> bool:
        """电机已使能或循环测试未结束时，关闭程序前需要操作员确认。"""
        return self._connected and (
            self._command.mcu_en_cmd == 1 or self._cycle_status.status in {"running", "paused"}
        )

    def _channels(self) -> list[int]:
        """当前配置下参与收发的通道列表 (-1 表示双通道)。"""
        return [0, 1] if self._channel == -1 else [self._channel]

    # ------------------------------------------------------------------
    # 连接生命周期
    # ------------------------------------------------------------------
    async def connect(self, config: CanConnectRequest) -> None:
        """串行执行设备连接，避免与停止/重连流程交叉操作硬件句柄。"""
        async with self._lifecycle_lock:
            if self._connected:
                # 重连走完整断开流程：停机帧、等待旧任务退出后再释放句柄，
                # 杜绝旧任务仍在 DLL 调用中时句柄被关闭。
                logger.info("设备已处于连接状态，先安全断开旧连接。")
                await self._disconnect()
            await self._connect(config)
        self._broadcast_telemetry()

    async def _connect(self, config: CanConnectRequest) -> None:
        """连接周立功 USBCAN 设备并开启通道与收发任务。

        :param config: 设备与通道配置参数
        """
        async with self._lock:
            self._device_type = config.device_type
            self._device_index = config.device_index
            self._channel = config.channel
            self._baud_rate = config.baud_rate
            self._mcu_1_last_rx_timestamp = None
            self._mcu_2_last_rx_timestamp = None
            self._mcu_tbox_last_rx_timestamp = None
            self._enable_since = None
            self._driver_error_streaks.clear()

            logger.info(
                "正在打开 USBCAN 设备 (type=%d, index=%d, chn=%d, baud=%d)...",
                self._device_type,
                self._device_index,
                self._channel,
                self._baud_rate,
            )

            # 1. 打开硬件设备与启动通道
            await self._driver.open_device(
                device_type=self._device_type,
                device_index=self._device_index,
            )
            try:
                for ch in self._channels():
                    await self._driver.open_channel(
                        channel=ch,
                        baud_rate=self._baud_rate,
                    )
            except Exception as err:
                # 若通道初始化失败，必须回滚释放已打开的设备句柄，防止硬件句柄泄漏
                logger.error("通道打开失败，正在回滚设备状态: %s", err)
                for ch in self._channels():
                    try:
                        await self._driver.close_channel(ch)
                    except Exception:
                        pass
                try:
                    await self._driver.close_device()
                except Exception:
                    pass
                raise

            self._connected = True
            self._is_transmitting = True
            self._link_error = None
            self._bus_warning = None

            # 2. 启动 10ms 发送循环与高频接收循环
            self._tx_task = asyncio.create_task(
                self._tx_loop(),
                name="axle_can_tx_loop",
            )
            self._rx_task = asyncio.create_task(
                self._rx_loop(),
                name="axle_can_rx_loop",
            )

            events.info(
                "CAN 已连接: 设备类型=%d 索引=%d 通道=%d 波特率=%d",
                self._device_type,
                self._device_index,
                self._channel,
                self._baud_rate,
            )

    async def disconnect(self) -> None:
        """串行执行设备停止与资源释放。"""
        async with self._lifecycle_lock:
            was_connected = self._connected
            await self._disconnect()
        if was_connected:
            events.info("CAN 已由操作员断开")

    async def _disconnect(self, *, failure_reason: str | None = None) -> None:
        """安全断开 CAN 通信并释放硬件资源 (需在生命周期锁内调用)。

        :param failure_reason: 因链路故障被动断开时的原因；正在执行的循环测试将以
            ``error`` 状态结束并记录该原因。
        """
        disconnect_started = time.perf_counter()

        # 先把控制量切换到安全值，让既有 10 ms 循环连续发送两帧。
        # 这样既保留 VCU_Life 连续性，也避免停掉循环后再额外等待一次底层发送调用。
        async with self._lock:
            was_connected = self._connected
            self._cancel_soft_stop_locked()
            cycle_active = self._cycle_status.status in {"running", "paused"}
            if failure_reason is not None and cycle_active:
                self._finish_cycle_locked("error", error=failure_reason)
            else:
                self._finish_cycle_locked("stopped")
            should_drain_shutdown_frames = self._connected and self._tx_task is not None
            self._disconnecting = should_drain_shutdown_frames
            self._set_safe_command_locked()
            self._shutdown_frames_remaining = (
                SHUTDOWN_FRAME_COUNT if should_drain_shutdown_frames else 0
            )
            self._shutdown_frames_sent.clear()

        shutdown_frames_confirmed = False
        if should_drain_shutdown_frames:
            try:
                await asyncio.wait_for(
                    self._shutdown_frames_sent.wait(),
                    timeout=SHUTDOWN_FRAME_TIMEOUT_SECONDS,
                )
                shutdown_frames_confirmed = True
            except TimeoutError:
                logger.warning(
                    "停机保护帧未在 %.0f ms 内完成发送，释放前补发一帧。",
                    SHUTDOWN_FRAME_TIMEOUT_SECONDS * 1000,
                )

        # 停止后台任务，并使实时反馈立即失效。
        async with self._lock:
            self._is_transmitting = False
            self._connected = False
            self._disconnecting = False
            self._bus_warning = None
            self._shutdown_frames_remaining = 0
            self._mcu_1_last_rx_timestamp = None
            self._mcu_2_last_rx_timestamp = None
            self._mcu_tbox_last_rx_timestamp = None
            self._enable_since = None
            tasks_to_cancel = [t for t in (self._tx_task, self._rx_task) if t is not None]
            self._tx_task = None
            self._rx_task = None

        # 在锁外取消并等待任务退出，避免任务因争抢状态锁而延迟退出。
        for task in tasks_to_cancel:
            if not task.done():
                task.cancel()
        for task in tasks_to_cancel:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as err:
                logger.warning("停止任务时发生异常: %s", err)

        # 周期循环已确认发出连续 Life 的停机帧时不再重复；否则在关闭前补发一帧。
        async with self._lock:
            await self._cleanup_hardware(
                send_shutdown_frame=was_connected and not shutdown_frames_confirmed,
            )

        logger.info(
            "USBCAN 停止通信并释放设备完成，耗时 %.1f ms。",
            (time.perf_counter() - disconnect_started) * 1000,
        )
        self._broadcast_telemetry()

    async def _cleanup_hardware(self, *, send_shutdown_frame: bool = True) -> None:
        """发送停机保护帧并释放硬件资源 (需在锁保护下调用)。"""
        channels_to_close = self._channels()

        # 周期循环未能确认停机帧时 (链路异常或任务已退出)，使用下一连续 Life 补发一帧。
        if send_shutdown_frame:
            try:
                self._command.life = (self._command.life + 1) % 16
                shutdown_payload = encode_vcu_11(
                    torque_req=0.0,
                    speed_req=0,
                    work_mode_req=0,
                    mcu_en_cmd=0,
                    gear_sts=3,
                    life=self._command.life,
                )
                for ch in channels_to_close:
                    if self._driver.is_channel_open(ch):
                        try:
                            sent = await self._driver.transmit(
                                can_id=CAN_ID_VCU_11,
                                data=shutdown_payload,
                                channel=ch,
                            )
                            if sent:
                                self._tx_frame_count += 1
                            else:
                                self._tx_error_count += 1
                        except Exception as err:
                            self._tx_error_count += 1
                            logger.warning("下发停机保护帧异常 (通道 %d): %s", ch, err)
            except Exception as err:
                logger.warning("生成停机保护帧异常: %s", err)

        # 关闭通道并释放设备。
        for ch in channels_to_close:
            close_channel_started = time.perf_counter()
            try:
                await self._driver.close_channel(ch)
            except Exception as err:
                logger.error("关闭通道 %d 时发生异常: %s", ch, err)
            finally:
                logger.info(
                    "关闭 CAN 通道 %d 耗时 %.1f ms。",
                    ch,
                    (time.perf_counter() - close_channel_started) * 1000,
                )
        close_device_started = time.perf_counter()
        try:
            await self._driver.close_device()
        except Exception as err:
            logger.error("关闭设备时发生异常: %s", err)
        finally:
            logger.info(
                "关闭 USBCAN 设备句柄耗时 %.1f ms。",
                (time.perf_counter() - close_device_started) * 1000,
            )

        logger.info("USBCAN 设备已完全关闭并释放。")

    # ------------------------------------------------------------------
    # 硬件链路健康与日志限流
    # ------------------------------------------------------------------
    def _log_throttled(self, key: str, level: int, msg: str, *args: object) -> None:
        """同一 key 的日志每秒最多输出一次，并汇报期间被省略的次数。"""
        now = time.monotonic()
        last, suppressed = self._log_throttle.get(key, (-math.inf, 0))
        if now - last < LOG_THROTTLE_SECONDS:
            self._log_throttle[key] = (last, suppressed + 1)
            return
        if suppressed:
            msg = f"{msg}（期间另有 %d 次同类告警已省略）"
            args = (*args, suppressed)
        logger.log(level, msg, *args)
        self._log_throttle[key] = (now, 0)

    def _note_driver_success(self, source: str) -> None:
        """一次成功的驱动调用即结束该收发源的连续异常计数。"""
        if source in self._driver_error_streaks:
            del self._driver_error_streaks[source]
        if self._bus_warning is not None and not self._driver_error_streaks:
            self._bus_warning = None
            events.info("CAN 总线通信已恢复")

    def _control_active(self) -> bool:
        """电机已使能或循环测试未结束：此时失去 CAN 控制必须自动停止通信并切断高压。"""
        return self._command.mcu_en_cmd == 1 or self._cycle_status.status in {
            "running",
            "paused",
        }

    def _note_driver_error(self, source: str, description: str, err: Exception) -> None:
        """记录驱动异常；测试进行中连续异常达到阈值时安排自动停止通信。

        空闲时只提示总线无应答、保持连接。异常持续期间一旦使能或启动循环，
        下一次异常即按已持续的时长判定为链路失效。
        """
        now = time.monotonic()
        count, since = self._driver_error_streaks.get(source, (0, now))
        count += 1
        self._driver_error_streaks[source] = (count, since)

        if not self._control_active():
            if self._bus_warning is None:
                self._bus_warning = BUS_NO_RESPONSE_WARNING
                events.warning("CAN 总线无应答，电机未使能，保持连接: %s: %s", description, err)
            return

        self._log_throttled(source, logging.WARNING, "%s异常: %s", description, err)

        if count >= LINK_FAILURE_ERROR_COUNT or now - since >= LINK_FAILURE_SECONDS:
            self._schedule_link_failure(
                f"{description}连续 {count} 次异常（持续 {(now - since) * 1000:.0f} ms），"
                f"已自动停止通信: {err}"
            )

    def _schedule_link_failure(self, reason: str) -> None:
        """在独立任务中执行自动断开，避免收发循环取消自身。"""
        if not self._connected or self._disconnecting:
            return
        if self._link_failure_task is not None and not self._link_failure_task.done():
            return
        self._link_failure_task = asyncio.create_task(
            self._handle_link_failure(reason),
            name="axle_can_link_failure",
        )

    async def _handle_link_failure(self, reason: str) -> None:
        """硬件链路失效：结束循环测试、发送停机帧 (尽力) 并释放设备。"""
        events.error("CAN 硬件链路失效，自动停止通信: %s", reason)
        async with self._lifecycle_lock:
            if not self._connected:
                return
            await self._disconnect(failure_reason=reason)
            self._link_error = reason
        # 失去 CAN 控制后电机指令无法送达，同时切断高压
        self._notify_emergency_listeners(f"CAN 链路故障: {reason}")
        self._broadcast_telemetry()

    # ------------------------------------------------------------------
    # 控制命令与循环测试
    # ------------------------------------------------------------------
    def _set_safe_command_locked(self) -> None:
        """在状态锁内写入统一的停机命令快照。"""
        self._command.torque_req = 0.0
        self._command.speed_req = 0
        self._command.work_mode_req = 0
        self._command.mcu_en_cmd = 0
        self._command.gear_sts = 3

    def _apply_update_locked(self, update: VcuCommandUpdateRequest) -> None:
        """在状态锁内合并一组已通过 Pydantic 校验的控制字段。"""
        for field_name in (
            "torque_req",
            "speed_req",
            "work_mode_req",
            "mcu_en_cmd",
            "gear_sts",
        ):
            value = getattr(update, field_name)
            if value is not None:
                setattr(self._command, field_name, value)

    def _apply_cycle_step_locked(self) -> None:
        """在状态锁内将当前循环步骤转换为完整控制命令。"""
        if self._cycle_config is None:
            raise CanDriverError("循环测试配置丢失。")
        step = self._cycle_config.steps[self._cycle_status.current_step_index]
        self._cycle_status.current_step_name = step.name
        self._cycle_status.current_step_gear = step.gear
        self._cycle_status.current_step_target_speed = step.target_speed
        self._cycle_status.current_step_duration_seconds = step.duration_seconds
        self._command.torque_req = 0.0
        self._command.speed_req = step.target_speed
        self._command.work_mode_req = 3
        self._command.mcu_en_cmd = 1
        self._command.gear_sts = step.gear

    def _finish_cycle_locked(
        self,
        status: str,
        *,
        error: str | None = None,
        abnormal: bool = False,
    ) -> None:
        """终止循环任务并统一进入禁用、归零、N 挡状态。

        循环正常跑完（completed）或异常中断（error / ``abnormal``，如急停）时通知自动判定；
        操作员主动终止、操作员下电或断开 CAN 不判定。
        """
        was_active = self._cycle_status.status in {"running", "paused"}
        self._cycle_generation += 1
        task = self._cycle_task
        self._cycle_task = None
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()
        self._set_safe_command_locked()
        self._cycle_status.status = status  # type: ignore[assignment]
        self._cycle_status.control_owner = "none"
        self._cycle_status.step_remaining_seconds = 0
        self._cycle_status.last_error = error
        if (
            was_active
            and (status in {"completed", "error"} or abnormal)
            and self._cycle_finished_listeners
        ):
            self._cycle_status.auto_judge = "pending"
            snapshot = self._cycle_status.model_copy()
            for listener in self._cycle_finished_listeners:
                self._spawn_listener(listener(snapshot), name="axle_cycle_finished_listener")

    async def start_cycle_test(
        self,
        request: CycleTestStartRequest,
    ) -> CycleTestStatus:
        """由后端取得控制权并启动单一循环测试状态机。"""
        async with self._lock:
            if not self._connected or not self._is_transmitting:
                raise CanDriverError("CAN 未连接，无法启动循环测试。")
            if self._disconnecting:
                raise CanDriverError("设备正在停止通信，无法启动循环测试。")
            if self._is_emergency_locked:
                raise CanDriverError("系统处于急停锁定状态，请先完成复位。")
            if self._cycle_status.status in {"running", "paused"}:
                raise CanDriverError("已有循环测试正在执行。")
            if self._cycle_status.auto_judge == "pending":
                raise CanDriverError("上一轮循环测试正在自动判定 / 下电，请稍候。")
            if self._manual_judging:
                raise CanDriverError("正在保存试车判定，请稍候。")

            self._cancel_soft_stop_locked()
            # 自动判定只看本轮循环：清掉循环前手动调试期间累计的统计与故障码
            self.test_session.reset()
            self._cycle_generation += 1
            generation = self._cycle_generation
            self._cycle_config = request.model_copy(deep=True)
            first_step = self._cycle_config.steps[0]
            self._cycle_step_remaining = float(first_step.duration_seconds)
            self._cycle_elapsed = 0.0
            self._cycle_status = CycleTestStatus(
                status="running",
                control_owner="cycle",
                total_loops=request.total_loops,
                current_loop=1,
                current_step_index=0,
                total_steps=len(request.steps),
                planned_total_seconds=(
                    sum(step.duration_seconds for step in request.steps) * request.total_loops
                ),
                step_remaining_seconds=first_step.duration_seconds,
                total_elapsed_seconds=0,
            )
            self._apply_cycle_step_locked()
            self._cycle_task = asyncio.create_task(
                self._cycle_loop(generation),
                name="axle_cycle_test",
            )
            result = self._cycle_status.model_copy()
            events.info(
                "循环测试启动: %d 步 × %d 圈，计划 %d s",
                result.total_steps,
                result.total_loops,
                result.planned_total_seconds,
            )

        self._broadcast_telemetry()
        return result

    async def pause_cycle_test(self) -> CycleTestStatus:
        """暂停循环计时并立即写入完整安全命令。"""
        async with self._lock:
            if self._cycle_status.status != "running":
                raise CanDriverError("当前没有可暂停的循环测试。")
            self._cycle_status.status = "paused"
            self._set_safe_command_locked()
            result = self._cycle_status.model_copy()
            events.info(
                "循环测试暂停: 第 %d 圈 第 %d 步",
                result.current_loop,
                result.current_step_index + 1,
            )
        self._broadcast_telemetry()
        return result

    async def resume_cycle_test(self) -> CycleTestStatus:
        """重新下发当前步骤并继续后端计时。"""
        async with self._lock:
            if self._cycle_status.status != "paused":
                raise CanDriverError("当前没有可继续的循环测试。")
            if not self._connected or self._is_emergency_locked:
                self._finish_cycle_locked("stopped", error="CAN 已断开或系统处于急停锁定状态。")
                raise CanDriverError("CAN 已断开或系统处于急停锁定状态。")
            self._apply_cycle_step_locked()
            self._cycle_status.status = "running"
            result = self._cycle_status.model_copy()
            events.info("循环测试继续")
        self._broadcast_telemetry()
        return result

    async def stop_cycle_test(self) -> CycleTestStatus:
        """主动终止循环测试并释放控制权。"""
        async with self._lock:
            was_active = self._cycle_status.status in {"running", "paused"}
            self._finish_cycle_locked("stopped")
            result = self._cycle_status.model_copy()
        if was_active:
            events.info("循环测试被操作员终止: 已用时 %d s", result.total_elapsed_seconds)
        self._broadcast_telemetry()
        return result

    async def _cycle_loop(self, generation: int) -> None:
        """使用服务端单调时钟驱动循环，不受浏览器后台节流影响。"""
        last_tick = time.monotonic()
        last_visible_remaining = self._cycle_status.step_remaining_seconds
        try:
            while True:
                await asyncio.sleep(0.1)
                should_broadcast = False
                async with self._lock:
                    if generation != self._cycle_generation:
                        return
                    if self._cycle_status.status == "paused":
                        last_tick = time.monotonic()
                        continue
                    if self._cycle_status.status != "running":
                        return

                    now = time.monotonic()
                    elapsed = max(0.0, now - last_tick)
                    last_tick = now
                    self._cycle_step_remaining = max(
                        0.0,
                        self._cycle_step_remaining - elapsed,
                    )
                    self._cycle_elapsed += elapsed
                    self._cycle_status.step_remaining_seconds = math.ceil(
                        self._cycle_step_remaining
                    )
                    self._cycle_status.total_elapsed_seconds = int(self._cycle_elapsed)

                    if self._cycle_status.step_remaining_seconds != last_visible_remaining:
                        last_visible_remaining = self._cycle_status.step_remaining_seconds
                        should_broadcast = True

                    if self._cycle_step_remaining <= 0:
                        if self._cycle_config is None:
                            raise CanDriverError("循环测试配置丢失。")
                        next_index = self._cycle_status.current_step_index + 1
                        if next_index >= len(self._cycle_config.steps):
                            if self._cycle_status.current_loop >= self._cycle_status.total_loops:
                                self._finish_cycle_locked("completed")
                                events.info(
                                    "循环测试完成: %d 圈，用时 %d s",
                                    self._cycle_status.total_loops,
                                    self._cycle_status.total_elapsed_seconds,
                                )
                                should_broadcast = True
                            else:
                                self._cycle_status.current_loop += 1
                                self._cycle_status.current_step_index = 0
                        else:
                            self._cycle_status.current_step_index = next_index

                        if self._cycle_status.status == "running":
                            step = self._cycle_config.steps[self._cycle_status.current_step_index]
                            self._cycle_step_remaining = float(step.duration_seconds)
                            self._cycle_status.step_remaining_seconds = step.duration_seconds
                            last_visible_remaining = step.duration_seconds
                            self._apply_cycle_step_locked()
                            should_broadcast = True

                if should_broadcast:
                    self._broadcast_telemetry()
        except asyncio.CancelledError:
            return
        except Exception as err:
            logger.exception("循环测试状态机异常: %s", err)
            events.error("循环测试异常终止: %s", err)
            async with self._lock:
                if generation == self._cycle_generation:
                    self._finish_cycle_locked("error", error=str(err))
            self._broadcast_telemetry()

    async def update_command(self, update: VcuCommandUpdateRequest) -> VcuCommandState:
        """更新 VCU 控制设定值。

        :param update: 包含待更新字段的请求体
        :return: 更新后的完整控制状态
        """
        async with self._lock:
            if self._disconnecting:
                raise CanDriverError("设备正在停止通信，暂不接受新的控制指令。")
            if self._cycle_status.status in {"running", "paused"}:
                raise CanDriverError(
                    "循环测试已取得控制权，手动控制已锁定。请先终止循环测试，或使用急停接口。"
                )
            # 自动判定期间（等待停转 → 判定 → 自动下电）不接受手动指令，避免干扰判定与下电
            if self._cycle_status.auto_judge == "pending":
                raise CanDriverError("循环测试正在自动判定 / 下电，手动控制暂时锁定，请稍候。")

            # 急停互锁保护：急停状态下禁止使能或写入非零控制量
            if self._is_emergency_locked:
                if (
                    (update.mcu_en_cmd is not None and update.mcu_en_cmd != 0)
                    or (update.torque_req is not None and update.torque_req != 0.0)
                    or (update.speed_req is not None and update.speed_req != 0)
                ):
                    raise CanDriverError(
                        "系统处于急停锁定状态，禁止使能或设置非零控制量。"
                        "请先调用 /emergency-reset 复位后再操作。"
                    )

            # 操作员的新指令优先于正在进行的平稳停机。
            self._cancel_soft_stop_locked()
            self._apply_update_locked(update)
            result = self._command.model_copy()

        self._broadcast_telemetry()
        return result

    async def emergency_stop(self, *, reason: str | None = None) -> VcuCommandState:
        """一键紧急停机 (Emergency Stop)。

        立即将使能置 0、目标转矩/转速归零、挂入空挡，并立即强制发送一帧控制报文。

        :param reason: 触发原因，缺省为操作员手动触发；写入安全事件日志
        """
        async with self._lock:
            self._cancel_soft_stop_locked()
            self._finish_cycle_locked(
                "stopped",
                error=f"急停已触发：{reason or '操作员手动急停'}",
                abnormal=True,
            )
            self._is_emergency_locked = True

            # 如果当前通道有效，立即同步下发紧急制动帧
            if self._connected:
                self._command.life = (self._command.life + 1) % 16
                payload = encode_vcu_11(
                    torque_req=0.0,
                    speed_req=0,
                    work_mode_req=self._command.work_mode_req,
                    mcu_en_cmd=0,
                    gear_sts=3,
                    life=self._command.life,
                )
                for ch in self._channels():
                    if self._driver.is_channel_open(ch):
                        try:
                            s = await self._driver.transmit(
                                can_id=CAN_ID_VCU_11,
                                data=payload,
                                channel=ch,
                            )
                            if s:
                                self._tx_frame_count += 1
                            else:
                                self._tx_error_count += 1
                        except Exception as err:
                            self._tx_error_count += 1
                            logger.error("紧急停机报文下发失败 (通道 %d): %s", ch, err)

            events.warning("紧急停机: %s", reason or "操作员手动触发")
            result = self._command.model_copy()

        self._notify_emergency_listeners(reason or "操作员手动急停")
        self._broadcast_telemetry()
        return result

    # ------------------------------------------------------------------
    # 与 PLC 上电控制的联动
    # ------------------------------------------------------------------
    def add_emergency_listener(self, listener: EmergencyListener) -> None:
        """注册急停 / 链路故障联动（例如 PLC 复位上电请求）。"""
        self._emergency_listeners.append(listener)

    def add_cycle_finished_listener(self, listener: CycleFinishedListener) -> None:
        """注册循环测试跑完 / 异常中断后的联动（自动判定、自动下电）。"""
        self._cycle_finished_listeners.append(listener)

    def _spawn_listener(self, coro: Coroutine[Any, Any, None], *, name: str) -> None:
        """在后台执行联动，不阻塞调用方（急停接口、循环状态机）。"""
        task = asyncio.create_task(coro, name=name)
        self._listener_tasks.add(task)
        task.add_done_callback(self._listener_tasks.discard)

    def _notify_emergency_listeners(self, reason: str) -> None:
        """在后台执行联动，不让 PLC 通讯拖慢急停接口的返回。"""
        for listener in self._emergency_listeners:
            self._spawn_listener(listener(reason), name="axle_emergency_listener")

    def judge_blocker(self) -> str | None:
        """手动判定前的放行检查；返回拒绝原因，None 表示允许。"""
        if self._cycle_status.status in {"running", "paused"}:
            return "循环测试正在执行，结束后会自动判定"
        if self._cycle_status.auto_judge == "pending":
            return "循环测试正在自动判定 / 下电，请稍候"
        if self._manual_judging:
            return "试车判定正在保存，请勿重复提交"
        return None

    def begin_manual_judge(self) -> str | None:
        """检查并占用手动判定；返回拒绝原因，None 表示已占用，结束后必须调用 end_manual_judge。

        检查与置位之间没有 await，与 start_cycle_test 的检查互斥。
        """
        blocker = self.judge_blocker()
        if blocker is None:
            self._manual_judging = True
        return blocker

    def end_manual_judge(self) -> None:
        self._manual_judging = False

    async def report_auto_judge(self, result: int | None, message: str) -> None:
        """自动判定流程结束后回写结论，通过遥测推送给界面。"""
        async with self._lock:
            self._cycle_status.auto_judge = "done"
            self._cycle_status.auto_judge_result = result  # type: ignore[assignment]
            self._cycle_status.auto_judge_message = message
        self._broadcast_telemetry()

    async def wait_motor_stopped(self, timeout_s: float) -> bool:
        """等待实际转速降到停稳阈值内；CAN 未连接或超时仍未停稳返回 False。"""
        deadline = time.monotonic() + timeout_s
        while True:
            if not self._connected:
                return False
            received_at = self._mcu_2_last_rx_timestamp
            if (
                received_at is not None
                and time.time() - received_at <= MCU_2_SAFETY_FRESHNESS_SECONDS
                and abs(self._mcu_2.mcu_act_motor_spd) <= SOFT_STOP_SPEED_THRESHOLD_RPM
            ):
                return True
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(SOFT_STOP_POLL_SECONDS)

    def power_on_blocker(self) -> str | None:
        """PLC 上电前的放行检查；返回拒绝原因，None 表示允许。

        急停互锁不阻止上电：互锁期间电机无法使能，上高压不会让电机转动。
        """
        if self._cycle_status.status in {"running", "paused"}:
            return "循环测试正在执行，请先终止循环测试"
        if self._connected and self._command.mcu_en_cmd == 1:
            return "电机仍处于使能状态，请先停机并关闭使能"
        return None

    def mes_telemetry(self) -> tuple[float, float]:
        """上传 MES 的 (实际转速 rpm, 电机温度 ℃)；CAN 未连接或反馈过期的一项给 0。"""
        if not self._connected:
            return 0.0, 0.0
        now = time.time()
        speed = 0.0
        if (
            self._mcu_2_last_rx_timestamp is not None
            and now - self._mcu_2_last_rx_timestamp <= MES_FEEDBACK_STALE_SECONDS
        ):
            speed = float(self._mcu_2.mcu_act_motor_spd)
        temp = 0.0
        if (
            self._mcu_tbox_last_rx_timestamp is not None
            and now - self._mcu_tbox_last_rx_timestamp <= MES_FEEDBACK_STALE_SECONDS
        ):
            temp = float(self._mcu_tbox.mcu_motor_temp)
        return speed, temp

    async def disable_for_power_off(
        self, motor_stop_timeout_s: float = POWER_OFF_MOTOR_STOP_TIMEOUT_SECONDS
    ) -> str | None:
        """PLC 下电前：结束循环测试与平稳停机，关闭使能并等待安全帧发出。

        有新鲜转速反馈且电机仍在转时，最多等待 motor_stop_timeout_s 让其停稳；
        超时不阻止下电，返回提示文字。没有转速反馈（CAN 未连接、控制器不在线）时不等待。
        """
        async with self._lock:
            if not self._connected:
                return None
            self._cancel_soft_stop_locked()
            if self._cycle_status.status in {"running", "paused"}:
                self._finish_cycle_locked("stopped", error="PLC 下电")
            was_enabled = self._command.mcu_en_cmd == 1
            self._set_safe_command_locked()
        self._broadcast_telemetry()
        # 10 ms 循环至少连续发出几帧“不使能、零转速、N 挡”后再切断高压
        await asyncio.sleep(TX_INTERVAL_SECONDS * 5)
        if was_enabled:
            events.info("PLC 下电前已关闭电机使能")

        deadline = time.monotonic() + motor_stop_timeout_s
        while True:
            received_at = self._mcu_2_last_rx_timestamp
            if (
                not self._connected
                or received_at is None
                or time.time() - received_at > MCU_2_SAFETY_FRESHNESS_SECONDS
                or abs(self._mcu_2.mcu_act_motor_spd) <= SOFT_STOP_SPEED_THRESHOLD_RPM
            ):
                return None
            if time.monotonic() >= deadline:
                speed = self._mcu_2.mcu_act_motor_spd
                events.warning("PLC 下电前等待电机停稳超时，当前转速 %d rpm", speed)
                return f"等待 {motor_stop_timeout_s:g} s 电机仍未停稳（{speed} rpm）"
            await asyncio.sleep(SOFT_STOP_POLL_SECONDS)

    async def external_safety_trip(self, metric: SafetyMetric, message: str) -> None:
        """外部安全条件（如 PLC Safe 断开）触发的自动停机：记录事件并急停。"""
        self.test_session.on_safety_trip()
        self._safety_trip_id += 1
        self._safety_last_trip = AxleSafetyTrip(
            trip_id=self._safety_trip_id,
            metric=metric,
            actual_value=0,
            threshold=0,
            unit="",
            message=message,
            triggered_at=datetime.now(UTC).isoformat(),
        )
        await self.emergency_stop(reason=f"自动安全停机 — {message}")

    @property
    def is_soft_stopping(self) -> bool:
        """平稳停机流程是否正在等待电机减速。"""
        return self._soft_stop_task is not None and not self._soft_stop_task.done()

    def _cancel_soft_stop_locked(self) -> None:
        """在状态锁内终止平稳停机（新指令、急停、断开或循环测试接管时调用）。"""
        task = self._soft_stop_task
        self._soft_stop_task = None
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()

    async def soft_stop(self) -> VcuCommandState:
        """平稳停机：目标归零让控制器主动减速，转速降到阈值内后自动关闭使能并切 N 挡。

        与急停不同，不进入互锁，停机完成后可直接重新操作。
        """
        async with self._lock:
            if not self._connected:
                raise CanDriverError("CAN 未连接，无法执行停机。")
            if self._disconnecting:
                raise CanDriverError("设备正在停止通信。")
            if self._cycle_status.status in {"running", "paused"}:
                raise CanDriverError("循环测试正在执行，请使用“终止并归零”。")

            self._cancel_soft_stop_locked()
            self._command.torque_req = 0.0
            self._command.speed_req = 0
            if self._command.mcu_en_cmd == 1:
                self._soft_stop_task = asyncio.create_task(
                    self._soft_stop_loop(),
                    name="axle_soft_stop",
                )
            else:
                # 未使能时电机不会被驱动，直接切到 N 挡即可。
                self._command.gear_sts = 3
            result = self._command.model_copy()

        events.info("平稳停机: 目标转速/转矩已归零，等待电机减速")
        self._broadcast_telemetry()
        return result

    async def _soft_stop_loop(self) -> None:
        """等待实际转速降到阈值内（或超时）后关闭使能并切 N 挡。"""
        deadline = time.monotonic() + SOFT_STOP_TIMEOUT_SECONDS
        try:
            while True:
                await asyncio.sleep(SOFT_STOP_POLL_SECONDS)
                async with self._lock:
                    if self._soft_stop_task is not asyncio.current_task():
                        return
                    received_at = self._mcu_2_last_rx_timestamp
                    has_fresh_feedback = (
                        received_at is not None
                        and time.time() - received_at <= MCU_2_SAFETY_FRESHNESS_SECONDS
                    )
                    stopped = (
                        has_fresh_feedback
                        and abs(self._mcu_2.mcu_act_motor_spd) <= SOFT_STOP_SPEED_THRESHOLD_RPM
                    )
                    timed_out = time.monotonic() >= deadline
                    if not (stopped or timed_out):
                        continue
                    self._command.mcu_en_cmd = 0
                    self._command.gear_sts = 3
                    self._soft_stop_task = None
                break
        except asyncio.CancelledError:
            return

        if stopped:
            events.info("平稳停机完成: 电机已停稳，使能已关闭")
        else:
            events.warning(
                "平稳停机超时 (%.0f s)，已强制关闭使能，电机将自由滑行",
                SOFT_STOP_TIMEOUT_SECONDS,
            )
        self._broadcast_telemetry()

    async def emergency_reset(self) -> VcuCommandState:
        """复位急停互锁状态 (Emergency Reset)。

        仅解除互锁标志，不会自动恢复使能或停机前的控制量：命令始终停留在使能关闭、
        目标转矩/转速归零、空挡的安全状态，必须由操作员重新下发。操作员确认现场安全
        后手动调用。越限原因未消除时，下一次新鲜 MCU 反馈会立即再次触发自动停机。

        :return: 复位后的完整控制状态 (仍为安全值)
        """
        async with self._lock:
            was_locked = self._is_emergency_locked
            self._is_emergency_locked = False
            if was_locked:
                # 保持“互锁解除后命令仍为安全值”的不变量，杜绝残留非零给定在解除
                # 瞬间被 10ms 循环带出。
                self._set_safe_command_locked()
            result = self._command.model_copy()

        if was_locked:
            events.info("急停互锁已复位，控制量保持安全值")

        self._broadcast_telemetry()
        return result

    @property
    def is_emergency_locked(self) -> bool:
        """急停互锁状态。"""
        return self._is_emergency_locked

    # ------------------------------------------------------------------
    # 安全监控
    # ------------------------------------------------------------------
    def get_safety_config(self) -> AxleSafetyConfig:
        """获取当前上位机自动停机配置快照。"""
        return self._safety_config.model_copy()

    async def update_safety_config(
        self,
        config: AxleSafetyConfig,
    ) -> AxleSafetyConfig:
        """更新自动停机阈值并持久化。

        保存配置本身不使用历史遥测立即触发急停；后续收到新鲜的 0x35B 或
        0x35C 反馈时，才会按新配置执行安全判断。新配置先在内存中生效，
        写盘失败时抛出 ``OSError`` 由接口层告知操作员。
        """
        async with self._lock:
            self._safety_config = config.model_copy()
            result = self._safety_config.model_copy()

        events.info(
            "安全配置已更新: 启用=%s 转速=%d RPM 转矩=%g Nm 温度=%g ℃ 反馈超时=%d ms",
            result.enabled,
            result.max_motor_speed_rpm,
            result.max_motor_torque_nm,
            result.max_motor_temp_c,
            result.feedback_timeout_ms,
        )
        self._broadcast_telemetry()
        await asyncio.to_thread(save_safety_config, self._safety_config_path, result)
        return result

    def _find_safety_violation(self) -> _SafetyViolation | None:
        """从新鲜 MCU 反馈中寻找第一项越限条件。

        转速和转矩使用绝对值，因此正反转与驱动/回馈转矩都会受同一阈值保护。
        电机温度只使用 0x35C 的 ``MCU_MotorTemp``，不以默认值或历史值判定。
        """
        config = self._safety_config
        if not config.enabled or self._is_emergency_locked:
            return None

        now = time.time()
        if (
            self._mcu_2_last_rx_timestamp is not None
            and now - self._mcu_2_last_rx_timestamp <= MCU_2_SAFETY_FRESHNESS_SECONDS
        ):
            actual_speed = float(abs(self._mcu_2.mcu_act_motor_spd))
            if actual_speed > config.max_motor_speed_rpm:
                return _SafetyViolation(
                    "motor_speed",
                    actual_speed,
                    float(config.max_motor_speed_rpm),
                    "RPM",
                )

            actual_torque = abs(self._mcu_2.mcu_act_motor_tq)
            if actual_torque > config.max_motor_torque_nm:
                return _SafetyViolation(
                    "motor_torque",
                    actual_torque,
                    config.max_motor_torque_nm,
                    "Nm",
                )

        if (
            self._mcu_tbox_last_rx_timestamp is not None
            and now - self._mcu_tbox_last_rx_timestamp <= MCU_TBOX_SAFETY_FRESHNESS_SECONDS
        ):
            actual_temperature = float(self._mcu_tbox.mcu_motor_temp)
            if actual_temperature > config.max_motor_temp_c:
                return _SafetyViolation(
                    "motor_temperature",
                    actual_temperature,
                    config.max_motor_temp_c,
                    "℃",
                )

        return None

    def _find_feedback_timeout(self) -> _SafetyViolation | None:
        """使能状态下 MCU_2 (0x35B) 反馈中断看门狗。

        越限判定只在收到反馈时运行，若 MCU 掉线或总线断开，转速/转矩保护将失效；
        因此在使能期间持续检查 0x35B 的新鲜度，以“使能时刻”与“最近一次反馈”中
        较晚者为基准，超时即视为失去闭环监控。
        """
        if self._command.mcu_en_cmd != 1:
            self._enable_since = None
            return None

        now = time.time()
        if self._enable_since is None:
            self._enable_since = now

        config = self._safety_config
        if not config.enabled or self._is_emergency_locked or self._disconnecting:
            return None

        reference = max(self._enable_since, self._mcu_2_last_rx_timestamp or 0.0)
        elapsed_ms = (now - reference) * 1000
        if elapsed_ms > config.feedback_timeout_ms:
            return _SafetyViolation(
                "feedback_timeout",
                round(elapsed_ms),
                float(config.feedback_timeout_ms),
                "ms",
            )
        return None

    async def _trip_safety(self, violation: _SafetyViolation) -> None:
        """记录自动停机事件并调用既有急停互锁。"""
        self.test_session.on_safety_trip()
        label = SAFETY_METRIC_LABELS[violation.metric]
        if violation.metric == "feedback_timeout":
            message = (
                f"使能状态下 {label} {violation.actual_value:g} ms，"
                f"超过自动停机阈值 {violation.threshold:g} ms。"
            )
        else:
            message = (
                f"{label} {violation.actual_value:g} {violation.unit} 超过自动停机阈值 "
                f"{violation.threshold:g} {violation.unit}。"
            )
        self._safety_trip_id += 1
        self._safety_last_trip = AxleSafetyTrip(
            trip_id=self._safety_trip_id,
            metric=violation.metric,
            actual_value=violation.actual_value,
            threshold=violation.threshold,
            unit=violation.unit,
            message=message,
            triggered_at=datetime.now(UTC).isoformat(),
        )
        # 复用统一急停路径，确保互锁、零转矩/零转速、空挡和立即发送逻辑一致。
        await self.emergency_stop(reason=f"自动安全停机 — {message}")

    async def _evaluate_safety(self) -> bool:
        """若任一已配置指标越限，记录事件并急停。"""
        violation = self._find_safety_violation()
        if violation is None:
            return False
        await self._trip_safety(violation)
        return True

    async def _evaluate_feedback_watchdog(self) -> bool:
        """若使能期间 MCU 反馈中断超时，记录事件并急停。"""
        violation = self._find_feedback_timeout()
        if violation is None:
            return False
        await self._trip_safety(violation)
        return True

    # ------------------------------------------------------------------
    # 报文监视与遥测快照
    # ------------------------------------------------------------------
    def _record_frame(
        self,
        *,
        direction: str,
        can_id: int,
        data: bytes,
        name: str = "",
    ) -> None:
        """内部记录单条 CAN 报文至循环缓冲区 (仅存原始字段，避免高频构造模型)。"""
        self._frame_sequence += 1
        self._recent_frames.append(
            _FrameRecord(
                sequence=self._frame_sequence,
                wall_time=time.time(),
                direction=direction,
                can_id=can_id,
                data=data,
                name=name,
            )
        )

    @staticmethod
    def _frame_item(record: _FrameRecord) -> CanFrameItem:
        """将缓冲区记录转换为对外报文模型 (字段由内部生成，跳过重复校验)。"""
        moment = datetime.fromtimestamp(record.wall_time)
        return CanFrameItem.model_construct(
            sequence=record.sequence,
            timestamp=f"{moment:%H:%M:%S}.{moment.microsecond // 1000:03d}",
            direction=record.direction,
            can_id=record.can_id,
            can_id_hex=f"0x{record.can_id:03X}",
            dlc=len(record.data),
            data_hex=record.data.hex(" ").upper(),
            name=record.name,
        )

    async def send_raw_frame(self, request: CanSendRawFrameRequest) -> bool:
        """手动下发单帧 CAN 测试或诊断报文。

        :param request: 包含目标 ID、16进制数据载荷及扩展帧标志的请求对象
        :return: 硬件发送是否成功
        """
        async with self._lock:
            if not self._connected:
                raise CanDriverError("USBCAN 硬件未连接，无法下发报文。")
            if (
                self._cycle_status.status in {"running", "paused"}
                or self._cycle_status.auto_judge == "pending"
            ) and request.can_id == CAN_ID_VCU_11:
                raise CanDriverError(
                    "循环测试运行或自动判定期间禁止手动下发 VCU_11 (0x258) 控制帧。"
                )
            if self._is_emergency_locked and request.can_id == CAN_ID_VCU_11:
                raise CanDriverError(
                    "系统处于急停锁定状态，禁止手动下发 VCU_11 (0x258) 控制帧。请先完成复位。"
                )

            valid_channels = [ch for ch in self._channels() if self._driver.is_channel_open(ch)]

            if not valid_channels:
                raise CanDriverError("当前通道未开启，无法下发报文。")

            cleaned = "".join(request.data_hex.split())
            try:
                payload = bytes.fromhex(cleaned)
            except ValueError as err:
                raise ValueError(f"16进制数据格式无效: {request.data_hex}") from err

            if len(payload) > 8:
                raise ValueError("标准 CAN 报文载荷长度 (DLC) 不能超过 8 字节。")

            any_success = False
            for ch in valid_channels:
                try:
                    s = await self._driver.transmit(
                        can_id=request.can_id,
                        data=payload,
                        channel=ch,
                        is_extended=request.is_extended,
                        is_remote=request.is_remote,
                    )
                    if s:
                        self._tx_frame_count += 1
                        any_success = True
                    else:
                        self._tx_error_count += 1
                except Exception as err:
                    self._tx_error_count += 1
                    logger.warning("CAN 原始报文发送异常 (通道 %d): %s", ch, err)

            if any_success:
                self._record_frame(
                    direction="TX",
                    can_id=request.can_id,
                    data=payload,
                    name=f"MANUAL_0x{request.can_id:X}",
                )
            return any_success

    def clear_frames(self) -> None:
        """清空最近报文监控缓冲区。"""
        self._recent_frames.clear()
        self._broadcast_telemetry()

    def get_telemetry(
        self,
        *,
        include_frames: bool = True,
        frame_limit: int | None = None,
    ) -> AxleTelemetry:
        """获取当前电驱桥系统最新遥测快照。"""
        now_str = datetime.now(UTC).isoformat()
        recent_frames: list[CanFrameItem] = []
        if include_frames:
            records = list(self._recent_frames)
            if frame_limit is not None:
                records = records[-frame_limit:]
            recent_frames = [self._frame_item(record) for record in records]

        return AxleTelemetry(
            connected=self._connected,
            is_transmitting=self._is_transmitting,
            is_emergency_locked=self._is_emergency_locked,
            device_type=self._device_type,
            device_index=self._device_index,
            channel=self._channel,
            baud_rate=self._baud_rate,
            command=self._command.model_copy(),
            cycle_test=self._cycle_status.model_copy(),
            mcu_1=self._mcu_1.model_copy(),
            mcu_1_last_rx_timestamp=self._mcu_1_last_rx_timestamp,
            mcu_2=self._mcu_2.model_copy(),
            mcu_2_last_rx_timestamp=self._mcu_2_last_rx_timestamp,
            mcu_tbox=self._mcu_tbox.model_copy(),
            mcu_tbox_last_rx_timestamp=self._mcu_tbox_last_rx_timestamp,
            safety=AxleSafetyStatus(
                config=self._safety_config.model_copy(),
                last_trip=(
                    self._safety_last_trip.model_copy()
                    if self._safety_last_trip is not None
                    else None
                ),
            ),
            soft_stopping=self.is_soft_stopping,
            link_error=self._link_error,
            bus_warning=self._bus_warning,
            driver_error=self._driver_error,
            tx_frame_count=self._tx_frame_count,
            rx_frame_count=self._rx_frame_count,
            tx_error_count=self._tx_error_count,
            last_rx_timestamp=self._last_rx_timestamp,
            recent_frames=recent_frames,
            updated_at=now_str,
        )

    def subscribe(self, *, include_frames: bool = False) -> asyncio.Queue[AxleTelemetry]:
        """注册 SSE 遥测流订阅队列。"""
        queue: asyncio.Queue[AxleTelemetry] = asyncio.Queue(maxsize=30)
        self._subscribers[queue] = include_frames
        return queue

    def unsubscribe(self, queue: asyncio.Queue[AxleTelemetry]) -> None:
        """注销 SSE 遥测流订阅队列。"""
        self._subscribers.pop(queue, None)

    def _broadcast_telemetry(self) -> None:
        """向所有已连接的 SSE 客户端广播最新数据快照。"""
        if not self._subscribers:
            return

        snapshots: dict[bool, AxleTelemetry] = {}
        dead_queues: list[asyncio.Queue[AxleTelemetry]] = []

        for q, include_frames in tuple(self._subscribers.items()):
            try:
                snapshot = snapshots.get(include_frames)
                if snapshot is None:
                    snapshot = self.get_telemetry(
                        include_frames=include_frames,
                        frame_limit=STREAM_FRAME_LIMIT if include_frames else None,
                    )
                    snapshots[include_frames] = snapshot

                # 若队列已满，弹出最旧项以保证前端展示最新数据
                if q.full():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                q.put_nowait(snapshot)
            except Exception:
                dead_queues.append(q)

        for q in dead_queues:
            self._subscribers.pop(q, None)

    async def shutdown(self) -> None:
        """系统退出时释放所有硬件连接并关闭驱动线程池。"""
        async with self._lifecycle_lock:
            if self._connected:
                await self._disconnect()
                events.info("程序退出，已发送停机帧并断开 CAN")
        link_task = self._link_failure_task
        if link_task is not None and not link_task.done():
            link_task.cancel()
            try:
                await link_task
            except asyncio.CancelledError:
                pass
        self._driver.shutdown_executor()

    # ------------------------------------------------------------------
    # 周期收发循环
    # ------------------------------------------------------------------
    async def _tx_loop(self) -> None:
        """VCU_11 10ms 高精度定时循环发送任务。

        按照通讯矩阵严格以 10ms 周期向驱动电机控制器 (MCU) 发送控制信号。
        """
        logger.info("VCU_11 10ms 发送循环已启动。")

        with windows_high_resolution_timer():
            try:
                next_tick = time.perf_counter()
                while self._is_transmitting:
                    # 1. 在锁保护下直接读取标量字段并自增 Life（避免 Pydantic 序列化开销）
                    async with self._lock:
                        self._command.life = (self._command.life + 1) % 16
                        tq = self._command.torque_req
                        spd = self._command.speed_req
                        mode = self._command.work_mode_req
                        en = self._command.mcu_en_cmd
                        gear = self._command.gear_sts
                        life = self._command.life
                        is_shutdown_payload = (
                            self._disconnecting
                            and tq == 0.0
                            and spd == 0
                            and mode == 0
                            and en == 0
                            and gear == 3
                        )

                    # 2. 纯 Python 位运算编码。手刹、制动、ABS、加速踏板与主动放电为整车信号，
                    # 空载台架上固定按无效值 (0) 发送。
                    payload = encode_vcu_11(
                        torque_req=tq,
                        speed_req=spd,
                        work_mode_req=mode,
                        mcu_en_cmd=en,
                        gear_sts=gear,
                        life=life,
                    )

                    # 3. 异步非阻塞发送 (受驱动内部 _tx_lock 保护保证硬件总线时序串行安全)
                    any_success = False
                    for ch in self._channels():
                        source = f"tx{ch}"
                        try:
                            s = await self._driver.transmit(
                                can_id=CAN_ID_VCU_11,
                                data=payload,
                                channel=ch,
                            )
                        except Exception as err:
                            self._tx_error_count += 1
                            self._note_driver_error(source, f"CAN 通道 {ch} 发送", err)
                            continue

                        self._note_driver_success(source)
                        if s:
                            self._tx_frame_count += 1
                            any_success = True
                        else:
                            # 驱动正常返回但硬件未接收：通常为总线无应答或发送缓冲区满。
                            self._tx_error_count += 1
                            self._log_throttled(
                                f"tx_reject{ch}",
                                logging.WARNING,
                                "VCU_11 发送未被硬件接受 (通道 %d)，请检查总线终端电阻与对端节点。",
                                ch,
                            )

                    if any_success:
                        self._record_frame(
                            direction="TX",
                            can_id=CAN_ID_VCU_11,
                            data=payload,
                            name="VCU_11 (控制器指令)",
                        )

                        if is_shutdown_payload:
                            async with self._lock:
                                if self._disconnecting and self._shutdown_frames_remaining > 0:
                                    self._shutdown_frames_remaining -= 1
                                    if self._shutdown_frames_remaining == 0:
                                        self._shutdown_frames_sent.set()

                    # 4. 绝对时间戳推移补偿（防止相位漂移累积）；若因卡顿落后超过一个
                    # 周期则丢弃错过的节拍重新对齐，避免恢复后集中补发一串报文。
                    next_tick += TX_INTERVAL_SECONDS
                    now = time.perf_counter()
                    sleep_duration = next_tick - now
                    if sleep_duration > 0:
                        await asyncio.sleep(sleep_duration)
                    else:
                        if -sleep_duration >= TX_INTERVAL_SECONDS:
                            self._log_throttled(
                                "tx_overrun",
                                logging.WARNING,
                                "VCU_11 发送周期滞后 %.1f ms，已重新对齐节拍。",
                                -sleep_duration * 1000,
                            )
                            next_tick = now
                        await asyncio.sleep(0)
            except asyncio.CancelledError:
                logger.info("VCU_11 发送循环已被取消。")
                raise
            except Exception as tx_err:
                logger.exception("VCU_11 发送循环发生未捕获异常: %s", tx_err)
                self._schedule_link_failure(f"VCU_11 发送循环异常终止: {tx_err}")

    async def _rx_loop(self) -> None:
        """CAN 报文接收与分发任务。

        以 5ms 周期轮询周立功硬件缓冲区，支持突发报文批量读取与即时解码；
        每轮同时执行反馈看门狗并按固定节拍推送 SSE 快照。
        """
        logger.info("CAN 接收循环已启动。")
        last_broadcast_time = time.perf_counter()

        try:
            while self._is_transmitting:
                # 批量接收硬件缓冲区中的报文
                frames: list[CanRawFrame] = []
                for ch in self._channels():
                    source = f"rx{ch}"
                    try:
                        ch_frames = await self._driver.receive(
                            channel=ch,
                            max_count=100,
                            wait_time_ms=1,
                        )
                    except Exception as err:
                        self._note_driver_error(source, f"CAN 通道 {ch} 接收", err)
                        continue
                    self._note_driver_success(source)
                    if ch_frames:
                        frames.extend(ch_frames)

                if frames:
                    await self._process_frames(frames)

                await self._evaluate_feedback_watchdog()

                # 固定节拍推送 (约 20Hz)：无报文时也保证计数器、指令与连接状态实时可见。
                now = time.perf_counter()
                if now - last_broadcast_time >= BROADCAST_INTERVAL_SECONDS:
                    self._broadcast_telemetry()
                    last_broadcast_time = now

                await asyncio.sleep(RX_POLL_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("CAN 接收循环已被取消。")
            raise
        except Exception as rx_err:
            logger.exception("CAN 接收循环发生未捕获异常: %s", rx_err)
            self._schedule_link_failure(f"CAN 接收循环异常终止: {rx_err}")

    async def _process_frames(self, frames: list[CanRawFrame]) -> None:
        """解码一批接收报文并在安全相关反馈更新后执行越限判定。"""
        self._rx_frame_count += len(frames)
        self._last_rx_timestamp = time.time()

        for frame in frames:
            # 仅处理有效的数据帧 (8 字节)
            if len(frame.data) < 8:
                continue

            frame_name = f"CAN_0x{frame.can_id:X}"
            # 使用 Python 3.10+ match-case 分发对应报文解码
            safety_feedback_updated = False
            try:
                match frame.can_id:
                    case 0x35A:  # CAN_ID_MCU_DRIVE_MOTOR_1
                        frame_name = "MCU_1 (母线电气/故障)"
                        d1 = decode_mcu_motor_1(frame.data)
                        self._mcu_1 = McuDriveMotor1Telemetry(
                            mcu_dc_main_wire_volt=d1.mcu_dc_main_wire_volt,
                            mcu_dc_main_wire_curr=d1.mcu_dc_main_wire_curr,
                            mcu_integ_ctr_flt_num=d1.mcu_integ_ctr_flt_num,
                            mcu_flt_code=d1.mcu_flt_code,
                            mcu_flt_levl=d1.mcu_flt_levl,
                            mcu_life_1=d1.mcu_life_1,
                            mcu_tbox_flt_levl=d1.mcu_tbox_flt_levl,
                        )
                        self._mcu_1_last_rx_timestamp = time.time()
                        self.test_session.on_mcu_1(
                            bus_current_a=d1.mcu_dc_main_wire_curr, fault_code=d1.mcu_flt_code
                        )

                    case 0x35B:  # CAN_ID_MCU_DRIVE_MOTOR_2
                        frame_name = "MCU_2 (电机转速/转矩)"
                        d2 = decode_mcu_motor_2(frame.data)
                        self._mcu_2 = McuDriveMotor2Telemetry(
                            mcu_motor_tor_max=d2.mcu_motor_tor_max,
                            mcu_act_motor_spd=d2.mcu_act_motor_spd,
                            mcu_act_motor_tq=d2.mcu_act_motor_tq,
                            mcu_motor_work_mod=d2.mcu_motor_work_mod,
                            mcu_lv_sts=d2.mcu_lv_sts,
                            mcu_en_sts=d2.mcu_en_sts,
                            mcu_motor_temp_extre_over=d2.mcu_motor_temp_extre_over,
                            mcu_mcu_temp_extre_over=d2.mcu_mcu_temp_extre_over,
                            mcu_life_2=d2.mcu_life_2,
                        )
                        self._mcu_2_last_rx_timestamp = time.time()
                        self.test_session.on_mcu_2(
                            speed_rpm=d2.mcu_act_motor_spd, torque_nm=d2.mcu_act_motor_tq
                        )
                        safety_feedback_updated = True

                    case 0x35C:  # CAN_ID_MCU_TBOX_DRIVE_MOTOR
                        frame_name = "MCU_Tbox (温度热管理)"
                        dt = decode_mcu_tbox_motor(frame.data)
                        self._mcu_tbox = McuTboxTelemetry(
                            num_mtr=dt.num_mtr,
                            num_mtr_srl=dt.num_mtr_srl,
                            st_mtr=dt.st_mtr,
                            mcu_motor_temp=dt.mcu_motor_temp,
                            mcu_ctller_temp=dt.mcu_ctller_temp,
                            mcu_tbox_life=dt.mcu_tbox_life,
                        )
                        self._mcu_tbox_last_rx_timestamp = time.time()
                        self.test_session.on_temperature(
                            motor_temp_c=dt.mcu_motor_temp, controller_temp_c=dt.mcu_ctller_temp
                        )
                        safety_feedback_updated = True

                    case 0x5EF:  # CAN_ID_MCU_SV
                        frame_name = "MCU_SV (版本信息)"

                    case 0x251:  # CAN_ID_ONEBOX_ESC_TSC1
                        frame_name = "Onebox_ESC_TSC1 (牵引控制)"

                    case 0x254:  # CAN_ID_ONEBOX_ESC_ENERGYRECOVERY
                        frame_name = "Onebox_ESC_EnergyRecovery (能量回收)"

                    case _:
                        # 其他未知或未配置的 CAN 报文
                        pass
            except Exception as decode_err:
                self._log_throttled(
                    f"decode{frame.can_id:X}",
                    logging.WARNING,
                    "解码 CAN 报文失败 (ID=0x%X, len=%d): %s",
                    frame.can_id,
                    len(frame.data),
                    decode_err,
                )

            self._record_frame(
                direction="RX",
                can_id=frame.can_id,
                data=frame.data,
                name=frame_name,
            )

            if safety_feedback_updated:
                await self._evaluate_safety()


# 全局单例管理器
_global_axle_manager: AxleManager | None = None


def peek_axle_manager() -> AxleManager | None:
    """返回已创建的单例；尚未创建时返回 None，不会触发驱动加载。"""
    return _global_axle_manager


def get_axle_manager() -> AxleManager:
    """获取电驱桥系统单例管理器实例。"""
    global _global_axle_manager
    if _global_axle_manager is None:
        _global_axle_manager = AxleManager(
            safety_config_path=get_settings().safety_config_path,
        )
    return _global_axle_manager
