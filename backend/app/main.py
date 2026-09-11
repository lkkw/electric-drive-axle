"""FastAPI application factory and ASGI entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import axle
from app.services.axle_manager import get_axle_manager

DEFAULT_FRONTEND_DIR = Path(__file__).resolve().parents[1] / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI 生命周期管理器。

    应用启动时执行 yield 前逻辑；应用关闭时执行 yield 后逻辑，
    确保在后台服务或桌面端退出时，安全下发停机指令并释放周立功 USBCAN 设备句柄。
    """
    # 启动阶段
    yield

    # 关闭阶段：安全清理电驱桥 CAN 硬件连接与底层驱动线程池
    manager = get_axle_manager()
    await manager.shutdown()


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
    description = (
        "基于 FastAPI + Vue 3 的电驱桥控制上位机，集成周立功 USBCAN 真实硬件驱动与 SSE 遥测流。"
    )
    application = FastAPI(
        title="电驱桥控制上位机系统",
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
    application.include_router(api_router)

    @application.get("/health", tags=["Health"], summary="健康检查")
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

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
