"""Small service layer used by the REST examples."""

from datetime import UTC, datetime
from uuid import uuid4

from app.schemas.demo import DemoEchoRequest, DemoEchoResponse, DemoResponse


class DemoService:
    """Keep business logic out of the router so it can grow independently."""

    def get_demo(self) -> DemoResponse:
        return DemoResponse(
            message="FastAPI REST 服务运行正常",
            server_time=datetime.now(UTC),
            request_id=uuid4(),
        )

    def echo(self, payload: DemoEchoRequest) -> DemoEchoResponse:
        return DemoEchoResponse(
            reply=f"{payload.name}，后端已收到：{payload.message}",
            received_at=datetime.now(UTC),
        )


demo_service = DemoService()
