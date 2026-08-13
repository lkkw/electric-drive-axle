"""FastAPI application factory and ASGI entry point."""

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import demo, sse

DEFAULT_FRONTEND_DIR = Path(__file__).resolve().parents[1] / "static"


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
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="RESTful API and Server-Sent Events starter backend.",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Client-Name"],
    )

    api_router = APIRouter(prefix=settings.api_prefix)
    api_router.include_router(demo.router)
    api_router.include_router(sse.router)
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
