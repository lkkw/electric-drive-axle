"""PLC 通信监视：写入记录、反馈变化记录、心跳单独存放、与上电流程的联动。"""

import asyncio
import struct

from fastapi.testclient import TestClient

from app.core.plc.points import STATION_BLOCK_SIZE, build_power_on_block
from app.main import app
from app.schemas.plc import PlcConfig
from app.services.plc_traffic import PlcTrafficLog, point_names_for_bit
from tests.test_plc_manager import make_manager


def station_block(*, safe: bool = True, power_on: bool = False, heart: bool = False) -> bytearray:
    block = bytearray(STATION_BLOCK_SIZE)
    block[62] = int(heart) | (int(safe) << 1) | (int(power_on) << 2) | (int(power_on) << 3)
    struct.pack_into(">h", block, 66, 340 if power_on else 0)
    return block


def test_bit_write_records_only_that_point() -> None:
    log = PlcTrafficLog()
    # 字节 0 同时含心跳与请求上电：只改请求上电时不能把心跳也记一遍
    log.record_write(0, bytes([0b01]), "下电", only=point_names_for_bit(1))
    entries = log.entries()["entries"]
    assert [(e["name"], e["value"], e["source"]) for e in entries] == [("request_power", 0, "下电")]
    assert entries[0]["address"] == "DB40.DBX0.1"


def test_power_on_block_records_every_write_point() -> None:
    log = PlcTrafficLog()
    log.record_write(0, build_power_on_block(0), "PLC 上电")
    values = {e["name"]: e["value"] for e in log.entries()["entries"]}
    assert values == {
        "heart": 0,
        "request_power": 1,
        "put_product_type": 1,
        "request_voltage": 340,
        "result": 0,
    }


def test_sample_records_feedback_changes_after_baseline() -> None:
    log = PlcTrafficLog()
    log.sample(station_block())  # 第一次只建立基准
    assert log.entries()["entries"] == []

    log.sample(station_block(power_on=True))
    changes = {e["name"]: (e["previous"], e["value"]) for e in log.entries()["entries"]}
    assert changes == {"power_on": (0, 1), "connect": (0, 1), "out_voltage": (0, 340)}

    snapshot = log.snapshot()
    assert snapshot["updated_at"] is not None
    read = {p["name"]: p["value"] for p in snapshot["read"]}
    assert read["safe"] == 1 and read["out_voltage"] == 340


def test_heartbeat_kept_separately_and_does_not_evict_important_entries() -> None:
    log = PlcTrafficLog(max_entries=5, max_frequent_entries=3)
    log.sample(station_block())
    log.sample(station_block(safe=False))  # 重要记录
    for i in range(20):  # 大量心跳跳变
        log.sample(station_block(safe=False, heart=bool(i % 2 == 0)))

    entries = log.entries()["entries"]
    important = [e for e in entries if not e["frequent"]]
    frequent = [e for e in entries if e["frequent"]]
    assert [e["name"] for e in important] == ["safe"]
    assert len(frequent) == 3


def test_incremental_fetch_and_clear() -> None:
    log = PlcTrafficLog()
    log.record_write(0, build_power_on_block(0), "PLC 上电")
    first = log.entries()
    assert len(first["entries"]) == 5
    assert log.entries(after_seq=first["latest_seq"])["entries"] == []

    log.clear()
    assert log.entries()["entries"] == []


def test_manager_records_power_cycle_with_sources() -> None:
    async def run_test() -> None:
        manager, _, _ = make_manager()
        await manager.connect(PlcConfig(simulation=True))
        try:
            await manager.power_on()
            await manager.power_off()
        finally:
            await manager.shutdown()

        entries = manager.traffic.entries()["entries"]
        writes = [
            (e["name"], e["value"], e["source"]) for e in entries if e["direction"] == "write"
        ]
        assert ("request_power", 1, "PLC 上电") in writes
        assert ("request_voltage", 340, "PLC 上电") in writes
        assert ("request_power", 0, "下电") in writes
        reads = [
            (e["name"], e["previous"], e["value"]) for e in entries if e["direction"] == "read"
        ]
        assert ("power_on", 0, 1) in reads
        assert ("power_on", 1, 0) in reads
        # 断开后快照清空，下次连接重新建立基准
        assert manager.traffic.snapshot()["updated_at"] is None

    asyncio.run(run_test())


def test_traffic_api() -> None:
    client = TestClient(app)
    snapshot = client.get("/api/v1/plc/traffic/snapshot").json()
    assert [p["name"] for p in snapshot["write"]][:2] == ["heart", "request_power"]
    assert snapshot["read"][1]["address"] == "DB40.DBX62.1"

    log = client.get("/api/v1/plc/traffic/log", params={"after_seq": 0}).json()
    assert "latest_seq" in log and isinstance(log["entries"], list)

    assert client.delete("/api/v1/plc/traffic/log").json()["status"] == "success"
    assert client.get("/api/v1/plc/traffic/log").json()["entries"] == []
