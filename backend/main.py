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
    )


if __name__ == "__main__":
    main()
