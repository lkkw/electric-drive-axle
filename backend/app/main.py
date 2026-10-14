"""FastAPI application factory and ASGI entry point."""

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging_setup import configure_logging
from app.routers import axle, plc, test_records
from app.services.axle_manager import get_axle_manager
from app.services.plc_manager import get_plc_manager


def _resolve_default_frontend_dir() -> Path:
    """解析打包（PyInstaller）或开发环境下的前端静态文件目录。"""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            p = Path(meipass) / "static"
            if p.is_dir():
                return p
        exe_dir = Path(sys.executable).resolve().parent
        for candidate in (exe_dir / "static", exe_dir / "_internal" / "static"):
            if candidate.is_dir():
                return candidate
    return Path(__file__).resolve().parents[1] / "static"


DEFAULT_FRONTEND_DIR = _resolve_default_frontend_dir()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI 生命周期管理器。

    应用启动时执行 yield 前逻辑；应用关闭时执行 yield 后逻辑，
    确保在后台服务或桌面端退出时，安全下发停机指令并释放周立功 USBCAN 设备句柄。
    """
    # 启动阶段：日志落盘（幂等，桌面入口可能已提前配置）
    settings = get_settings()
    configure_logging(settings.log_dir)
    logging.getLogger("app").info("%s v%s 启动", settings.app_name, settings.app_version)
    # 启动时就创建 PLC 管理器，确保急停联动（复位上电请求）始终已注册
    plc_manager = get_plc_manager()
    yield

    # 关闭阶段：先让电驱桥发停机帧并释放 USBCAN，再复位 PLC 上电请求切断高压
    manager = get_axle_manager()
    await manager.shutdown()
    await plc_manager.shutdown()


def create_app(
    *,
    serve_frontend: bool = False,
    frontend_dir: str | Path | None = None,
) -> FastAPI:
    """Create the API application and optionally serve a built Vue SPA.

    The normal development entry point keeps ``serve_frontend`` disabled because
    Vite serves the UI with hot reload. The PyWebView desktop entry point enables
    it and serves the bundled build from the same random local port.
    """
    settings = get_settings()
    description = "株齿2.5T电驱桥下线测试上位机系统，集成周立功 USBCAN 硬件驱动与 SSE 实时遥测流。"
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=description,
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Client-Name"],
    )

    api_router = APIRouter(prefix=settings.api_prefix)
    api_router.include_router(axle.router)
    api_router.include_router(plc.router)
    api_router.include_router(test_records.router)
    application.include_router(api_router)

    @application.get("/health", tags=["Health"], summary="健康检查")
    async def health_check() -> dict[str, str]:
        return {"status": "ok", "version": settings.app_version}

    if serve_frontend:
        static_dir = Path(frontend_dir) if frontend_dir is not None else DEFAULT_FRONTEND_DIR
        index_file = static_dir / "index.html"
        if not index_file.is_file():
            raise RuntimeError(
                f"Frontend build not found at {index_file}. "
                "Run `uv run python build.py --prepare-only` first."
            )

        # Register after the API routes. FastAPI checks the backend routes first
        # and falls back to index.html for Vue Router history-mode URLs.
        application.frontend(
            "/",
            directory=static_dir,
            fallback="index.html",
        )

    return application


app = create_app()
