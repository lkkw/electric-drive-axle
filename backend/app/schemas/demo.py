"""Schemas used by the REST demo endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DemoResponse(BaseModel):
    message: str
    server_time: datetime
    request_id: UUID


class DemoEchoRequest(BaseModel):
    name: str = Field(min_length=1, max_length=50, examples=["Vue"])
    message: str = Field(min_length=1, max_length=200, examples=["Hello FastAPI"])


class DemoEchoResponse(BaseModel):
    reply: str
    received_at: datetime
