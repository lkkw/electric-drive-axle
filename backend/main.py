"""Local development launcher for ``uv run main.py``.

The actual ASGI application remains in ``app.main`` so the backend can still
be imported, tested, and packaged as a regular Python package.
"""

import uvicorn


def main() -> None:
    """Start the FastAPI development server with automatic reload enabled."""
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        # 前端常开的 SSE 长连接（/stream）不会自己结束；不设超时时热重启会一直卡在
        # "Waiting for connections to close"。1 s 后强制关闭连接，继续重启。
        timeout_graceful_shutdown=1,
    )


if __name__ == "__main__":
    main()
