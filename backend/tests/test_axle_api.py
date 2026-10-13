"""Integration and API tests for Electric Drive Axle endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import axle_manager as axle_manager_module

client = TestClient(app)


def test_get_axle_status_initial() -> None:
    """测试初始未连接状态下的遥测接口。"""
    response = client.get("/api/v1/axle/status")
    assert response.status_code == 200
    data = response.json()
    assert "connected" in data
    assert "command" in data
    assert data["cycle_test"]["status"] in {"idle", "stopped"}
    assert "mcu_1" in data
    assert "mcu_2" in data
    assert "mcu_tbox" in data
    assert data["baud_rate"] == 500000
    assert data["command"]["gear_sts"] == 3  # 空挡 N


def test_update_axle_command() -> None:
    """测试更新上位机控制设定值。"""
    payload = {
        "torque_req": 200.0,
        "speed_req": 1500,
        "work_mode_req": 1,
        "mcu_en_cmd": 1,
        "gear_sts": 1,
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


def test_cycle_test_start_requires_connected_can() -> None:
    """未连接硬件时，后端循环任务不得获取控制权。"""
    response = client.post(
        "/api/v1/axle/cycle-test/start",
        json={
            "total_loops": 1,
            "steps": [
                {
                    "id": "forward",
                    "name": "正转",
                    "gear": 1,
                    "target_speed": 500,
                    "duration_seconds": 1,
                }
            ],
        },
    )
    assert response.status_code == 409
    assert "CAN 未连接" in response.json()["detail"]


def test_update_safety_config() -> None:
    """安全配置路由应保存配置，并拒绝超出 DBC 信号量程的阈值。"""
    original = client.get("/api/v1/axle/safety/config").json()
    payload = {
        "enabled": True,
        "max_motor_speed_rpm": 3200,
        "max_motor_torque_nm": 450.0,
        "max_motor_temp_c": 95.0,
        "feedback_timeout_ms": 800,
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


def test_update_safety_config_reports_persistence_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写盘失败时返回 500 并说明配置仅在本次运行中生效。"""
    original = client.get("/api/v1/axle/safety/config").json()

    def fail_save(*_: object) -> None:
        raise OSError("磁盘只读")

    monkeypatch.setattr(axle_manager_module, "save_safety_config", fail_save)
    try:
        response = client.put(
            "/api/v1/axle/safety/config",
            json={**original, "max_motor_speed_rpm": 2800},
        )
        assert response.status_code == 500
        assert "重启后将丢失" in response.json()["detail"]
    finally:
        monkeypatch.undo()
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


def test_emergency_reset_releases_interlock() -> None:
    """急停互锁需显式复位，复位后仅解除封锁而不恢复停机前的控制量。"""
    try:
        # 前序用例已触发急停，该接口幂等，这里显式确保处于互锁状态
        assert client.post("/api/v1/axle/emergency-stop").status_code == 200
        locked_status = client.get("/api/v1/axle/status").json()
        assert locked_status["is_emergency_locked"] is True

        blocked = client.post(
            "/api/v1/axle/command",
            json={"mcu_en_cmd": 1, "speed_req": 3000},
        )
        assert blocked.status_code == 409
        assert "急停锁定" in blocked.json()["detail"]

        response = client.post("/api/v1/axle/emergency-reset")
        assert response.status_code == 200
        state = response.json()
        assert state["mcu_en_cmd"] == 0
        assert state["torque_req"] == 0.0
        assert state["speed_req"] == 0
        assert state["gear_sts"] == 3  # 空挡
        assert state["work_mode_req"] == 0  # 模式归零为关闭

        unlocked_status = client.get("/api/v1/axle/status").json()
        assert unlocked_status["is_emergency_locked"] is False

        # 复位后普通控制指令重新放行
        allowed = client.post("/api/v1/axle/command", json={"mcu_en_cmd": 1})
        assert allowed.status_code == 200
    finally:
        # 全局单例贯穿整个测试会话，必须恢复为未锁定且归零的安全状态
        client.post(
            "/api/v1/axle/command",
            json={"mcu_en_cmd": 0, "speed_req": 0, "torque_req": 0, "gear_sts": 3},
        )


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
        "can_id": 0x258,
        "data_hex": "01 02 03 04 05 06 07 08",
        "is_extended": False,
        "is_remote": False,
    }
    response = client.post("/api/v1/axle/can/send", json=payload)
    assert response.status_code == 400
    assert "未连接" in response.json()["detail"]


def test_get_fault_codes_api() -> None:
    """测试获取 MCU 故障代码表 (DEF 三列)。"""
    response = client.get("/api/v1/axle/fault-codes")
    assert response.status_code == 200
    fault_codes = response.json()
    assert len(fault_codes) == 22
    first = fault_codes[0]
    assert first["code"] == "MCU_64"
    assert first["meaning"] == "VCE过流故障"
    assert "三级" in first["level"]
    assert first["raw_code"] == 64


def test_command_rejects_vehicle_only_signals_and_unused_gears() -> None:
    """空载台架只开放 D/R/N 与电机控制量，整车信号与 L/P 挡必须被拒绝。"""
    for payload in (
        {"active_discharge": 1},
        {"hand_brk_sts": 1},
        {"acc_position": 10.0},
        {"gear_sts": 4},
        {"gear_sts": 5},
    ):
        response = client.post("/api/v1/axle/command", json=payload)
        assert response.status_code == 422, payload
