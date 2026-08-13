"""Server-Sent Events endpoint implemented with an async generator."""

import asyncio
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from app.services.sse_service import sse_service

router = APIRouter(prefix="/sse", tags=["SSE"])


async def generate_events(
    request: Request,
    *,
    interval_seconds: float,
    max_events: int | None = None,
) -> AsyncGenerator[str, None]:
    """Yield events until the browser disconnects or an optional limit is reached."""
    sequence = 1

    try:
        while max_events is None or sequence <= max_events:
            if await request.is_disconnected():
                break

            message = sse_service.create_message(sequence)
            yield sse_service.encode_event(
                message,
                retry_ms=3_000 if sequence == 1 else None,
            )
            sequence += 1

            # Keep an await cancellation point in an infinite stream. Never use time.sleep here.
            if max_events is None or sequence <= max_events:
                await asyncio.sleep(interval_seconds)
    except asyncio.CancelledError:
        # Let Starlette/Uvicorn finish cancellation and release the connection cleanly.
        raise


@router.get("/events", summary="订阅实时演示消息")
async def stream_events(
    request: Request,
    interval_seconds: float = Query(default=1.0, ge=0.1, le=30.0),
    max_events: int | None = Query(default=None, ge=1, le=100),
) -> StreamingResponse:
    """Open an SSE stream. `max_events` is useful for demos and automated tests."""
    return StreamingResponse(
        generate_events(
            request,
            interval_seconds=interval_seconds,
            max_events=max_events,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Disable buffering when the app is deployed behind Nginx.
            "X-Accel-Buffering": "no",
        },
    )
