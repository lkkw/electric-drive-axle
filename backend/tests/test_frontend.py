from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def create_frontend_build(directory: Path) -> None:
    (directory / "assets").mkdir(parents=True)
    (directory / "index.html").write_text(
        '<!doctype html><html><body><div id="app">desktop</div></body></html>',
        encoding="utf-8",
    )
    (directory / "assets" / "app.js").write_text("console.log('ready')", encoding="utf-8")


def test_desktop_app_serves_vue_and_keeps_api_routes(tmp_path: Path) -> None:
    create_frontend_build(tmp_path)
    client = TestClient(create_app(serve_frontend=True, frontend_dir=tmp_path))

    root_response = client.get("/")
    fallback_response = client.get("/settings/profile", headers={"Accept": "text/html"})
    unknown_api_response = client.get("/api/v1/not-found")
    asset_response = client.get("/assets/app.js")
    api_response = client.get("/api/v1/demo")

    assert root_response.status_code == 200
    assert '<div id="app">desktop</div>' in root_response.text
    assert fallback_response.status_code == 200
    assert '<div id="app">desktop</div>' in fallback_response.text
    assert unknown_api_response.status_code == 404
    assert asset_response.text == "console.log('ready')"
    assert api_response.status_code == 200


def test_desktop_app_requires_a_frontend_build(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="Frontend build not found"):
        create_app(serve_frontend=True, frontend_dir=tmp_path)
