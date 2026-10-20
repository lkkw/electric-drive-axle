"""PLC 自动上电 / 下电与安全联锁（1 号工位，340 V）。

流程与 magmit 项目一致（详见 docs/技术文档.md）：

- 上电：确认 Safe=1 → 一次写入 22 字节控制区（Request_power=1、产品编号 1、
  电压 340 V，其余清零）→ 每 0.2 s 轮询，最长 30 s 等到 Power_on=1 且 Connect=1；
  超时由后端自己复位 Request_power。
- 下电：先关闭电机使能（电机仍在转时最多等 10 s 停稳）→ Request_power=0 →
  最长 5 s 确认 Power_on、Connect 均为 0。
- 常驻监视（0.2 s）：已请求上电或已通电时 Safe=0 → 复位 Request_power 并触发急停。
- 心跳：每秒翻转上位机心跳，检测 PLC 心跳跳变；只用于显示。
- MES 上传：常驻监视中把电机实际转速 (rpm)、电机温度 (℃) 写入 Speed / Temp，
  与 PLC 中的值不同时才写；CAN 未连接或反馈过期时写 0。
- 反向联动：电驱桥急停或 CAN 链路故障时，立即复位 Request_power 切断高压。
- PLC 读写全部在一个专用单线程里按提交顺序执行：调用超时后已提交的写入仍会执行，
  但一定排在随后提交的复位之前，不会出现“复位先写、迟到的上电请求后写”。
"""

import asyncio
import concurrent.futures
import logging
import math
import os
import struct
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from app.core.config import get_settings
from app.core.logging_setup import EVENT_LOGGER_NAME
from app.core.plc.client import (
    PlcClientError,
    SimulatedStationClient,
    SnapStationClient,
    StationClient,
)
from app.core.plc.points import (
    BIT_PC_HEART,
    BIT_REQUEST_POWER,
    MES_BLOCK_SIZE,
    OFFSET_PC_STATUS,
    OFFSET_RESULT,
    OFFSET_SPEED,
    POWER_ON_BLOCK_SIZE,
    PRODUCT_TYPE_CODE,
    TARGET_VOLTAGE_V,
    StationFeedback,
    build_mes_block,
    build_power_on_block,
    decode_station,
    set_bit,
)
from app.schemas.plc import PlcActionResponse, PlcConfig, PlcStatus, PowerState
from app.services.plc_traffic import PlcTrafficLog, point_names_for_bit

logger = logging.getLogger("app.plc")
events = logging.getLogger(EVENT_LOGGER_NAME)

STATUS_POLL_SECONDS = 0.2
HEARTBEAT_INTERVAL_SECONDS = 1.0
HEARTBEAT_TIMEOUT_SECONDS = 4.0
FEEDBACK_STALE_SECONDS = 1.0
IO_TIMEOUT_SECONDS = 2.0
CONNECT_TIMEOUT_SECONDS = 5.0
POWER_ON_TIMEOUT_SECONDS = 30.0
POWER_OFF_TIMEOUT_SECONDS = 5.0
SAFETY_RESET_RETRY_SECONDS = 1.0
LOG_THROTTLE_SECONDS = 5.0

ClientFactory = Callable[[PlcConfig], StationClient]
SafetyTripHook = Callable[[str], Awaitable[None]]
BeforePowerOffHook = Callable[[], Awaitable[str | None]]  # 返回需要提示操作员的问题
PowerOnBlocker = Callable[[], str | None]
MesTelemetrySource = Callable[[], tuple[float, float]]


class PlcOperationError(Exception):
    """按业务规则拒绝或执行失败的上电 / 下电操作，携带 HTTP 状态码与中文原因。"""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _consume_exception(future: asyncio.Future[Any]) -> None:
    if not future.cancelled() and future.exception() is not None:
        logger.debug("PLC 调用在等待方离开后失败: %s", future.exception())


def default_client_factory(config: PlcConfig) -> StationClient:
    if config.simulation:
        return SimulatedStationClient()
    return SnapStationClient(config.ip, config.rack, config.slot)


def load_plc_config(path: Path | None) -> PlcConfig:
    """读取保存的连接参数；不存在或损坏时使用默认值。本地仿真不随配置记忆，每次启动默认关闭。"""
    if path is None or not path.is_file():
        return PlcConfig()
    try:
        config = PlcConfig.model_validate_json(path.read_text(encoding="utf-8"))
        return config.model_copy(update={"simulation": False})
    except (OSError, ValueError, ValidationError) as err:
        logger.warning("PLC 连接配置 %s 无法读取，已使用默认值: %s", path, err)
        return PlcConfig()


def save_plc_config(path: Path | None, config: PlcConfig) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


class PlcPowerManager:
    """PLC 连接、上电 / 下电编排、Safe 常驻联锁与心跳。"""

    def __init__(
        self,
        *,
        config_path: Path | None = None,
        client_factory: ClientFactory = default_client_factory,
        power_on_timeout_s: float = POWER_ON_TIMEOUT_SECONDS,
        power_off_timeout_s: float = POWER_OFF_TIMEOUT_SECONDS,
        poll_interval_s: float = STATUS_POLL_SECONDS,
        io_timeout_s: float = IO_TIMEOUT_SECONDS,
    ) -> None:
        self._config_path = config_path
        self._config = load_plc_config(config_path)
        self._client_factory = client_factory
        self._power_on_timeout_s = power_on_timeout_s
        self._power_off_timeout_s = power_off_timeout_s
        self._poll_interval_s = poll_interval_s
        self._io_timeout_s = io_timeout_s

        # snap7 Client 不支持并发；单线程执行器同时保证读写按提交顺序生效
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="plc_io"
        )
        # 已超时但仍在执行器里没结束的调用数；大于 0 时常驻监视不再追加读取
        self._stalled_calls = 0

        self._client: StationClient | None = None
        self._connected = False
        self._connection_lock = asyncio.Lock()
        self._monitor_task: asyncio.Task[None] | None = None

        self._feedback: StationFeedback | None = None
        self._feedback_at: float | None = None
        self._communication_error: str | None = None

        self._operation_lock = asyncio.Lock()
        self._operation: Literal["powering_on", "powering_off"] | None = None
        self._abort_power_on = False
        self._last_message: str | None = None

        self._safety_tripped = False
        self._last_safety_reset_attempt = -math.inf
        self._pc_heart = False
        self._last_heart_write = -math.inf
        self._last_plc_heart: bool | None = None
        self._last_plc_heart_change: float | None = None
        self._log_throttle: dict[str, float] = {}

        # PLC 通信监视（联调用）：记录每次写入与 PLC 反馈变化
        self.traffic = PlcTrafficLog()

        self._on_safety_trip: SafetyTripHook | None = None
        self._before_power_off: BeforePowerOffHook | None = None
        self._power_on_blocker: PowerOnBlocker | None = None
        self._mes_telemetry: MesTelemetrySource | None = None

    # ------------------------------------------------------------------
    # 与电驱桥管理器的联动
    # ------------------------------------------------------------------
    def bind_axle(
        self,
        *,
        on_safety_trip: SafetyTripHook,
        before_power_off: BeforePowerOffHook,
        power_on_blocker: PowerOnBlocker,
        mes_telemetry: MesTelemetrySource | None = None,
    ) -> None:
        self._on_safety_trip = on_safety_trip
        self._before_power_off = before_power_off
        self._power_on_blocker = power_on_blocker
        self._mes_telemetry = mes_telemetry

    @property
    def client(self) -> StationClient | None:
        return self._client

    @property
    def config(self) -> PlcConfig:
        return self._config.model_copy()

    # ------------------------------------------------------------------
    # 底层读写
    # ------------------------------------------------------------------
    async def _io(
        self, func: Callable[..., Any], *args: Any, limit_seconds: float | None = None
    ) -> Any:
        """在 PLC 专用线程中执行一次调用。

        超时只结束等待，不取消调用：已排队的写入照常按顺序执行，保证后提交的
        复位一定在其后生效。超时调用结束前计入 ``_stalled_calls``。
        """
        if limit_seconds is None:
            limit_seconds = self._io_timeout_s
        future = asyncio.get_running_loop().run_in_executor(self._executor, func, *args)
        # 等待方超时或被取消后没人再取结果：取走异常，避免“exception was never retrieved”
        future.add_done_callback(_consume_exception)
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=limit_seconds)
        except TimeoutError as err:
            self._stalled_calls += 1
            future.add_done_callback(self._on_stalled_call_done)
            raise PlcClientError(f"PLC 读写超时（{limit_seconds:g}s）") from err

    def _on_stalled_call_done(self, _future: asyncio.Future[Any]) -> None:
        self._stalled_calls -= 1

    def _require_client(self) -> StationClient:
        if not self._connected or self._client is None:
            raise PlcOperationError(409, "PLC 未连接，请先连接 PLC")
        return self._client

    async def _refresh(self) -> StationFeedback:
        client = self._require_client()
        try:
            block = await self._io(client.read_station)
        except PlcClientError as err:
            self._communication_error = str(err)
            raise
        feedback = decode_station(block)
        self.traffic.sample(block)
        now = time.monotonic()
        self._feedback = feedback
        self._feedback_at = now
        self._communication_error = None
        if self._last_plc_heart is None or feedback.plc_heart != self._last_plc_heart:
            self._last_plc_heart = feedback.plc_heart
            self._last_plc_heart_change = now
        return feedback

    async def _update(
        self,
        offset: int,
        size: int,
        transform: Callable[[bytearray], bytes | bytearray],
        source: str,
        *,
        only: tuple[str, ...] | None = None,
    ) -> None:
        """读-改-写一段写区，并把实际写入的字节记入通信监视。"""
        client = self._require_client()
        written: list[bytes] = []

        def capture(current: bytearray) -> bytes:
            data = bytes(transform(current))
            written.append(data)
            return data

        await self._io(client.update, offset, size, capture)
        if written:
            self.traffic.record_write(offset, written[0], source, only=only)

    async def _write_bit(self, bit: int, value: bool, source: str) -> None:
        """只改字节 0 的某一位；通信监视只记录这一位，不把同字节的其他点位也记一遍。"""
        await self._update(
            OFFSET_PC_STATUS,
            1,
            lambda current: bytes([set_bit(current[0], bit, value)]),
            source,
            only=point_names_for_bit(bit),
        )

    async def _reset_request_power_quietly(self, context: str) -> bool:
        """尽力复位 Request_power；失败只记录，不抛出（用于超时、退出、急停联动）。"""
        if not self._connected or self._client is None:
            return False
        try:
            await self._write_bit(BIT_REQUEST_POWER, False, context)
            return True
        except Exception as err:
            logger.error("%s：复位 Request_power 失败: %s", context, err)
            return False

    def _log_throttled(self, key: str, msg: str, *args: object) -> None:
        now = time.monotonic()
        if now - self._log_throttle.get(key, -math.inf) >= LOG_THROTTLE_SECONDS:
            self._log_throttle[key] = now
            logger.warning(msg, *args)

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------
    async def connect(self, config: PlcConfig) -> PlcStatus:
        async with self._connection_lock:
            await self._prepare_release_locked(
                "切换 PLC 连接", "台架仍在供电，请先下电再切换 PLC 连接"
            )
            await self._disconnect_locked()

            client = self._client_factory(config)
            try:
                await self._io(client.connect, limit_seconds=CONNECT_TIMEOUT_SECONDS)
            except PlcClientError as err:
                # 连接超时后仍可能在后台连上：排一次断开在它后面，不留下孤立连接
                self._executor.submit(client.disconnect)
                raise PlcOperationError(502, str(err)) from err

            self._config = config.model_copy()
            try:
                save_plc_config(self._config_path, self._config)
            except OSError as err:
                logger.warning("PLC 连接配置保存失败: %s", err)
            self._client = client
            self._connected = True
            self._safety_tripped = False
            self._last_plc_heart = None
            self._last_plc_heart_change = None
            self._last_message = None
            try:
                await self._refresh()
            except PlcClientError as err:
                self._log_throttled("connect-read", "PLC 已连接但首次读取失败: %s", err)
            self._monitor_task = asyncio.create_task(self._monitor_loop(), name="plc_monitor")

        mode = (
            "本地仿真"
            if config.simulation
            else f"{config.ip} rack={config.rack} slot={config.slot}"
        )
        events.info("PLC 已连接: %s", mode)
        return self.status()

    async def disconnect(self) -> PlcStatus:
        async with self._connection_lock:
            await self._prepare_release_locked(
                "断开 PLC", "台架仍在供电（已请求上电或接触器吸合），请先下电再断开 PLC"
            )
            was_connected = self._connected
            await self._disconnect_locked()
        if was_connected:
            events.info("PLC 已断开")
        return self.status()

    async def _prepare_release_locked(self, action: str, powered_message: str) -> None:
        """断开 / 切换连接前的检查。

        - 通讯正常且仍在供电：拒绝，要求先下电；
        - 通讯已中断：无法确认供电状态，尽力复位上电请求后放行，以便重新连接恢复监视；
        - 上电 / 下电进行中：拒绝，避免关掉连接后留下上电请求无人复位。
          放在最后检查，且与随后的 _disconnect_locked 之间没有 await。
        """
        if not self._connected:
            return
        if self.status().communication_ok:
            if self._feedback is not None and self._feedback.supply_active:
                raise PlcOperationError(409, powered_message)
        elif self._feedback is not None and self._feedback.supply_active:
            self._abort_power_on = True
            await self._reset_request_power_quietly(f"通讯中断时{action}")
            events.warning("PLC 通讯中断，%s前已尝试复位上电请求，请现场确认高压已断开", action)
        if self._operation_lock.locked():
            raise PlcOperationError(409, f"PLC 正在执行上电或下电，请完成后再{action}")

    async def _disconnect_locked(self) -> None:
        # 先标记断开：之后新的上电 / 下电会在 _require_client 处直接拒绝
        self._connected = False
        task, self._monitor_task = self._monitor_task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        client, self._client = self._client, None
        self._connected = False
        self._feedback = None
        self._feedback_at = None
        self._communication_error = None
        self.traffic.reset_baseline()
        if client is not None:
            try:
                await self._io(client.disconnect)
            except Exception as err:
                logger.warning("PLC 断开时返回异常: %s", err)

    async def shutdown(self) -> None:
        """程序退出：复位上电请求（切断高压）后断开 PLC。"""
        async with self._connection_lock:
            if self._connected:
                self._abort_power_on = True
                if await self._reset_request_power_quietly("程序退出"):
                    events.info("程序退出，已复位 PLC 上电请求")
            await self._disconnect_locked()

    # ------------------------------------------------------------------
    # 常驻监视：状态刷新、Safe 联锁、心跳
    # ------------------------------------------------------------------
    async def _monitor_loop(self) -> None:
        logger.info("PLC 常驻监视已启动（周期 %.1fs）", self._poll_interval_s)
        while True:
            started = time.monotonic()
            try:
                await self._monitor_step()
            except asyncio.CancelledError:
                raise
            except Exception as err:
                self._log_throttled("monitor", "PLC 监视单步执行失败: %s", err)
            await asyncio.sleep(max(0.0, self._poll_interval_s - (time.monotonic() - started)))

    async def _monitor_step(self) -> None:
        if self._stalled_calls:
            # 上一次调用还卡在 PLC 线程里：不再追加读取，避免网络中断时请求越排越多。
            # 反馈随之过期，状态显示通信中断。
            self._log_throttled("stalled", "PLC 读写无响应，暂停常驻读取直到上一次调用结束")
            return
        try:
            feedback = await self._refresh()
        except PlcClientError as err:
            self._log_throttled("read", "PLC 状态读取失败: %s", err)
            return
        await self._check_safety(feedback)
        await self._upload_mes(feedback)

        now = time.monotonic()
        if now - self._last_heart_write >= HEARTBEAT_INTERVAL_SECONDS:
            self._last_heart_write = now
            self._pc_heart = not self._pc_heart
            try:
                await self._write_bit(BIT_PC_HEART, self._pc_heart, "心跳")
            except PlcClientError as err:
                self._log_throttled("heart", "PLC 心跳写入失败: %s", err)

    def serial_number(self) -> str | None:
        """最近一次读到的产品序列号；PLC 未连接或为空时返回 None。"""
        if not self._connected or self._feedback is None:
            return None
        return self._feedback.serial_number or None

    async def write_result(self, result: int) -> None:
        """试车判定：把测试结果写入 Result（1=OK 2=NG）上传 MES；下次上电时清零。"""
        if result not in (1, 2):
            raise ValueError(f"测试结果只能是 1 或 2: {result}")
        data = struct.pack(">h", result)
        try:
            await self._update(OFFSET_RESULT, 2, lambda _current: data, "试车判定")
        except PlcClientError as err:
            raise PlcOperationError(502, f"写入测试结果失败: {err}") from err
        events.info("试车判定已写入 PLC: Result=%d", result)

    async def _upload_mes(self, feedback: StationFeedback) -> None:
        """把实际转速、电机温度写入 Speed / Temp（上传 MES）；与 PLC 中的值相同则不写。"""
        if self._mes_telemetry is None:
            return
        speed, temp = self._mes_telemetry()
        data = build_mes_block(speed, temp)
        if data == build_mes_block(feedback.speed, feedback.temp):
            return
        try:
            await self._update(OFFSET_SPEED, MES_BLOCK_SIZE, lambda _current: data, "MES 上传")
        except PlcClientError as err:
            self._log_throttled("mes", "PLC 转速 / 温度写入失败: %s", err)

    async def _check_safety(self, feedback: StationFeedback) -> None:
        """已请求上电或已通电时 Safe=0：复位 Request_power 并触发一次急停。"""
        if feedback.safe or not feedback.supply_active:
            # Safe 恢复或已断电：下一次 Safe 断开必须重新停机
            self._safety_tripped = False
            return

        now = time.monotonic()
        if (
            feedback.request_power
            and now - self._last_safety_reset_attempt >= SAFETY_RESET_RETRY_SECONDS
        ):
            self._last_safety_reset_attempt = now
            self._abort_power_on = True
            await self._reset_request_power_quietly("Safe 断开自动复位")

        if self._safety_tripped:
            return
        self._safety_tripped = True
        reason = "PLC 安全回路断开 (Safe=0)，已复位上电请求"
        self._last_message = reason
        events.error(reason)
        if self._on_safety_trip is not None:
            try:
                await self._on_safety_trip(reason)
            except Exception as err:
                logger.exception("Safe 断开后的急停联动失败: %s", err)

    async def cut_power_for_emergency(self, reason: str) -> None:
        """电驱桥急停 / 链路故障联动：不等待其他操作，立即复位上电请求。"""
        if not self._connected:
            return
        self._abort_power_on = True
        if self._feedback is not None and not self._feedback.supply_active:
            return
        reset = await self._reset_request_power_quietly("急停联动")
        if reset and not self._safety_tripped:
            # 由 Safe 断开引起的急停已记录过更准确的原因，这里只复位、不重复提示
            self._last_message = f"急停联动，已复位 PLC 上电请求（{reason}）"
            events.warning("急停联动，已复位 PLC 上电请求: %s", reason)

    # ------------------------------------------------------------------
    # 上电 / 下电
    # ------------------------------------------------------------------
    async def power_on(self) -> PlcActionResponse:
        if self._operation_lock.locked():
            raise PlcOperationError(409, "PLC 正在执行上电或下电，请勿重复提交")
        async with self._operation_lock:
            self._require_client()
            # 取得锁后立即清除中止标记：此后到达的下电 / 急停不会被覆盖
            self._abort_power_on = False
            if self._power_on_blocker is not None:
                reason = self._power_on_blocker()
                if reason:
                    raise PlcOperationError(409, reason)
            try:
                feedback = await self._refresh()
            except PlcClientError as err:
                raise PlcOperationError(502, f"读取 PLC 状态失败: {err}") from err
            if not feedback.safe:
                raise PlcOperationError(409, "安全回路未闭合 (Safe=0)，禁止上电")
            if feedback.power_on and feedback.connect:
                return self._result("success", "台架已处于上电状态")

            self._operation = "powering_on"
            succeeded = False
            try:
                if self._abort_power_on:
                    raise PlcOperationError(409, "上电已中止（收到下电、急停或安全回路断开）")
                try:
                    await self._update(
                        OFFSET_PC_STATUS,
                        POWER_ON_BLOCK_SIZE,
                        lambda current: build_power_on_block(current[0]),
                        "PLC 上电",
                    )
                except PlcClientError as err:
                    raise PlcOperationError(502, f"上电请求写入失败: {err}") from err
                events.info(
                    "PLC 请求上电: 产品编号=%d 电压=%d V", PRODUCT_TYPE_CODE, TARGET_VOLTAGE_V
                )

                deadline = time.monotonic() + self._power_on_timeout_s
                while time.monotonic() < deadline:
                    await asyncio.sleep(self._poll_interval_s)
                    if self._abort_power_on:
                        raise PlcOperationError(409, "上电已中止（收到下电、急停或安全回路断开）")
                    try:
                        feedback = await self._refresh()
                    except PlcClientError:
                        continue  # 单次读失败继续等待，由总超时兜底
                    if not feedback.safe:
                        raise PlcOperationError(
                            409, "上电过程中安全回路断开 (Safe=0)，已复位上电请求"
                        )
                    if feedback.power_on and feedback.connect:
                        succeeded = True
                        message = f"已上电，输出电压 {feedback.out_voltage} V"
                        if feedback.get_product_type != PRODUCT_TYPE_CODE:
                            message += (
                                f"；注意：PLC 回传产品编号为 {feedback.get_product_type}，"
                                f"与写入的 {PRODUCT_TYPE_CODE} 不一致"
                            )
                        events.info("PLC 上电完成: %s", message)
                        return self._result("success", message)

                raise PlcOperationError(
                    504,
                    f"上电超时：{self._power_on_timeout_s:g} s 内未收到上电完成与主接触器吸合，"
                    "已复位上电请求",
                )
            finally:
                self._operation = None
                if not succeeded:
                    await self._reset_request_power_quietly("上电未完成复位")

    async def power_off(self) -> PlcActionResponse:
        # 下电优先：先让进行中的上电退出，再取得操作锁
        self._abort_power_on = True
        async with self._operation_lock:
            self._require_client()
            self._operation = "powering_off"
            try:
                issues: list[str] = []
                if self._before_power_off is not None:
                    try:
                        note = await self._before_power_off()
                    except Exception as err:
                        issues.append(f"关闭电机使能未确认: {err}")
                    else:
                        if note:
                            issues.append(note)

                try:
                    await self._write_bit(BIT_REQUEST_POWER, False, "下电")
                except PlcClientError as err:
                    raise PlcOperationError(
                        502, f"下电指令写入失败: {err}。请按现场流程手动断开高压"
                    ) from err
                events.info("PLC 请求下电")

                deadline = time.monotonic() + self._power_off_timeout_s
                while time.monotonic() < deadline:
                    try:
                        feedback = await self._refresh()
                        if not feedback.power_on and not feedback.connect:
                            message = "已下电，主接触器已断开"
                            if issues:
                                message += "；" + "；".join(issues)
                            events.info("PLC 下电完成")
                            return self._result("partial" if issues else "success", message)
                    except PlcClientError:
                        pass
                    await asyncio.sleep(self._poll_interval_s)

                issues.insert(
                    0,
                    f"{self._power_off_timeout_s:g} s 内未确认主接触器断开，请人工核查",
                )
                events.warning("PLC 下电未确认: %s", "；".join(issues))
                return self._result("partial", "下电指令已发出；" + "；".join(issues))
            finally:
                self._operation = None

    def _result(self, status: Literal["success", "partial"], message: str) -> PlcActionResponse:
        """生成操作结果。操作已结束，先清除进行中标记，返回的快照才是最终状态。"""
        self._operation = None
        self._last_message = message
        return PlcActionResponse(status=status, message=message, plc=self.status())

    def set_simulated_safe(self, safe: bool) -> PlcStatus:
        if not isinstance(self._client, SimulatedStationClient):
            raise PlcOperationError(409, "仅在本地仿真模式下可以模拟安全回路")
        self._client.safe = safe
        return self.status()

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------
    def status(self) -> PlcStatus:
        now = time.monotonic()
        feedback = self._feedback
        communication_ok = (
            self._connected
            and feedback is not None
            and self._feedback_at is not None
            and now - self._feedback_at <= FEEDBACK_STALE_SECONDS
        )
        heartbeat_alive = (
            communication_ok
            and self._last_plc_heart_change is not None
            and now - self._last_plc_heart_change <= HEARTBEAT_TIMEOUT_SECONDS
        )

        power_state: PowerState = "idle"
        fault_reason: str | None = None
        if self._connected:
            if self._operation is not None:
                power_state = self._operation
            elif not communication_ok:
                power_state = "fault"
                fault_reason = self._communication_error or "PLC 通信中断"
            elif feedback is not None and feedback.supply_active and not feedback.safe:
                power_state = "fault"
                fault_reason = "安全回路断开 (Safe=0)"
            elif feedback is not None and feedback.power_on and feedback.connect:
                power_state = "powered"
            elif feedback is not None and feedback.request_power:
                power_state = "fault"
                fault_reason = "已请求上电但未收到上电完成，请下电后重试"

        base = PlcStatus(
            connected=self._connected,
            simulation=self._config.simulation,
            ip=self._config.ip,
            rack=self._config.rack,
            slot=self._config.slot,
            communication_ok=communication_ok,
            communication_error=self._communication_error,
            plc_heartbeat_alive=heartbeat_alive,
            power_state=power_state,
            fault_reason=fault_reason,
            last_message=self._last_message,
        )
        if feedback is None or not self._connected:
            return base
        return base.model_copy(
            update={
                "safe": feedback.safe,
                "request_power": feedback.request_power,
                "power_on": feedback.power_on,
                "contactor_closed": feedback.connect,
                "product_type_feedback": feedback.get_product_type,
                "output_voltage": feedback.out_voltage,
                "output_current": feedback.out_current,
                "serial_number": feedback.serial_number,
            }
        )


_global_plc_manager: PlcPowerManager | None = None


def get_plc_manager() -> PlcPowerManager:
    """获取 PLC 管理器单例，并与电驱桥管理器双向联动。"""
    global _global_plc_manager
    if _global_plc_manager is None:
        from app.services.axle_manager import get_axle_manager

        manager = PlcPowerManager(config_path=get_settings().plc_config_path)
        axle = get_axle_manager()
        manager.bind_axle(
            on_safety_trip=lambda reason: axle.external_safety_trip("plc_safe", reason),
            before_power_off=axle.disable_for_power_off,
            power_on_blocker=axle.power_on_blocker,
            mes_telemetry=axle.mes_telemetry,
        )
        axle.add_emergency_listener(manager.cut_power_for_emergency)
        # 循环测试跑完 / 异常中断后自动判定并请求下电
        from app.services.auto_judge import CycleAutoJudge
        from app.services.test_records import get_test_record_store

        auto_judge = CycleAutoJudge(axle=axle, plc=manager, store_factory=get_test_record_store)
        axle.add_cycle_finished_listener(auto_judge.on_cycle_finished)
        _global_plc_manager = manager
    return _global_plc_manager


def peek_plc_manager() -> PlcPowerManager | None:
    return _global_plc_manager
