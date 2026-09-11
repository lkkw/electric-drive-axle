"""Electric Drive Axle State Manager and Communication Coordinator.

Manages:
- CAN hardware lifecycle (connect, disconnect, channel setup).
- Real-time 10ms high-precision transmission task (VCU_11, ID 0x314).
- Real-time high-throughput receive task and bitwise decoding (0x35A, 0x35B, 0x35C).
- Thread-safe state synchronization and SSE subscription broadcast.
"""

import asyncio
import logging
import time
from collections import deque
from datetime import UTC, datetime

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
from app.core.can.driver import CanDriverError, ZlgCanDriver, windows_high_resolution_timer
from app.schemas.axle import (
    AxleTelemetry,
    CanConnectRequest,
    CanFrameItem,
    CanSendRawFrameRequest,
    McuDriveMotor1Telemetry,
    McuDriveMotor2Telemetry,
    McuTboxTelemetry,
    VcuCommandState,
    VcuCommandUpdateRequest,
)

logger = logging.getLogger("app.axle_manager")


class AxleManager:
    """电驱桥上位机系统核心管理器 (单例生命周期)。"""

    def __init__(self, driver: ZlgCanDriver | None = None) -> None:
        """初始化管理器。"""
        self._driver = driver or ZlgCanDriver()
        self._lock = asyncio.Lock()

        # 通信配置
        self._device_type: int = ZcanDeviceType.USBCAN2
        self._device_index: int = 0
        self._channel: int = 0
        self._baud_rate: int = 250000

        # 控制指令状态 (VCU_11 发送内容)
        self._command = VcuCommandState()

        # 遥测反馈状态
        self._mcu_1 = McuDriveMotor1Telemetry()
        self._mcu_2 = McuDriveMotor2Telemetry()
        self._mcu_tbox = McuTboxTelemetry()

        # 通信统计
        self._connected: bool = False
        self._is_transmitting: bool = False
        self._is_emergency_locked: bool = False  # 急停互锁标志：触发后拒绝一切使能/驱动指令
        self._tx_frame_count: int = 0
        self._rx_frame_count: int = 0
        self._tx_error_count: int = 0
        self._last_rx_timestamp: float | None = None
        self._recent_frames: deque[CanFrameItem] = deque(maxlen=500)

        # 异步循环任务句柄
        self._tx_task: asyncio.Task[None] | None = None
        self._rx_task: asyncio.Task[None] | None = None

        # SSE 事件分发队列集合
        self._subscribers: set[asyncio.Queue[AxleTelemetry]] = set()

    @property
    def is_connected(self) -> bool:
        """硬件连接状态。"""
        return self._connected

    @property
    def is_transmitting(self) -> bool:
        """报文发送循环状态。"""
        return self._is_transmitting

    async def connect(self, config: CanConnectRequest) -> None:
        """连接周立功 USBCAN 设备并开启通道与收发任务。

        :param config: 设备与通道配置参数
        """
        async with self._lock:
            if self._connected:
                logger.info("设备已处于连接状态，先安全断开旧连接。")
                await self._disconnect_internal()

            self._device_type = config.device_type
            self._device_index = config.device_index
            self._channel = config.channel
            self._baud_rate = config.baud_rate

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
                if self._channel == -1:
                    await self._driver.open_channel(
                        channel=0,
                        baud_rate=self._baud_rate,
                    )
                    await self._driver.open_channel(
                        channel=1,
                        baud_rate=self._baud_rate,
                    )
                else:
                    await self._driver.open_channel(
                        channel=self._channel,
                        baud_rate=self._baud_rate,
                    )
            except Exception as err:
                # 若通道初始化失败，必须回滚释放已打开的设备句柄，防止硬件句柄泄漏
                logger.error("通道打开失败，正在回滚设备状态: %s", err)
                if self._channel == -1:
                    try:
                        await self._driver.close_channel(0)
                    except Exception:
                        pass
                    try:
                        await self._driver.close_channel(1)
                    except Exception:
                        pass
                else:
                    try:
                        await self._driver.close_channel(self._channel)
                    except Exception:
                        pass
                try:
                    await self._driver.close_device()
                except Exception:
                    pass
                raise

            self._connected = True
            self._is_transmitting = True

            # 2. 启动 10ms 发送循环与高频接收循环
            self._tx_task = asyncio.create_task(
                self._tx_loop(),
                name="axle_can_tx_loop",
            )
            self._rx_task = asyncio.create_task(
                self._rx_loop(),
                name="axle_can_rx_loop",
            )

            logger.info("USBCAN 启动成功，10ms 控制循环与接收循环已就绪。")

    async def disconnect(self) -> None:
        """安全断开 CAN 通信并释放硬件资源。"""
        async with self._lock:
            await self._disconnect_internal()

    async def _disconnect_internal(self) -> None:
        """内部断开流程 (需在锁保护下调用)。"""
        self._is_transmitting = False
        self._connected = False

        # 1. 停止发送和接收后台任务
        tasks_to_cancel = [t for t in (self._tx_task, self._rx_task) if t is not None]
        for task in tasks_to_cancel:
            task.cancel()

        for task in tasks_to_cancel:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as err:
                logger.warning("停止任务时发生异常: %s", err)

        self._tx_task = None
        self._rx_task = None

        # 2. 发送使能关闭报文 (停机保护)
        try:
            shutdown_payload = encode_vcu_11(
                torque_req=0.0,
                speed_req=0,
                work_mode_req=0,
                mcu_en_cmd=0,
                gear_sts=3,  # 空挡
                active_discharge=0,
                life=0,
            )
            channels_to_close = [0, 1] if self._channel == -1 else [self._channel]
            for ch in channels_to_close:
                if self._driver.is_channel_open(ch):
                    try:
                        await self._driver.transmit(
                            can_id=CAN_ID_VCU_11,
                            data=shutdown_payload,
                            channel=ch,
                        )
                    except Exception as err:
                        logger.warning("下发停机保护帧异常 (通道 %d): %s", ch, err)
        except Exception as err:
            logger.warning("生成停机保护帧异常: %s", err)

        # 3. 关闭通道并释放设备
        channels_to_close = [0, 1] if self._channel == -1 else [self._channel]
        for ch in channels_to_close:
            try:
                await self._driver.close_channel(ch)
            except Exception as err:
                logger.error("关闭通道 %d 时发生异常: %s", ch, err)
        try:
            await self._driver.close_device()
        except Exception as err:
            logger.error("关闭设备时发生异常: %s", err)

        logger.info("USBCAN 设备已完全关闭并释放。")

    async def update_command(self, update: VcuCommandUpdateRequest) -> VcuCommandState:
        """更新 VCU 控制设定值。

        :param update: 包含待更新字段的请求体
        :return: 更新后的完整控制状态
        """
        async with self._lock:
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

            if update.torque_req is not None:
                self._command.torque_req = update.torque_req
            if update.speed_req is not None:
                self._command.speed_req = update.speed_req
            if update.work_mode_req is not None:
                self._command.work_mode_req = update.work_mode_req
            if update.mcu_en_cmd is not None:
                self._command.mcu_en_cmd = update.mcu_en_cmd
            if update.gear_sts is not None:
                self._command.gear_sts = update.gear_sts
            if update.active_discharge is not None:
                self._command.active_discharge = update.active_discharge

            return self._command.model_copy()

    async def emergency_stop(self) -> VcuCommandState:
        """一键紧急停机 (Emergency Stop)。

        立即将使能置 0、目标转矩与转速归零、挂入空挡，并立即强制发送一帧控制报文。
        """
        async with self._lock:
            self._is_emergency_locked = True
            self._command.mcu_en_cmd = 0
            self._command.torque_req = 0.0
            self._command.speed_req = 0
            self._command.gear_sts = 3  # 空挡 N
            self._command.active_discharge = 0

            # 如果当前通道有效，立即同步下发紧急制动帧
            if self._connected:
                channels_to_use = [0, 1] if self._channel == -1 else [self._channel]
                self._command.life = (self._command.life + 1) % 16
                payload = encode_vcu_11(
                    torque_req=0.0,
                    speed_req=0,
                    work_mode_req=self._command.work_mode_req,
                    mcu_en_cmd=0,
                    gear_sts=3,
                    active_discharge=0,
                    life=self._command.life,
                )
                for ch in channels_to_use:
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

            logger.warning("已触发紧急停机: 使能已关闭，目标转矩/转速归零！")
            return self._command.model_copy()

    async def emergency_reset(self) -> VcuCommandState:
        """复位急停互锁状态 (Emergency Reset)。

        解除急停锁定，允许后续正常控制指令。操作员确认安全后手动调用。
        """
        async with self._lock:
            self._is_emergency_locked = False
            logger.info("急停互锁已复位，系统恢复正常控制模式。")
            return self._command.model_copy()

    @property
    def is_emergency_locked(self) -> bool:
        """急停互锁状态。"""
        return self._is_emergency_locked


    def _record_frame(
        self,
        *,
        direction: str,
        can_id: int,
        data: bytes,
        name: str = "",
    ) -> None:
        """内部记录单条 CAN 报文至循环缓冲区。"""
        now = datetime.now()
        timestamp = f"{now.strftime('%H:%M:%S')}.{now.microsecond // 1000:03d}"
        data_hex = " ".join(f"{b:02X}" for b in data)
        self._recent_frames.append(
            CanFrameItem(
                timestamp=timestamp,
                direction=direction,
                can_id=can_id,
                can_id_hex=f"0x{can_id:03X}",
                dlc=len(data),
                data_hex=data_hex,
                name=name,
            )
        )

    async def send_raw_frame(self, request: CanSendRawFrameRequest) -> bool:
        """手动下发单帧 CAN 测试或诊断报文。

        :param request: 包含目标 ID、16进制数据载荷及扩展帧标志的请求对象
        :return: 硬件发送是否成功
        """
        async with self._lock:
            if not self._connected:
                raise CanDriverError("USBCAN 硬件未连接，无法下发报文。")

            channels_to_use = [0, 1] if self._channel == -1 else [self._channel]
            valid_channels = [ch for ch in channels_to_use if self._driver.is_channel_open(ch)]

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

    def get_telemetry(self) -> AxleTelemetry:
        """获取当前电驱桥系统最新遥测快照。"""
        now_str = datetime.now(UTC).isoformat()
        return AxleTelemetry(
            connected=self._connected,
            is_transmitting=self._is_transmitting,
            is_emergency_locked=self._is_emergency_locked,
            device_type=self._device_type,
            device_index=self._device_index,
            channel=self._channel,
            baud_rate=self._baud_rate,
            command=self._command.model_copy(),
            mcu_1=self._mcu_1.model_copy(),
            mcu_2=self._mcu_2.model_copy(),
            mcu_tbox=self._mcu_tbox.model_copy(),
            tx_frame_count=self._tx_frame_count,
            rx_frame_count=self._rx_frame_count,
            tx_error_count=self._tx_error_count,
            last_rx_timestamp=self._last_rx_timestamp,
            recent_frames=list(self._recent_frames),
            updated_at=now_str,
        )

    def subscribe(self) -> asyncio.Queue[AxleTelemetry]:
        """注册 SSE 遥测流订阅队列。"""
        queue: asyncio.Queue[AxleTelemetry] = asyncio.Queue(maxsize=30)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[AxleTelemetry]) -> None:
        """注销 SSE 遥测流订阅队列。"""
        self._subscribers.discard(queue)

    def _broadcast_telemetry(self) -> None:
        """向所有已连接的 SSE 客户端广播最新数据快照。"""
        if not self._subscribers:
            return

        snapshot = self.get_telemetry()
        dead_queues: list[asyncio.Queue[AxleTelemetry]] = []

        for q in self._subscribers:
            try:
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
            self._subscribers.discard(q)

    async def shutdown(self) -> None:
        """系统退出时释放所有硬件连接并关闭驱动线程池。"""
        async with self._lock:
            if self._connected:
                await self._disconnect_internal()
        self._driver.shutdown_executor()

    async def _tx_loop(self) -> None:
        """VCU_11 10ms 高精度定时循环发送任务。

        按照通讯矩阵严格以 10ms 周期向驱动电机控制器 (MCU) 发送控制信号。
        """
        target_interval = 0.010  # 10ms
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
                        dischg = self._command.active_discharge
                        life = self._command.life

                    # 2. 纯 Python 位运算编码
                    payload = encode_vcu_11(
                        torque_req=tq,
                        speed_req=spd,
                        work_mode_req=mode,
                        mcu_en_cmd=en,
                        gear_sts=gear,
                        active_discharge=dischg,
                        life=life,
                    )

                    # 3. 异步非阻塞发送 (受驱动内部 _tx_lock 保护保证硬件总线时序串行安全)
                    channels_to_use = [0, 1] if self._channel == -1 else [self._channel]
                    any_success = False
                    for ch in channels_to_use:
                        try:
                            s = await self._driver.transmit(
                                can_id=CAN_ID_VCU_11,
                                data=payload,
                                channel=ch,
                            )
                            if s:
                                self._tx_frame_count += 1
                                any_success = True
                            else:
                                self._tx_error_count += 1
                        except Exception as err:
                            self._tx_error_count += 1
                            logger.warning("CAN 发送异常 (通道 %d): %s", ch, err)

                    if any_success:
                        self._record_frame(
                            direction="TX",
                            can_id=CAN_ID_VCU_11,
                            data=payload,
                            name="VCU_11 (控制器指令)",
                        )

                    # 4. 绝对时间戳推移补偿（防止相位漂移累积）
                    next_tick += target_interval
                    sleep_duration = next_tick - time.perf_counter()
                    if sleep_duration > 0:
                        await asyncio.sleep(sleep_duration)
            except asyncio.CancelledError:
                logger.info("VCU_11 发送循环已被取消。")
                raise
            except Exception as tx_err:
                logger.exception("VCU_11 发送循环发生未捕获异常: %s", tx_err)

    async def _rx_loop(self) -> None:
        """CAN 报文接收与分发任务。

        以 5ms 周期轮询周立功硬件缓冲区，支持突发报文批量读取与即时解码。
        """
        logger.info("CAN 接收循环已启动。")
        last_broadcast_time = time.perf_counter()

        try:
            while self._is_transmitting:
                # 批量接收硬件缓冲区中的报文
                channels_to_use = [0, 1] if self._channel == -1 else [self._channel]
                frames = []
                for ch in channels_to_use:
                    try:
                        ch_frames = await self._driver.receive(
                            channel=ch,
                            max_count=100,
                            wait_time_ms=1,
                        )
                        if ch_frames:
                            frames.extend(ch_frames)
                    except Exception as err:
                        logger.warning("CAN 硬件接收驱动异常 (通道 %d): %s", ch, err)
                        
                if not frames:
                    await asyncio.sleep(0.005)
                    continue

                if frames:
                    self._rx_frame_count += len(frames)
                    self._last_rx_timestamp = time.time()

                    for frame in frames:
                        # 仅处理有效的数据帧 (8 字节)
                        if len(frame.data) < 8:
                            continue

                        frame_name = f"CAN_0x{frame.can_id:X}"
                        # 使用 Python 3.10+ match-case 分发对应报文解码
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

                                case 0x35B:  # CAN_ID_MCU_DRIVE_MOTOR_2
                                    frame_name = "MCU_2 (电机转速/转矩)"
                                    d2 = decode_mcu_motor_2(frame.data)
                                    self._mcu_2 = McuDriveMotor2Telemetry(
                                        mcu_motor_tor_max=d2.mcu_motor_tor_max,
                                        mcu_act_motor_spd=d2.mcu_act_motor_spd,
                                        mcu_act_motor_tq=d2.mcu_act_motor_tq,
                                        mcu_active_dischrg_sts=d2.mcu_active_dischrg_sts,
                                        mcu_motor_work_mod=d2.mcu_motor_work_mod,
                                        mcu_lv_sts=d2.mcu_lv_sts,
                                        mcu_en_sts=d2.mcu_en_sts,
                                        mcu_motor_temp_extre_over=d2.mcu_motor_temp_extre_over,
                                        mcu_mcu_temp_extre_over=d2.mcu_mcu_temp_extre_over,
                                        mcu_life_2=d2.mcu_life_2,
                                    )

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

                                case _:
                                    # 其他未知或未配置的 CAN 报文
                                    pass
                        except Exception as decode_err:
                            logger.warning(
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

                # 控制 SSE 广播频率 (约 20Hz / 50ms 一次推送，保证流畅且不阻塞网络)
                now = time.perf_counter()
                if now - last_broadcast_time >= 0.050:
                    self._broadcast_telemetry()
                    last_broadcast_time = now

                await asyncio.sleep(0.005)
        except asyncio.CancelledError:
            logger.info("CAN 接收循环已被取消。")
            raise
        except Exception as rx_err:
            logger.exception("CAN 接收循环发生未捕获异常: %s", rx_err)


# 全局单例管理器
_global_axle_manager: AxleManager | None = None


def get_axle_manager() -> AxleManager:
    """获取电驱桥系统单例管理器实例。"""
    global _global_axle_manager
    if _global_axle_manager is None:
        _global_axle_manager = AxleManager()
    return _global_axle_manager
