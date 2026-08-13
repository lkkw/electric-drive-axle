"""Schemas carried by the SSE event stream."""

from datetime import datetime

from pydantic import BaseModel


class SseMessage(BaseModel):
    sequence: int
    message: str
    timestamp: datetime
