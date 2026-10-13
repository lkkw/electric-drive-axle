"""投产相关保障：版本一致性、日志落盘、驱动加载失败、单实例与关闭确认。"""

import asyncio
import json
import logging
import sys
import threading
import tomllib
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.core import logging_setup
from app.core.can.driver import CanDriverError
from app.core.config import get_settings
from app.main import app
from app.schemas.axle import CanConnectRequest, VcuCommandUpdateRequest
from app.services import axle_manager as axle_manager_module
from app.services.axle_manager import AxleManager
from desktop import acquire_single_instance, make_closing_handler, release_single_instance
from tests.test_axle_manager import create_mock_driver

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_versions_are_consistent_across_backend_and_frontend() -> None:
    pyproject = tomllib.loads((BACKEND_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    package = json.loads((BACKEND_DIR.parent / "frontend" / "package.json").read_text("utf-8"))

    assert pyproject["project"]["version"] == __version__
    assert package["version"] == __version__
    assert get_settings().app_version == __version__


def test_health_reports_version() -> None:
    response = TestClient(app).get("/health")
    assert response.json() == {"status": "ok", "version": __version__}


@pytest.fixture
def isolated_logging() -> object:
    """在隔离状态下测试日志配置，结束后恢复全局 logging 与异常钩子。"""
    root = logging.getLogger()
    events = logging.getLogger(logging_setup.EVENT_LOGGER_NAME)
    saved = (
        list(root.handlers),
        root.level,
        list(events.handlers),
        getattr(root, logging_setup._CONFIGURED_ATTR, False),
        sys.excepthook,
        threading.excepthook,
    )
    setattr(root, logging_setup._CONFIGURED_ATTR, False)
    yield
    for logger, handlers in ((root, saved[0]), (events, saved[2])):
        for handler in list(logger.handlers):
            if handler not in handlers:
                handler.close()
                logger.removeHandler(handler)
    root.setLevel(saved[1])
    setattr(root, logging_setup._CONFIGURED_ATTR, saved[3])
    sys.excepthook = saved[4]
    threading.excepthook = saved[5]


@pytest.mark.usefixtures("isolated_logging")
def test_configure_logging_writes_app_and_event_logs(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    logging_setup.configure_logging(log_dir)
    logging_setup.configure_logging(log_dir)  # 幂等：不应重复添加处理器

    logging.getLogger("app.axle_manager").warning("普通告警")
    logging.getLogger(logging_setup.EVENT_LOGGER_NAME).warning("紧急停机: 测试")
    for handler in logging.getLogger().handlers + logging.getLogger("app.events").handlers:
        handler.flush()

    app_log = (log_dir / "app.log").read_text(encoding="utf-8")
    event_log = (log_dir / "events.log").read_text(encoding="utf-8")
    assert "普通告警" in app_log
    assert "紧急停机: 测试" in app_log
    assert "紧急停机: 测试" in event_log
    assert "普通告警" not in event_log
    assert app_log.count("普通告警") == 1


def test_manager_survives_driver_load_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_driver() -> None:
        raise FileNotFoundError("未找到默认周立功动态库 zlgcan.dll")

    monkeypatch.setattr(axle_manager_module, "ZlgCanDriver", broken_driver)

    async def run_test() -> None:
        manager = AxleManager()
        telemetry = manager.get_telemetry()
        assert telemetry.driver_error is not None
        assert "zlgcan.dll" in telemetry.driver_error

        with pytest.raises(CanDriverError, match="CAN 驱动加载失败"):
            await manager.connect(CanConnectRequest())
        assert not manager.is_connected

        # 未连接时的断开、急停与退出都不能因缺少驱动而报错。
        await manager.disconnect()
        await manager.emergency_stop()
        await manager.shutdown()

    asyncio.run(run_test())


def test_event_log_records_manual_and_automatic_emergency_stop(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def run_test() -> None:
        manager = AxleManager(driver=create_mock_driver())
        await manager.emergency_stop()

    with caplog.at_level(logging.INFO, logger=logging_setup.EVENT_LOGGER_NAME):
        asyncio.run(run_test())

    messages = [r.getMessage() for r in caplog.records if r.name == "app.events"]
    assert "紧急停机: 操作员手动触发" in messages


def test_requires_close_confirmation_only_while_running() -> None:
    async def run_test() -> None:
        manager = AxleManager(driver=create_mock_driver())
        assert not manager.requires_close_confirmation

        await manager.connect(CanConnectRequest())
        try:
            assert not manager.requires_close_confirmation
            await manager.update_safety_config(
                manager.get_safety_config().model_copy(update={"enabled": False})
            )
            await manager.update_command(VcuCommandUpdateRequest(mcu_en_cmd=1))
            assert manager.requires_close_confirmation
            await manager.update_command(VcuCommandUpdateRequest(mcu_en_cmd=0))
            assert not manager.requires_close_confirmation
        finally:
            await manager.disconnect()

    asyncio.run(run_test())


def test_closing_handler_asks_only_when_axle_is_running() -> None:
    running = MagicMock(requires_close_confirmation=True)
    idle = MagicMock(requires_close_confirmation=False)
    confirm = MagicMock(return_value=False)

    assert make_closing_handler("t", lambda: None, confirm)() is True
    assert make_closing_handler("t", lambda: idle, confirm)() is True
    confirm.assert_not_called()

    # 运行中：操作员选“否”则取消关闭，选“是”才允许关闭。
    assert make_closing_handler("t", lambda: running, confirm)() is False
    confirm.return_value = True
    assert make_closing_handler("t", lambda: running, confirm)() is True
    assert confirm.call_count == 2


@pytest.mark.skipif(sys.platform != "win32", reason="命名互斥量仅在 Windows 上实现")
def test_single_instance_mutex_blocks_second_instance() -> None:
    name = f"Local\\axle-test-{uuid.uuid4()}"
    first = acquire_single_instance(name)
    try:
        assert first
        assert acquire_single_instance(name) is None
    finally:
        release_single_instance(first)

    again = acquire_single_instance(name)
    assert again
    release_single_instance(again)
