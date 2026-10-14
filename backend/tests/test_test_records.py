"""试车记录：试车统计累计、记录存储与筛选、CSV 导出、判定接口写入 PLC Result。"""

# 业务类名以 Test 开头（TestSession 等），按模块导入，避免被 pytest 当作测试类收集

import csv
import struct
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import test_records as schemas
from app.services import test_records as records
from app.services import test_session
from app.services.axle_manager import get_axle_manager
from app.services.plc_manager import get_plc_manager

client = TestClient(app)
PREFIX = "/api/v1/test-records"


def test_session_tracks_absolute_maximums_and_fault_codes() -> None:
    session = test_session.TestSession()
    assert session.snapshot().started_at is None

    session.on_mcu_2(speed_rpm=1200, torque_nm=-35.5)
    session.on_mcu_2(speed_rpm=-3000, torque_nm=20.0)  # 反转也按绝对值
    session.on_mcu_1(bus_current_a=-80.0, fault_code=64)
    session.on_mcu_1(bus_current_a=10.0, fault_code=64)  # 重复故障码只记一次
    session.on_mcu_1(bus_current_a=10.0, fault_code=0)
    session.on_temperature(motor_temp_c=60, controller_temp_c=45)
    session.on_temperature(motor_temp_c=55, controller_temp_c=50)
    session.on_safety_trip()

    stats = session.snapshot()
    assert stats.started_at is not None and stats.duration_s is not None
    assert stats.max_speed_rpm == 3000
    assert stats.max_torque_nm == 35.5
    assert stats.max_bus_current_a == 80.0
    assert stats.max_motor_temp_c == 60
    assert stats.max_controller_temp_c == 50
    assert stats.fault_codes == ["MCU_64"]
    assert stats.safety_trips == 1

    session.reset()
    assert session.snapshot() == schemas.TestSessionStats()


def test_fault_code_name_falls_back_to_raw_value() -> None:
    assert test_session.fault_code_name(64) == "MCU_64"
    assert test_session.fault_code_name(9999) == "MCU_9999"


def test_store_query_filters_and_csv_export(tmp_path: Path) -> None:
    store = records.TestRecordStore(tmp_path / "records.db", tmp_path / "exports")
    stats = schemas.TestSessionStats(max_speed_rpm=3000, fault_codes=["MCU_64", "MCU_135"])
    yesterday = datetime.now().astimezone() - timedelta(days=1)
    store.add(result=1, remark="", sn="SN-001", session=stats, plc_result_written=True)
    store.add(result=2, remark="异响", sn="SN-002", session=stats, plc_result_written=False)
    store.add(
        result=1,
        remark="",
        sn="SN-003",
        session=stats,
        plc_result_written=True,
        judged_at=yesterday,
    )

    all_records = store.query(records.TestRecordFilters())
    assert [r.sn for r in all_records] == ["SN-002", "SN-001", "SN-003"]  # 最新在前
    assert all_records[0].fault_codes == "MCU_64,MCU_135"
    assert all_records[0].plc_result_written is False

    assert [r.sn for r in store.query(records.TestRecordFilters(result=2))] == ["SN-002"]
    assert [r.sn for r in store.query(records.TestRecordFilters(sn="003"))] == ["SN-003"]
    today = date.today()
    assert len(store.query(records.TestRecordFilters(date_from=today, date_to=today))) == 2

    path = store.export_csv(all_records)
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0][:3] == ["判定时间", "序列号", "结论"]
    assert rows[1][1:4] == ["SN-002", "NG", "异响"]
    assert len(rows) == 4


def test_judge_without_plc_saves_record_and_resets_session() -> None:
    axle = get_axle_manager()
    axle.test_session.on_mcu_2(speed_rpm=1500, torque_nm=12.0)
    assert client.get(f"{PREFIX}/session").json()["max_speed_rpm"] == 1500

    response = client.post(f"{PREFIX}/judge", json={"result": 2, "remark": "过流"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["record"]["result"] == 2
    assert body["record"]["max_speed_rpm"] == 1500
    assert body["record"]["plc_result_written"] is False
    assert "未写入 PLC" in body["message"]

    # 判定后统计清零，开始下一台
    assert client.get(f"{PREFIX}/session").json()["started_at"] is None

    records = client.get(PREFIX, params={"result": 2}).json()
    assert any(r["id"] == body["record"]["id"] and r["remark"] == "过流" for r in records)


def test_judge_writes_result_to_simulated_plc() -> None:
    plc = get_plc_manager()
    response = client.post(
        "/api/v1/plc/connect",
        json={"ip": "192.168.8.1", "rack": 0, "slot": 1, "simulation": True},
    )
    assert response.status_code == 200
    try:
        response = client.post(f"{PREFIX}/judge", json={"result": 1})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["record"]["plc_result_written"] is True
        assert "已写入 PLC" in body["message"]
        assert plc.client is not None
        assert struct.unpack_from(">h", plc.client.read_station(), 6)[0] == 1
    finally:
        client.post("/api/v1/plc/disconnect")


def test_judge_rejects_invalid_result() -> None:
    assert client.post(f"{PREFIX}/judge", json={"result": 3}).status_code == 422
