"""Standard REST endpoints."""

from fastapi import APIRouter, status

from app.schemas.demo import DemoEchoRequest, DemoEchoResponse, DemoResponse
from app.services.demo_service import demo_service

router = APIRouter(prefix="/demo", tags=["Demo REST"])


@router.get("", response_model=DemoResponse, summary="读取演示数据")
async def get_demo() -> DemoResponse:
    """Return a small payload used by the Vue/Pinia demo."""
    return demo_service.get_demo()


@router.post(
    "/echo",
    response_model=DemoEchoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="回显提交的数据",
)
async def echo_demo(payload: DemoEchoRequest) -> DemoEchoResponse:
    """Show request-body validation and a service-layer call."""
    return demo_service.echo(payload)
