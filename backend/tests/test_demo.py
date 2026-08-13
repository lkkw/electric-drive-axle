from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_demo() -> None:
    response = client.get("/api/v1/demo")

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "FastAPI REST 服务运行正常"
    assert payload["request_id"]
    assert payload["server_time"]


def test_echo_demo() -> None:
    response = client.post(
        "/api/v1/demo/echo",
        json={"name": "Vue", "message": "Hello FastAPI"},
    )

    assert response.status_code == 201
    assert response.json()["reply"] == "Vue，后端已收到：Hello FastAPI"


def test_cors_preflight_allows_the_vite_origin() -> None:
    response = client.options(
        "/api/v1/demo",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
