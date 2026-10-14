"""试车记录持久化（SQLite，标准库 sqlite3）与 CSV 导出。

每次操作员判定合格 / NG 时保存一条，判定时间按 UTC 保存，查询时按本地日期过滤。
"""

import csv
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.schemas.test_records import TestRecord, TestSessionStats

_COLUMNS = (
    "timestamp",
    "sn",
    "result",
    "remark",
    "started_at",
    "duration_s",
    "max_speed_rpm",
    "max_torque_nm",
    "max_motor_temp_c",
    "max_controller_temp_c",
    "max_bus_current_a",
    "fault_codes",
    "safety_trips",
    "plc_result_written",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS test_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    sn TEXT,
    result INTEGER NOT NULL,
    remark TEXT NOT NULL DEFAULT '',
    started_at TEXT,
    duration_s REAL,
    max_speed_rpm INTEGER,
    max_torque_nm REAL,
    max_motor_temp_c REAL,
    max_controller_temp_c REAL,
    max_bus_current_a REAL,
    fault_codes TEXT NOT NULL DEFAULT '',
    safety_trips INTEGER NOT NULL DEFAULT 0,
    plc_result_written INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_test_records_timestamp ON test_records (timestamp);
CREATE INDEX IF NOT EXISTS idx_test_records_sn ON test_records (sn);
"""

CSV_HEADERS = (
    "判定时间",
    "序列号",
    "结论",
    "备注",
    "试车时长(s)",
    "最高转速(RPM)",
    "最大转矩(Nm)",
    "最高电机温度(℃)",
    "最高控制器温度(℃)",
    "最大母线电流(A)",
    "故障码",
    "安全停机次数",
    "已写入 PLC",
)


@dataclass(frozen=True, slots=True)
class TestRecordFilters:
    date_from: date | None = None
    date_to: date | None = None
    sn: str | None = None
    result: int | None = None


def _utc_iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def _local_day_start_utc(day: date) -> str:
    """本地日期 0 点对应的 UTC 时间字符串（与保存格式一致，可直接按字符串比较）。"""
    return _utc_iso(datetime(day.year, day.month, day.day).astimezone())


def _local_time_text(value: str | None) -> str:
    if not value:
        return ""
    return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _blank(value: Any) -> Any:
    return "" if value is None else value


class TestRecordStore:
    """试车记录的增查与导出；sqlite 连接按次打开，线程安全。"""

    def __init__(self, db_path: Path, export_dir: Path) -> None:
        self._db_path = db_path
        self._export_dir = export_dir
        self._lock = threading.Lock()
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        if not self._initialized:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        if not self._initialized:
            conn.executescript(_SCHEMA)
            self._initialized = True
        return conn

    def add(
        self,
        *,
        result: int,
        remark: str,
        sn: str | None,
        session: TestSessionStats,
        plc_result_written: bool,
        judged_at: datetime | None = None,
    ) -> TestRecord:
        values: dict[str, Any] = {
            "timestamp": _utc_iso(judged_at or datetime.now(UTC)),
            "sn": sn or None,
            "result": result,
            "remark": remark.strip(),
            "started_at": session.started_at,
            "duration_s": session.duration_s,
            "max_speed_rpm": session.max_speed_rpm,
            "max_torque_nm": session.max_torque_nm,
            "max_motor_temp_c": session.max_motor_temp_c,
            "max_controller_temp_c": session.max_controller_temp_c,
            "max_bus_current_a": session.max_bus_current_a,
            "fault_codes": ",".join(session.fault_codes),
            "safety_trips": session.safety_trips,
            "plc_result_written": int(plc_result_written),
        }
        placeholders = ", ".join("?" for _ in _COLUMNS)
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                f"INSERT INTO test_records ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
                [values[name] for name in _COLUMNS],
            )
            record_id = cursor.lastrowid
        conn.close()
        values["plc_result_written"] = plc_result_written
        return TestRecord(id=int(record_id or 0), **values)

    def query(self, filters: TestRecordFilters, limit: int = 500) -> list[TestRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if filters.date_from:
            clauses.append("timestamp >= ?")
            params.append(_local_day_start_utc(filters.date_from))
        if filters.date_to:
            clauses.append("timestamp < ?")
            params.append(_local_day_start_utc(filters.date_to + timedelta(days=1)))
        if filters.sn:
            clauses.append("sn LIKE ?")
            params.append(f"%{filters.sn.strip()}%")
        if filters.result:
            clauses.append("result = ?")
            params.append(filters.result)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM test_records {where} ORDER BY timestamp DESC, id DESC LIMIT ?",
                [*params, limit],
            ).fetchall()
        conn.close()
        return [
            TestRecord(**{**dict(row), "plc_result_written": bool(row["plc_result_written"])})
            for row in rows
        ]

    def export_csv(self, records: list[TestRecord]) -> Path:
        """写出 CSV（utf-8-sig，Excel 可直接打开中文）。"""
        self._export_dir.mkdir(parents=True, exist_ok=True)
        path = self._export_dir / f"试车记录_{datetime.now():%Y%m%d_%H%M%S}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADERS)
            for r in records:
                writer.writerow(
                    [
                        _local_time_text(r.timestamp),
                        r.sn or "",
                        "合格" if r.result == 1 else "NG",
                        r.remark,
                        _blank(r.duration_s),
                        _blank(r.max_speed_rpm),
                        _blank(r.max_torque_nm),
                        _blank(r.max_motor_temp_c),
                        _blank(r.max_controller_temp_c),
                        _blank(r.max_bus_current_a),
                        r.fault_codes,
                        r.safety_trips,
                        "是" if r.plc_result_written else "否",
                    ]
                )
        return path


_global_store: TestRecordStore | None = None


def get_test_record_store() -> TestRecordStore:
    global _global_store
    if _global_store is None:
        settings = get_settings()
        _global_store = TestRecordStore(settings.test_records_db_path, settings.export_dir)
    return _global_store
