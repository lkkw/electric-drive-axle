"""ZLG USBCAN Hardware Driver using ctypes and ThreadPoolExecutor.

Encapsulates 64-bit Windows zlgcan.dll. All blocking C calls are dispatched
to a ThreadPoolExecutor using asyncio's loop.run_in_executor to avoid
blocking the FastAPI async event loop.
"""

import asyncio
import ctypes
import os
import platform
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from ctypes import (
    byref,
    c_char_p,
    c_int,
    c_uint,
    c_void_p,
    windll,
)
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.can.constants import BAUDRATE_TIMINGS, ZcanDeviceType
from app.core.can.zlgcan_types import (
    INVALID_CHANNEL_HANDLE,
    INVALID_DEVICE_HANDLE,
    P_ZCAN_CHANNEL_ERR_INFO,
    P_ZCAN_CHANNEL_INIT_CONFIG,
    P_ZCAN_DEVICE_INFO,
    ZCAN_CHANNEL_INIT_CONFIG,
    ZCAN_STATUS_OK,
    ZCAN_TYPE_CAN,
    P_ZCAN_Receive_Data,
    P_ZCAN_Transmit_Data,
    ZCAN_Receive_Data,
    ZCAN_Transmit_Data,
)

# C 驱动调用默认超时（秒）：防止 USB 断开时线程永久阻塞
_C_CALL_TIMEOUT: float = 5.0
# 周期收发调用超时（秒）：单帧收发正常耗时为毫秒级，超时即视为硬件链路异常，
# 让上层尽快判定掉线，而不是让 10ms 控制循环卡住数秒。
_IO_CALL_TIMEOUT: float = 0.5


class CanDriverError(Exception):
    """CAN 驱动基础异常。"""


class CanDeviceNotOpenError(CanDriverError):
    """设备未打开或句柄无效异常。"""


class CanChannelNotOpenError(CanDriverError):
    """通道未打开或初始化失败异常。"""


@dataclass(slots=True, frozen=True)
class CanRawFrame:
    """接收到的 CAN 原始数据帧。"""

    can_id: int  # 报文标识符
    data: bytes  # 报文有效载荷 (DLC 长度)
    is_extended: bool  # 是否为扩展帧
    is_remote: bool  # 是否为远程帧
    timestamp: int  # 硬件微秒时间戳


@contextmanager
def windows_high_resolution_timer():
    """在 Windows 操作系统下启用 1ms 多媒体定时器分辨率。

    默认情况下 Windows 系统调度计时器粒度为 15.625ms，会导致 asyncio.sleep(0.010)
    漂移至 15~16ms，引起控制周期严重抖动。启用 timeBeginPeriod(1) 可将定时器精度
    锁定在 1ms，并在退出时通过 finally 恢复。
    """
    enabled = False
    if platform.system() == "Windows":
        try:
            windll.winmm.timeBeginPeriod(1)
            enabled = True
        except Exception:
            pass
    try:
        yield
    finally:
        if enabled:
            try:
                windll.winmm.timeEndPeriod(1)
            except Exception:
                pass


class ZlgCanDriver:
    """周立功 USBCAN 设备驱动封装类。

    提供线程安全、非阻塞的异步接口（基于 asyncio + ThreadPoolExecutor）。
    """

    def __init__(
        self,
        dll_path: str | Path | None = None,
        max_workers: int = 6,
    ) -> None:
        """初始化 ZLG CAN 驱动。

        :param dll_path: 可选的 DLL 绝对路径，缺省时自动在项目内定位
        :param max_workers: 线程池最大工作线程数
        """
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="zlgcan_worker",
        )
        self._device_handle: int = INVALID_DEVICE_HANDLE
        self._channel_handles: dict[int, int] = {}
        self._tx_lock = asyncio.Lock()  # 串行化硬件报文发送，防止并发调用损坏 C 驱动缓冲区
        self._rx_buffer_cache: dict[tuple[int, int], ctypes.Array[ZCAN_Receive_Data]] = {}
        self._dll_path = self._resolve_dll_path(dll_path)
        self._dll = self._load_dll(self._dll_path)

    @property
    def is_device_open(self) -> bool:
        """设备是否已成功打开。"""
        return self._device_handle != INVALID_DEVICE_HANDLE

    def is_channel_open(self, channel: int = 0) -> bool:
        """指定通道是否已启动。"""
        return self._channel_handles.get(channel, INVALID_CHANNEL_HANDLE) != INVALID_CHANNEL_HANDLE

    async def _call(
        self,
        limit_seconds: float,
        description: str,
        func: Callable[..., Any],
        *args: Any,
    ) -> Any:
        """在线程池中执行一次阻塞 C 调用，并施加统一超时。

        超时只能结束协程侧等待，已进入 C 函数的工作线程无法被强制中断；
        尚在线程池排队的调用会随 ``wait_for`` 取消而一并撤销，避免堆积。
        """
        loop = asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(self._executor, func, *args),
                timeout=limit_seconds,
            )
        except TimeoutError as err:
            raise CanDriverError(
                f"{description}超时（{limit_seconds:g}s），硬件可能已断开。"
            ) from err

    @staticmethod
    def _resolve_dll_path(custom_path: str | Path | None) -> Path:
        """解析 zlgcan.dll 的绝对路径。"""
        if custom_path:
            p = Path(custom_path).resolve()
            if p.is_file():
                return p
            raise FileNotFoundError(f"未找到指定的 zlgcan.dll: {p}")

        # 打包环境（PyInstaller 冻结环境）
        if getattr(sys, "frozen", False):
            candidates = [
                Path(getattr(sys, "_MEIPASS", "")) / "zlgcan_x64" / "zlgcan.dll",
                Path(sys.executable).resolve().parent / "zlgcan_x64" / "zlgcan.dll",
                Path(sys.executable).resolve().parent / "_internal" / "zlgcan_x64" / "zlgcan.dll",
            ]
            for candidate in candidates:
                if candidate.is_file():
                    return candidate

        # 开发环境：默认从 backend/zlgcan_x64/zlgcan.dll 定位
        dev_candidates = [
            Path(__file__).resolve().parents[3] / "zlgcan_x64" / "zlgcan.dll",
            Path.cwd() / "zlgcan_x64" / "zlgcan.dll",
            Path.cwd() / "backend" / "zlgcan_x64" / "zlgcan.dll",
        ]
        for dev_p in dev_candidates:
            if dev_p.is_file():
                return dev_p

        raise FileNotFoundError(
            f"未找到默认周立功动态库 zlgcan.dll，已检查路径: {dev_candidates[0]}"
        )

    def _load_dll(self, dll_path: Path) -> ctypes.WinDLL:
        """加载 Windows 64位动态链接库并声明各 C 函数签名。"""
        if platform.system() != "Windows":
            raise RuntimeError("ZLG USBCAN 驱动仅支持 Windows 操作系统。")

        dll_dir = dll_path.parent
        if sys.version_info >= (3, 8) and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(dll_dir))
            kernel_dir = dll_dir / "kerneldlls"
            if kernel_dir.is_dir():
                os.add_dll_directory(str(kernel_dir))

        try:
            dll = windll.LoadLibrary(str(dll_path))
        except OSError as err:
            raise CanDriverError(
                f"加载 {dll_path} 失败: {err}。"
                "请确认 zlgcan_x64/kerneldlls 目录完整，并已安装 VC++ 运行库与 USBCAN 驱动。"
            ) from err

        # 显式配置 C 函数签名，防止 64 位指针截断 (argtypes & restype)
        dll.ZCAN_OpenDevice.argtypes = [c_uint, c_uint, c_uint]
        dll.ZCAN_OpenDevice.restype = c_void_p

        dll.ZCAN_CloseDevice.argtypes = [c_void_p]
        dll.ZCAN_CloseDevice.restype = c_uint

        dll.ZCAN_GetDeviceInf.argtypes = [c_void_p, P_ZCAN_DEVICE_INFO]
        dll.ZCAN_GetDeviceInf.restype = c_uint

        dll.ZCAN_InitCAN.argtypes = [c_void_p, c_uint, P_ZCAN_CHANNEL_INIT_CONFIG]
        dll.ZCAN_InitCAN.restype = c_void_p

        dll.ZCAN_StartCAN.argtypes = [c_void_p]
        dll.ZCAN_StartCAN.restype = c_uint

        dll.ZCAN_ResetCAN.argtypes = [c_void_p]
        dll.ZCAN_ResetCAN.restype = c_uint

        dll.ZCAN_ClearBuffer.argtypes = [c_void_p]
        dll.ZCAN_ClearBuffer.restype = c_uint

        dll.ZCAN_Transmit.argtypes = [c_void_p, P_ZCAN_Transmit_Data, c_uint]
        dll.ZCAN_Transmit.restype = c_uint

        dll.ZCAN_Receive.argtypes = [c_void_p, P_ZCAN_Receive_Data, c_uint, c_int]
        dll.ZCAN_Receive.restype = c_uint

        dll.ZCAN_GetReceiveNum.argtypes = [c_void_p, c_uint]
        dll.ZCAN_GetReceiveNum.restype = c_uint

        dll.ZCAN_SetValue.argtypes = [c_void_p, c_char_p, c_void_p]
        dll.ZCAN_SetValue.restype = c_uint

        dll.ZCAN_ReadChannelErrInfo.argtypes = [c_void_p, P_ZCAN_CHANNEL_ERR_INFO]
        dll.ZCAN_ReadChannelErrInfo.restype = c_uint

        return dll

    async def open_device(
        self,
        device_type: int = ZcanDeviceType.USBCAN2,
        device_index: int = 0,
    ) -> None:
        """异步打开 USBCAN 设备。

        :param device_type: 设备型号代码 (缺省 4: USBCAN2)
        :param device_index: 设备卡索引 (0 为第一张卡)
        """
        if self.is_device_open:
            return

        handle = await self._call(
            _C_CALL_TIMEOUT,
            "打开设备",
            self._dll.ZCAN_OpenDevice,
            int(device_type),
            int(device_index),
            0,
        )

        if not handle or handle == INVALID_DEVICE_HANDLE:
            raise CanDriverError(f"打开 ZLG 设备失败 (type={device_type}, index={device_index})")

        self._device_handle = handle

    async def open_channel(
        self,
        channel: int = 0,
        baud_rate: int = 500000,
    ) -> None:
        """异步配置波特率并启动 CAN 通道。

        :param channel: 通道号 (0 或 1)
        :param baud_rate: 波特率 (例如 250000, 500000)
        """
        if not self.is_device_open:
            raise CanDeviceNotOpenError("必须先成功打开设备，才能开启通道。")

        if self.is_channel_open(channel):
            return

        # 1. 查询经典 CAN 控制器 (SJA1000) Timing0/Timing1 映射
        timing = BAUDRATE_TIMINGS.get(baud_rate)
        if not timing:
            raise CanDriverError(
                f"不支持的波特率: {baud_rate} bps。可选波特率: {list(BAUDRATE_TIMINGS.keys())}"
            )
        t0, t1 = timing

        # 2. 针对支持动态属性树的设备 (如 USBCAN-2E-U 等)，尝试调用 SetValue 设置波特率
        # 经典 USBCAN1/2 等 SJA1000 设备不支持 SetValue 返回 0 属正常，
        # 核心波特率参数由后续 InitCAN 中的 timing0/timing1 准确写入硬件寄存器
        try:
            path_str = f"{channel}/baud_rate"
            val_str = str(baud_rate)
            await self._call(
                _C_CALL_TIMEOUT,
                "设置波特率属性",
                self._dll.ZCAN_SetValue,
                self._device_handle,
                path_str.encode("utf-8"),
                val_str.encode("utf-8"),
            )
        except Exception:
            pass

        # 3. 初始化 CAN 通道结构体 (配置 SJA1000 关键寄存器与全通滤波)
        init_cfg = ZCAN_CHANNEL_INIT_CONFIG()
        init_cfg.can_type = ZCAN_TYPE_CAN
        init_cfg.config.can.acc_code = 0x00000000
        init_cfg.config.can.acc_mask = 0xFFFFFFFF  # 允许接收所有标准/扩展帧
        init_cfg.config.can.timing0 = t0
        init_cfg.config.can.timing1 = t1
        init_cfg.config.can.mode = 0  # 正常收发模式

        chn_handle = await self._call(
            _C_CALL_TIMEOUT,
            f"初始化通道 {channel} ",
            self._dll.ZCAN_InitCAN,
            self._device_handle,
            channel,
            byref(init_cfg),
        )

        if not chn_handle or chn_handle == INVALID_CHANNEL_HANDLE:
            raise CanChannelNotOpenError(f"初始化通道 {channel} 失败 (InitCAN)。")

        # 4. 启动 CAN 通道
        start_ret = await self._call(
            _C_CALL_TIMEOUT,
            f"启动通道 {channel} ",
            self._dll.ZCAN_StartCAN,
            chn_handle,
        )
        if start_ret != ZCAN_STATUS_OK:
            await self._call(
                _C_CALL_TIMEOUT,
                f"复位通道 {channel} ",
                self._dll.ZCAN_ResetCAN,
                chn_handle,
            )
            raise CanChannelNotOpenError(f"启动通道 {channel} 失败 (StartCAN)。")

        self._channel_handles[channel] = chn_handle

    async def transmit(
        self,
        can_id: int,
        data: bytes,
        channel: int = 0,
        is_extended: bool = False,
        is_remote: bool = False,
    ) -> bool:
        """异步单帧发送 CAN 报文 (受 _tx_lock 保护，防止多协程并发写入破坏 C 驱动缓冲区)。

        :param can_id: CAN ID (例如 0x258)
        :param data: 报文数据 (最多 8 字节)
        :param channel: 目标通道号
        :param is_extended: 是否扩展帧
        :param is_remote: 是否远程帧
        :return: 发送是否成功
        """
        async with self._tx_lock:
            chn_handle = self._channel_handles.get(channel)
            if not chn_handle:
                raise CanChannelNotOpenError(f"通道 {channel} 未开启，无法发送数据。")

            data_len = min(len(data), 8)
            tx_obj = ZCAN_Transmit_Data()
            tx_obj.transmit_type = 0  # 正常发送
            tx_obj.frame.can_id = can_id & 0x1FFFFFFF
            tx_obj.frame.can_dlc = data_len
            tx_obj.frame.eff = 1 if is_extended else 0
            tx_obj.frame.rtr = 1 if is_remote else 0

            for i in range(data_len):
                tx_obj.frame.data[i] = data[i]

            ret = await self._call(
                _IO_CALL_TIMEOUT,
                "CAN 报文发送",
                self._dll.ZCAN_Transmit,
                chn_handle,
                byref(tx_obj),
                1,
            )
            return ret == 1

    async def receive(
        self,
        channel: int = 0,
        max_count: int = 50,
        wait_time_ms: int = 1,
    ) -> list[CanRawFrame]:
        """异步批量接收缓冲区中的 CAN 报文。

        :param channel: 通道号
        :param max_count: 一次读取的最大帧数
        :param wait_time_ms: 底层驱动等待超时 (毫秒)
        :return: 接收到的报文列表
        """
        chn_handle = self._channel_handles.get(channel)
        if not chn_handle:
            return []

        # 复用预分配的 ctypes 接收缓冲区，避免高频 GC 抖动
        buf_key = (channel, max_count)
        if buf_key not in self._rx_buffer_cache:
            self._rx_buffer_cache[buf_key] = (ZCAN_Receive_Data * max_count)()
        rx_buffer = self._rx_buffer_cache[buf_key]

        actual_num = await self._call(
            _IO_CALL_TIMEOUT,
            "CAN 报文接收",
            self._dll.ZCAN_Receive,
            chn_handle,
            ctypes.cast(rx_buffer, P_ZCAN_Receive_Data),
            max_count,
            wait_time_ms,
        )

        if not actual_num or actual_num <= 0:
            return []

        frames: list[CanRawFrame] = []
        for i in range(actual_num):
            item = rx_buffer[i]
            dlc = min(item.frame.can_dlc, 8)
            frame_data = bytes(item.frame.data[:dlc])
            frames.append(
                CanRawFrame(
                    can_id=item.frame.can_id,
                    data=frame_data,
                    is_extended=bool(item.frame.eff),
                    is_remote=bool(item.frame.rtr),
                    timestamp=item.timestamp,
                )
            )

        return frames

    async def clear_buffer(self, channel: int = 0) -> None:
        """异步清空通道缓冲区。"""
        chn_handle = self._channel_handles.get(channel)
        if chn_handle:
            await self._call(
                _C_CALL_TIMEOUT,
                f"清空通道 {channel} 缓冲区",
                self._dll.ZCAN_ClearBuffer,
                chn_handle,
            )

    async def close_channel(self, channel: int = 0) -> None:
        """异步重置并关闭指定通道。"""
        chn_handle = self._channel_handles.pop(channel, None)
        if chn_handle and chn_handle != INVALID_CHANNEL_HANDLE:
            await self._call(
                _C_CALL_TIMEOUT,
                f"关闭通道 {channel} ",
                self._dll.ZCAN_ResetCAN,
                chn_handle,
            )

    async def close_device(self) -> None:
        """异步关闭所有通道并释放设备句柄与线程池。"""
        # 1. 先关闭所有已打开的通道
        channels = list(self._channel_handles.keys())
        for chn in channels:
            try:
                await self.close_channel(chn)
            except Exception:
                pass

        # 2. 关闭设备
        handle = self._device_handle
        self._device_handle = INVALID_DEVICE_HANDLE
        if handle != INVALID_DEVICE_HANDLE:
            try:
                await self._call(
                    _C_CALL_TIMEOUT,
                    "关闭设备",
                    self._dll.ZCAN_CloseDevice,
                    handle,
                )
            except Exception:
                pass

    def shutdown_executor(self) -> None:
        """关闭线程池并取消排队任务。"""
        self._executor.shutdown(wait=False, cancel_futures=True)


class UnavailableCanDriver(ZlgCanDriver):
    """周立功动态库加载失败时的占位驱动。

    保持与 ``ZlgCanDriver`` 相同的接口，使程序仍能启动并在界面上展示失败原因；
    任何打开设备或收发操作都会抛出带原因的 ``CanDriverError``，释放类操作为空操作。
    """

    def __init__(self, reason: str) -> None:
        # 刻意不调用父类构造：不加载 DLL、不创建线程池。
        self.reason = reason
        self._device_handle = INVALID_DEVICE_HANDLE
        self._channel_handles = {}

    def _unavailable(self) -> CanDriverError:
        return CanDriverError(f"CAN 驱动加载失败: {self.reason}")

    async def open_device(self, device_type: int = 0, device_index: int = 0) -> None:
        raise self._unavailable()

    async def open_channel(self, channel: int = 0, baud_rate: int = 500000) -> None:
        raise self._unavailable()

    async def transmit(
        self,
        can_id: int,
        data: bytes,
        channel: int = 0,
        is_extended: bool = False,
        is_remote: bool = False,
    ) -> bool:
        raise self._unavailable()

    async def receive(
        self,
        channel: int = 0,
        max_count: int = 50,
        wait_time_ms: int = 1,
    ) -> list[CanRawFrame]:
        raise self._unavailable()

    async def clear_buffer(self, channel: int = 0) -> None:
        return None

    async def close_channel(self, channel: int = 0) -> None:
        return None

    async def close_device(self) -> None:
        return None

    def shutdown_executor(self) -> None:
        return None
