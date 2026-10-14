"""PLC 通信监视：记录上位机写给 PLC 的每一次内容，以及 PLC 反馈值的变化。

移植自 magmit 项目的 PLC 通信监视，按本台架只用 1 号工位做了简化：

- 写入：``PlcPowerManager`` 每次写成功后调用 ``record_write``，附带“来源”
  （PLC 上电、下电、Safe 断开自动复位、急停联动……）。单个位写入只记录那一位，
  避免每秒的心跳把“请求上电 = 0”也记一遍。
- 读取：常驻监视每 0.2 s 读取整个工位时调用 ``sample``，PLC 反馈区数值变化时记一条。
  不额外产生 PLC 通讯。
- 只在内存中保留。心跳每秒都有，单独存放并只保留最近 ``MAX_FREQUENT_ENTRIES`` 条，
  避免把上电、Safe 变化等重要记录挤掉。
"""

import struct
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from app.core.plc import points as p

MAX_ENTRIES = 500
MAX_FREQUENT_ENTRIES = 200

Direction = Literal["write", "read"]
PointType = Literal["BOOL", "INT", "REAL", "STRING"]


@dataclass(frozen=True, slots=True)
class TrafficPoint:
    name: str
    label: str
    direction: Direction
    offset: int
    data_type: PointType
    bit: int = 0
    frequent: bool = False

    @property
    def address(self) -> str:
        start = p.STATION_BASE + self.offset
        if self.data_type == "BOOL":
            return f"DB{p.DB_NUMBER}.DBX{start}.{self.bit}"
        if self.data_type == "INT":
            return f"DB{p.DB_NUMBER}.DBW{start}"
        if self.data_type == "REAL":
            return f"DB{p.DB_NUMBER}.DBD{start}"
        return f"DB{p.DB_NUMBER}.DBB{start} STRING[30]"

    @property
    def size(self) -> int:
        return {"BOOL": 1, "INT": 2, "REAL": 4, "STRING": p.SN_MAX_LENGTH + 2}[self.data_type]

    def decode(self, block: bytes | bytearray, base_offset: int = 0) -> Any:
        """从 ``block`` 中解码本点位；``base_offset`` 为 block[0] 对应的工位内偏移。"""
        at = self.offset - base_offset
        if self.data_type == "BOOL":
            return int(bool(block[at] & (1 << self.bit)))
        if self.data_type == "INT":
            return struct.unpack_from(">h", block, at)[0]
        if self.data_type == "REAL":
            return round(struct.unpack_from(">f", block, at)[0], 2)
        length = min(block[at + 1], p.SN_MAX_LENGTH, len(block) - at - 2)
        return bytes(block[at + 2 : at + 2 + length]).decode("latin-1", errors="replace").strip()


POINTS: tuple[TrafficPoint, ...] = (
    # 上位机 → PLC
    TrafficPoint(
        "heart", "上位机心跳", "write", p.OFFSET_PC_STATUS, "BOOL", p.BIT_PC_HEART, frequent=True
    ),
    TrafficPoint(
        "request_power", "请求上电", "write", p.OFFSET_PC_STATUS, "BOOL", p.BIT_REQUEST_POWER
    ),
    TrafficPoint("put_product_type", "产品编号", "write", p.OFFSET_PUT_PRODUCT_TYPE, "INT"),
    TrafficPoint("request_voltage", "产品电压", "write", p.OFFSET_REQUEST_VOLTAGE, "INT"),
    TrafficPoint("result", "测试结果", "write", p.OFFSET_RESULT, "INT"),
    TrafficPoint("speed", "实时转速", "write", p.OFFSET_SPEED, "REAL", frequent=True),
    TrafficPoint("temp", "电机温度", "write", p.OFFSET_TEMP, "REAL", frequent=True),
    # PLC → 上位机
    TrafficPoint(
        "plc_heart", "PLC 心跳", "read", p.OFFSET_PLC_STATUS, "BOOL", p.BIT_PLC_HEART, frequent=True
    ),
    TrafficPoint("safe", "安全信号 Safe", "read", p.OFFSET_PLC_STATUS, "BOOL", p.BIT_SAFE),
    TrafficPoint("power_on", "上电完成", "read", p.OFFSET_PLC_STATUS, "BOOL", p.BIT_POWER_ON),
    TrafficPoint("connect", "主接触器吸合", "read", p.OFFSET_PLC_STATUS, "BOOL", p.BIT_CONNECT),
    TrafficPoint("get_product_type", "编号回传", "read", p.OFFSET_GET_PRODUCT_TYPE, "INT"),
    TrafficPoint("out_voltage", "输出电压", "read", p.OFFSET_OUT_VOLTAGE, "INT"),
    TrafficPoint("out_current", "输出电流", "read", p.OFFSET_OUT_CURRENT, "INT"),
    TrafficPoint("sn", "产品序列号", "read", p.OFFSET_SN, "STRING"),
)


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


class PlcTrafficLog:
    """内存中的 PLC 通信记录与最新点表快照（线程安全）。"""

    def __init__(
        self,
        max_entries: int = MAX_ENTRIES,
        max_frequent_entries: int = MAX_FREQUENT_ENTRIES,
    ) -> None:
        self._lock = threading.Lock()
        self._entries: deque[dict[str, Any]] = deque(maxlen=max_entries)
        self._frequent: deque[dict[str, Any]] = deque(maxlen=max_frequent_entries)
        self._seq = 0
        self._snapshot: dict[str, Any] = {}
        self._snapshot_at: str | None = None
        self._baseline: dict[str, Any] | None = None

    def _append(self, point: TrafficPoint, value: Any, previous: Any, source: str) -> None:
        self._seq += 1
        target = self._frequent if point.frequent else self._entries
        target.append(
            {
                "seq": self._seq,
                "time": _now(),
                "direction": point.direction,
                "name": point.name,
                "label": point.label,
                "address": point.address,
                "value": value,
                "previous": previous,
                "source": source,
                "frequent": point.frequent,
            }
        )

    def record_write(
        self,
        offset: int,
        data: bytes | bytearray,
        source: str,
        *,
        only: tuple[str, ...] | None = None,
    ) -> None:
        """记录一次写入（``data`` 为写入后的字节，从工位内偏移 ``offset`` 开始）。

        ``only`` 指定实际要写的点位（例如只改了请求上电那一位）；为 None 时记录
        这段字节覆盖到的全部写区点位（例如上电时一次写入的 14 字节）。
        """
        end = offset + len(data)
        with self._lock:
            for point in POINTS:
                if point.direction != "write":
                    continue
                if only is not None and point.name not in only:
                    continue
                if point.offset < offset or point.offset + point.size > end:
                    continue
                self._append(point, point.decode(data, offset), None, source)

    def sample(self, block: bytes | bytearray) -> None:
        """常驻监视每次读取整个工位后调用：PLC 反馈区数值变化时记一条。"""
        values = {point.name: point.decode(block) for point in POINTS}
        with self._lock:
            baseline = self._baseline
            if baseline is not None:
                for point in POINTS:
                    if point.direction != "read":
                        continue
                    if baseline.get(point.name) != values[point.name]:
                        self._append(point, values[point.name], baseline.get(point.name), "")
            self._baseline = values
            self._snapshot = values
            self._snapshot_at = datetime.now().strftime("%H:%M:%S")

    def reset_baseline(self) -> None:
        """PLC 断开时调用：清空快照；重新连上后的第一次采样只建立基准、不产生记录。"""
        with self._lock:
            self._baseline = None
            self._snapshot = {}
            self._snapshot_at = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            values = dict(self._snapshot)
            updated_at = self._snapshot_at
        sides: dict[str, list[dict[str, Any]]] = {"write": [], "read": []}
        for point in POINTS:
            sides[point.direction].append(
                {
                    "name": point.name,
                    "label": point.label,
                    "address": point.address,
                    "value": values.get(point.name),
                }
            )
        return {"updated_at": updated_at, **sides}

    def entries(self, after_seq: int = 0) -> dict[str, Any]:
        with self._lock:
            items = [e for e in (*self._entries, *self._frequent) if e["seq"] > after_seq]
            items.sort(key=lambda e: e["seq"])
            return {"latest_seq": self._seq, "entries": items}

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._frequent.clear()


def point_names_for_bit(bit: int) -> tuple[str, ...]:
    """字节 0 的位号 → 写区点位名（用于单个位写入只记录那一位）。"""
    for point in POINTS:
        if point.direction == "write" and point.data_type == "BOOL" and point.bit == bit:
            return (point.name,)
    return ()
