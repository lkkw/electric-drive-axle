"""Unit tests for ZlgCanDriver hardware abstraction layer."""

import asyncio
import threading
from unittest.mock import MagicMock

import pytest

from app.core.can import driver as driver_module
from app.core.can.constants import BAUDRATE_TIMINGS
from app.core.can.driver import (
    CanChannelNotOpenError,
    CanDriverError,
    ZlgCanDriver,
    windows_high_resolution_timer,
)
from app.core.can.zlgcan_types import (
    ZCAN_STATUS_OK,
)


def test_baudrate_timings_mapping() -> None:
    """验证 SJA1000 经典波特率预分频寄存器映射表完备性。"""
    # 250kbps: (0x01, 0x1C)
    assert 250000 in BAUDRATE_TIMINGS
    assert BAUDRATE_TIMINGS[250000] == (0x01, 0x1C)

    # 电驱桥默认通信波特率 500kbps: (0x00, 0x1C)
    assert 500000 in BAUDRATE_TIMINGS
    assert BAUDRATE_TIMINGS[500000] == (0x00, 0x1C)

    # 1000kbps: (0x00, 0x14)
    assert 1000000 in BAUDRATE_TIMINGS
    assert BAUDRATE_TIMINGS[1000000] == (0x00, 0x14)


def test_windows_high_resolution_timer_context_manager() -> None:
    """验证 Windows 高精度多媒体定时器上下文管理器在进入与退出时的安全性。"""
    with windows_high_resolution_timer():
        # 在上下文管理器内正常执行
        x = 1 + 1
        assert x == 2


def test_open_channel_unsupported_baud_rate() -> None:
    """测试传入不支持的异常波特率时抛出 CanDriverError。"""

    async def run_test() -> None:
        driver = ZlgCanDriver()
        driver._device_handle = 12345  # 模拟设备已打开

        with pytest.raises(CanDriverError, match="不支持的波特率"):
            await driver.open_channel(channel=0, baud_rate=999999)

        driver.shutdown_executor()

    asyncio.run(run_test())


def test_open_channel_sja1000_timing_configured() -> None:
    """测试 open_channel 能够准确将 Timing0/Timing1 注入 InitCAN 结构体。"""

    async def run_test() -> None:
        driver = ZlgCanDriver()
        driver._device_handle = 12345

        mock_dll = MagicMock()
        mock_dll.ZCAN_SetValue.return_value = 0  # 模拟经典 USBCAN2 不支持 SetValue
        mock_dll.ZCAN_InitCAN.return_value = 88888  # 模拟通道句柄
        mock_dll.ZCAN_StartCAN.return_value = ZCAN_STATUS_OK
        driver._dll = mock_dll

        await driver.open_channel(channel=0, baud_rate=250000)

        assert driver.is_channel_open(0)
        # 验证 InitCAN 被调用
        mock_dll.ZCAN_InitCAN.assert_called_once()
        args = mock_dll.ZCAN_InitCAN.call_args[0]
        # args: (device_handle, channel, byref(init_cfg))
        assert args[0] == 12345
        assert args[1] == 0
        cfg_pointer = args[2]
        # 检查传入结构体中的 timing0 和 timing1
        cfg = cfg_pointer._obj
        assert cfg.config.can.timing0 == 0x01
        assert cfg.config.can.timing1 == 0x1C

        driver.shutdown_executor()

    asyncio.run(run_test())


def test_open_channel_default_baud_rate_500k() -> None:
    """测试不传 baud_rate 时 open_channel 默认使用 500k (timing0=0x00, timing1=0x1C)。"""

    async def run_test() -> None:
        driver = ZlgCanDriver()
        driver._device_handle = 12345

        mock_dll = MagicMock()
        mock_dll.ZCAN_SetValue.return_value = 0
        mock_dll.ZCAN_InitCAN.return_value = 88888
        mock_dll.ZCAN_StartCAN.return_value = ZCAN_STATUS_OK
        driver._dll = mock_dll

        # 不传 baud_rate，验证默认波特率参数生效
        await driver.open_channel(channel=0)

        assert driver.is_channel_open(0)
        mock_dll.ZCAN_InitCAN.assert_called_once()
        args = mock_dll.ZCAN_InitCAN.call_args[0]
        cfg_pointer = args[2]
        cfg = cfg_pointer._obj
        assert cfg.config.can.timing0 == 0x00
        assert cfg.config.can.timing1 == 0x1C

        driver.shutdown_executor()

    asyncio.run(run_test())


def test_transmit_serialization_lock() -> None:
    """测试 transmit 受内部锁保护，保证多协程发送的串行化。"""

    async def run_test() -> None:
        driver = ZlgCanDriver()
        driver._device_handle = 12345
        driver._channel_handles[0] = 88888

        active_calls = 0
        max_concurrent = 0

        def fake_transmit(chn: int, obj_ptr: object, count: int) -> int:
            nonlocal active_calls, max_concurrent
            active_calls += 1
            if active_calls > max_concurrent:
                max_concurrent = active_calls
            # 模拟微小耗时
            import time

            time.sleep(0.005)
            active_calls -= 1
            return 1

        mock_dll = MagicMock()
        mock_dll.ZCAN_Transmit.side_effect = fake_transmit
        driver._dll = mock_dll

        # 并发发送 10 帧报文
        coros = [driver.transmit(can_id=0x258, data=bytes([i] * 8), channel=0) for i in range(10)]
        results = await asyncio.gather(*coros)

        assert all(results)
        # 验证并发深度始终为 1 (完全被 tx_lock 串行化)
        assert max_concurrent == 1

        driver.shutdown_executor()

    asyncio.run(run_test())


def test_restart_channel_resets_then_starts_same_handle() -> None:
    """通道重启按复位、启动顺序调用，句柄保持不变；任一步失败抛出异常。"""

    async def run_test() -> None:
        driver = ZlgCanDriver()
        driver._device_handle = 12345
        driver._channel_handles[0] = 88888
        calls: list[tuple[str, int]] = []

        mock_dll = MagicMock()
        mock_dll.ZCAN_ResetCAN.side_effect = lambda chn: calls.append(("reset", chn)) or 1
        mock_dll.ZCAN_StartCAN.side_effect = lambda chn: calls.append(("start", chn)) or 1
        driver._dll = mock_dll

        await driver.restart_channel(0)
        assert calls == [("reset", 88888), ("start", 88888)]
        assert driver.is_channel_open(0)

        mock_dll.ZCAN_StartCAN.side_effect = None
        mock_dll.ZCAN_StartCAN.return_value = 0
        with pytest.raises(CanChannelNotOpenError, match="启动通道 0 失败"):
            await driver.restart_channel(0)

        with pytest.raises(CanChannelNotOpenError):
            await driver.restart_channel(1)

        driver.shutdown_executor()

    asyncio.run(run_test())


def test_read_channel_error_decodes_bus_off() -> None:
    """读取通道错误状态：解析总线关闭标志与错误数据；调用失败时抛异常。"""

    async def run_test() -> None:
        driver = ZlgCanDriver()
        driver._device_handle = 12345
        driver._channel_handles[0] = 88888

        def fake_read(chn: int, info_ptr: object) -> int:
            info = info_ptr._obj
            info.error_code = 0x0024
            info.passive_ErrData[0] = 0x19
            info.passive_ErrData[2] = 0xFF
            return 1

        mock_dll = MagicMock()
        mock_dll.ZCAN_ReadChannelErrInfo.side_effect = fake_read
        driver._dll = mock_dll

        info = await driver.read_channel_error(0)
        assert info.bus_off
        assert info.passive_err_data == bytes([0x19, 0x00, 0xFF])
        assert "总线关闭" in info.describe() and "错误被动" in info.describe()

        mock_dll.ZCAN_ReadChannelErrInfo.side_effect = None
        mock_dll.ZCAN_ReadChannelErrInfo.return_value = 0
        with pytest.raises(CanDriverError, match="错误状态失败"):
            await driver.read_channel_error(0)
        with pytest.raises(CanChannelNotOpenError):
            await driver.read_channel_error(1)
        driver.shutdown_executor()

    asyncio.run(run_test())


def test_blocked_transmit_does_not_starve_receive(monkeypatch: pytest.MonkeyPatch) -> None:
    """发送阻塞在驱动里时不再占用新线程，接收仍可执行；阻塞解除后发送恢复。"""
    monkeypatch.setattr(driver_module, "_IO_CALL_TIMEOUT", 0.02)

    async def run_test() -> None:
        driver = ZlgCanDriver(max_workers=2)
        driver._device_handle = 12345
        driver._channel_handles[0] = 88888
        release = threading.Event()
        transmit_calls = 0

        def blocking_transmit(chn: int, obj_ptr: object, count: int) -> int:
            nonlocal transmit_calls
            transmit_calls += 1
            release.wait(timeout=5)
            return 1

        mock_dll = MagicMock()
        mock_dll.ZCAN_Transmit.side_effect = blocking_transmit
        mock_dll.ZCAN_Receive.return_value = 0
        driver._dll = mock_dll

        for _ in range(4):
            with pytest.raises(CanDriverError, match="发送超时"):
                await driver.transmit(can_id=0x258, data=bytes(8), channel=0)
        assert transmit_calls == 1

        assert await driver.receive(channel=0) == []

        release.set()
        await asyncio.sleep(0.05)
        assert await driver.transmit(can_id=0x258, data=bytes(8), channel=0) is True
        assert transmit_calls == 2
        driver.shutdown_executor()

    asyncio.run(run_test())


def test_transmit_sets_remote_frame_flag() -> None:
    """原始报文接口传入远程帧标志时，驱动结构体必须设置 RTR 位。"""

    async def run_test() -> None:
        driver = ZlgCanDriver()
        driver._device_handle = 12345
        driver._channel_handles[0] = 88888
        captured_rtr: list[int] = []

        def fake_transmit(chn: int, obj_ptr: object, count: int) -> int:
            captured_rtr.append(obj_ptr._obj.frame.rtr)
            return 1

        mock_dll = MagicMock()
        mock_dll.ZCAN_Transmit.side_effect = fake_transmit
        driver._dll = mock_dll

        sent = await driver.transmit(
            can_id=0x258,
            data=bytes(8),
            channel=0,
            is_remote=True,
        )

        assert sent is True
        assert captured_rtr == [1]
        driver.shutdown_executor()

    asyncio.run(run_test())
