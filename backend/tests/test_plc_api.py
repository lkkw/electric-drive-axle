"""PLC 接口：仿真模式下完整走一遍连接 → 上电 → 下电 → 断开。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
PREFIX = "/api/v1/plc"


def test_plc_status_before_connect() -> None:
    data = client.get(f"{PREFIX}/status").json()
    assert data["connected"] is False
    assert data["target_voltage"] == 340
    assert data["product_type_expected"] == 1


def test_power_on_requires_connected_plc() -> None:
    response = client.post(f"{PREFIX}/power-on")
    assert response.status_code == 409
    assert "未连接" in response.json()["detail"]


def test_connect_rejects_invalid_ip() -> None:
    response = client.post(f"{PREFIX}/connect", json={"ip": "10.30.73", "rack": 0, "slot": 1})
    assert response.status_code == 422


def test_simulated_power_cycle_via_api() -> None:
    response = client.post(
        f"{PREFIX}/connect",
        json={"ip": "192.168.8.1", "rack": 0, "slot": 1, "simulation": True},
    )
    assert response.status_code == 200
    assert response.json()["connected"] is True
    try:
        response = client.post(f"{PREFIX}/power-on")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "success"
        assert body["plc"]["power_state"] == "powered"
        assert body["plc"]["output_voltage"] == 340

        # 供电中禁止断开 PLC（会失去 Safe 联锁）
        response = client.post(f"{PREFIX}/disconnect")
        assert response.status_code == 409

        response = client.post(f"{PREFIX}/power-off")
        assert response.status_code == 200
        assert response.json()["plc"]["contactor_closed"] is False

        # 仿真安全回路断开后禁止上电
        assert client.post(f"{PREFIX}/simulation/safe", json={"safe": False}).status_code == 200
        response = client.post(f"{PREFIX}/power-on")
        assert response.status_code == 409
        assert "Safe=0" in response.json()["detail"]
        client.post(f"{PREFIX}/simulation/safe", json={"safe": True})
    finally:
        final = client.post(f"{PREFIX}/disconnect")
        assert final.status_code == 200

    assert client.get(f"{PREFIX}/status").json()["connected"] is False
