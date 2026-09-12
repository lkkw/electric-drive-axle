"""Integration and API tests for Electric Drive Axle endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get_axle_status_initial() -> None:
    """测试初始未连接状态下的遥测接口。"""
    response = client.get("/api/v1/axle/status")
    assert response.status_code == 200
    data = response.json()
    assert "connected" in data
    assert "command" in data
    assert "mcu_1" in data
    assert "mcu_2" in data
    assert "mcu_tbox" in data
    assert data["command"]["gear_sts"] == 3  # 空挡 N


def test_update_axle_command() -> None:
    """测试更新上位机控制设定值。"""
    payload = {
        "torque_req": 200.0,
        "speed_req": 1500,
        "work_mode_req": 1,
        "mcu_en_cmd": 1,
        "gear_sts": 1,
        "active_discharge": 0,
    }
    response = client.post("/api/v1/axle/command", json=payload)
    assert response.status_code == 200
    state = response.json()
    assert state["torque_req"] == 200.0
    assert state["speed_req"] == 1500
    assert state["mcu_en_cmd"] == 1
    assert state["gear_sts"] == 1

    # 验证读取到的状态已同步更新
    status_resp = client.get("/api/v1/axle/status")
    assert status_resp.status_code == 200
    cmd_data = status_resp.json()["command"]
    assert cmd_data["torque_req"] == 200.0
    assert cmd_data["speed_req"] == 1500


def test_update_safety_config() -> None:
    """安全配置路由应保存配置，并拒绝超出 DBC 信号量程的阈值。"""
    original = client.get("/api/v1/axle/safety/config").json()
    payload = {
        "enabled": True,
        "max_motor_speed_rpm": 3200,
        "max_motor_torque_nm": 450.0,
        "max_motor_temp_c": 95.0,
    }

    try:
        response = client.put("/api/v1/axle/safety/config", json=payload)
        assert response.status_code == 200
        assert response.json() == payload

        status_data = client.get("/api/v1/axle/status").json()
        assert status_data["safety"]["config"] == payload

        invalid_response = client.put(
            "/api/v1/axle/safety/config",
            json={**payload, "max_motor_temp_c": 211.0},
        )
        assert invalid_response.status_code == 422
    finally:
        client.put("/api/v1/axle/safety/config", json=original)


def test_emergency_stop() -> None:
    """测试紧急停机接口。"""
    response = client.post("/api/v1/axle/emergency-stop")
    assert response.status_code == 200
    state = response.json()
    assert state["mcu_en_cmd"] == 0
    assert state["torque_req"] == 0.0
    assert state["speed_req"] == 0
    assert state["gear_sts"] == 3  # 强制空挡


def test_disconnect_when_idle() -> None:
    """测试未连接时调用断开接口应安全返回。"""
    response = client.post("/api/v1/axle/disconnect")
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_clear_can_frames() -> None:
    """测试清空报文监视缓冲区。"""
    response = client.post("/api/v1/axle/can/clear-frames")
    assert response.status_code == 200
    assert response.json()["success"] is True

    status_resp = client.get("/api/v1/axle/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["recent_frames"] == []


def test_send_raw_can_frame_not_connected() -> None:
    """测试硬件未连接时手动下发报文应返回 400 提示未连接。"""
    payload = {
        "can_id": 0x314,
        "data_hex": "01 02 03 04 05 06 07 08",
        "is_extended": False,
        "is_remote": False,
    }
    response = client.post("/api/v1/axle/can/send", json=payload)
    assert response.status_code == 400
    assert "未连接" in response.json()["detail"]
