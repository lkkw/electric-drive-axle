"""1 号工位的 PLC 读写客户端：真实 PLC（python-snap7）与本地仿真两种实现。

两种实现提供同样的同步接口，由 ``PlcPowerManager`` 放进线程池调用：

- ``read_station()``：一次读取工位全部 124 字节；
- ``update(offset, size, transform)``：在同一把锁内“读出 → 修改 → 写回”。
  心跳位与 Request_power 同在字节 0，必须这样写才不会互相覆盖。

snap7 的 Client 不支持并发访问，所有调用都在锁内串行执行。
"""

import struct
import threading
import time
from collections.abc import Callable
from typing import Protocol

from app.core.plc.points import (
    BIT_CONNECT,
    BIT_PLC_HEART,
    BIT_POWER_ON,
    BIT_REQUEST_POWER,
    BIT_SAFE,
    DB_NUMBER,
    OFFSET_GET_PRODUCT_TYPE,
    OFFSET_OUT_CURRENT,
    OFFSET_OUT_VOLTAGE,
    OFFSET_PC_STATUS,
    OFFSET_PLC_STATUS,
    OFFSET_PUT_PRODUCT_TYPE,
    OFFSET_REQUEST_VOLTAGE,
    STATION_BASE,
    STATION_BLOCK_SIZE,
    set_bit,
)

ByteTransform = Callable[[bytearray], bytes | bytearray]

# 单次 S7 收发超时。update() 是“读 + 写”两次往返，2 × 0.8 s 仍短于
# PlcPowerManager 的 2 s 调用超时，网络中断时调用能在超时前自行失败退出，
# 不会在线程里继续卡着（snap7 默认收超时 3 s，比调用超时还长）。
SNAP7_IO_TIMEOUT_SECONDS = 0.8


class PlcClientError(Exception):
    """PLC 连接或读写失败。"""


class StationClient(Protocol):
    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def read_station(self) -> bytearray: ...

    def update(self, offset: int, size: int, transform: ByteTransform) -> None: ...


def apply_io_timeout(client: object, seconds: float) -> None:
    """设置已连接 snap7 客户端的收发超时。

    基于 libsnap7 的版本通过 set_param 生效；纯 Python 实现（3.x）只把参数存起来，
    实际超时取连接对象的 socket 超时，所以两处都设置。
    """
    from snap7.type import Parameter

    millis = int(seconds * 1000)
    for param in (Parameter.SendTimeout, Parameter.RecvTimeout):
        try:
            client.set_param(param, millis)  # type: ignore[attr-defined]
        except Exception:
            pass
    connection = getattr(client, "connection", None)
    if connection is None:
        return
    if hasattr(connection, "timeout"):
        connection.timeout = seconds
    sock = getattr(connection, "socket", None)
    if sock is not None:
        sock.settimeout(seconds)


class SnapStationClient:
    """通过 python-snap7 访问真实 S7-1500（非优化块访问的 DB40）。"""

    def __init__(self, ip: str, rack: int, slot: int) -> None:
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self._lock = threading.Lock()
        self._client = None

    def connect(self) -> None:
        import snap7  # 延迟导入：仿真与测试不依赖真实协议栈

        with self._lock:
            if self._client is not None:
                return
            client = snap7.client.Client()
            try:
                client.connect(self.ip, self.rack, self.slot)
            except Exception as err:
                try:
                    client.disconnect()
                except Exception:
                    pass
                raise PlcClientError(
                    f"连接 PLC {self.ip} (rack={self.rack}, slot={self.slot}) 失败: {err}"
                ) from err
            apply_io_timeout(client, SNAP7_IO_TIMEOUT_SECONDS)
            self._client = client

    def disconnect(self) -> None:
        with self._lock:
            client, self._client = self._client, None
            if client is not None:
                try:
                    client.disconnect()
                except Exception:
                    pass

    def _require_client(self):  # noqa: ANN202 - snap7 类型在延迟导入中
        if self._client is None:
            raise PlcClientError("PLC 未连接")
        return self._client

    def read_station(self) -> bytearray:
        with self._lock:
            client = self._require_client()
            try:
                return client.db_read(DB_NUMBER, STATION_BASE, STATION_BLOCK_SIZE)
            except Exception as err:
                raise PlcClientError(f"读取 DB{DB_NUMBER} 失败: {err}") from err

    def update(self, offset: int, size: int, transform: ByteTransform) -> None:
        with self._lock:
            client = self._require_client()
            start = STATION_BASE + offset
            try:
                current = client.db_read(DB_NUMBER, start, size)
                client.db_write(DB_NUMBER, start, bytearray(transform(current)))
            except Exception as err:
                raise PlcClientError(f"写入 DB{DB_NUMBER}.DBB{start} 失败: {err}") from err


class SimulatedStationClient:
    """本地仿真 PLC：按时间推演 1 号工位的 PLC 反馈。

    - Safe 默认闭合，可通过 ``safe`` 属性模拟安全回路断开（PLC 随即断开接触器）；
    - Request_power=1 持续 ``power_on_delay_s`` 后置位 Power_on/Connect，
      回传产品编号，输出电压等于请求电压；
    - Request_power=0 持续 ``power_off_delay_s`` 后清除上述反馈；
    - PLC 心跳每秒翻转；``responsive=False`` 时模拟 PLC 不响应上电。
    """

    def __init__(
        self,
        *,
        power_on_delay_s: float = 1.5,
        power_off_delay_s: float = 0.5,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.power_on_delay_s = power_on_delay_s
        self.power_off_delay_s = power_off_delay_s
        self.safe = True
        self.responsive = True
        self._clock = clock
        self._lock = threading.Lock()
        self._memory = bytearray(STATION_BLOCK_SIZE)
        self._request_since: float | None = None
        self._release_since: float | None = None
        self._connected = False

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def _require_connected(self) -> None:
        if not self._connected:
            raise PlcClientError("PLC 未连接")

    def _set_plc_bit(self, bit: int, value: bool) -> None:
        self._memory[OFFSET_PLC_STATUS] = set_bit(self._memory[OFFSET_PLC_STATUS], bit, value)

    def _advance(self) -> None:
        now = self._clock()
        mem = self._memory
        self._set_plc_bit(BIT_PLC_HEART, int(now) % 2 == 1)
        self._set_plc_bit(BIT_SAFE, self.safe)

        request = bool(mem[OFFSET_PC_STATUS] & (1 << BIT_REQUEST_POWER))
        powered = bool(mem[OFFSET_PLC_STATUS] & (1 << BIT_POWER_ON))

        if not self.safe:
            # 安全回路断开时 PLC 自行切断主回路
            self._request_since = None
            self._set_supply(False)
            return

        if request:
            self._release_since = None
            if self._request_since is None:
                self._request_since = now
            if (
                self.responsive
                and not powered
                and now - self._request_since >= self.power_on_delay_s
            ):
                self._set_supply(True)
        else:
            self._request_since = None
            if powered:
                if self._release_since is None:
                    self._release_since = now
                if now - self._release_since >= self.power_off_delay_s:
                    self._release_since = None
                    self._set_supply(False)

    def _set_supply(self, on: bool) -> None:
        mem = self._memory
        self._set_plc_bit(BIT_POWER_ON, on)
        self._set_plc_bit(BIT_CONNECT, on)
        if on:
            mem[OFFSET_GET_PRODUCT_TYPE : OFFSET_GET_PRODUCT_TYPE + 2] = mem[
                OFFSET_PUT_PRODUCT_TYPE : OFFSET_PUT_PRODUCT_TYPE + 2
            ]
            mem[OFFSET_OUT_VOLTAGE : OFFSET_OUT_VOLTAGE + 2] = mem[
                OFFSET_REQUEST_VOLTAGE : OFFSET_REQUEST_VOLTAGE + 2
            ]
        else:
            struct.pack_into(">h", mem, OFFSET_OUT_VOLTAGE, 0)
        struct.pack_into(">h", mem, OFFSET_OUT_CURRENT, 0)

    def read_station(self) -> bytearray:
        with self._lock:
            self._require_connected()
            self._advance()
            return bytearray(self._memory)

    def update(self, offset: int, size: int, transform: ByteTransform) -> None:
        with self._lock:
            self._require_connected()
            current = bytearray(self._memory[offset : offset + size])
            self._memory[offset : offset + size] = bytes(transform(current))[:size]
            self._advance()
