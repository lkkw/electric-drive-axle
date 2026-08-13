"""SSE message creation and wire-format helpers."""

from datetime import UTC, datetime

from app.schemas.sse import SseMessage


class SseService:
    def create_message(self, sequence: int) -> SseMessage:
        return SseMessage(
            sequence=sequence,
            message=f"服务端实时消息 #{sequence}",
            timestamp=datetime.now(UTC),
        )

    def encode_event(self, message: SseMessage, *, retry_ms: int | None = None) -> str:
        """Encode one named SSE event; the final blank line is required."""
        lines = [
            f"id: {message.sequence}",
            "event: demo",
        ]
        if retry_ms is not None:
            lines.append(f"retry: {retry_ms}")
        lines.extend((f"data: {message.model_dump_json()}", "", ""))
        return "\n".join(lines)


sse_service = SseService()
