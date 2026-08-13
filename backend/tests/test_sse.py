import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_sse_stream_can_finish_with_a_limit() -> None:
    with client.stream(
        "GET",
        "/api/v1/sse/events?interval_seconds=0.1&max_events=2",
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert body.count("event: demo") == 2
    assert "retry: 3000" in body

    data_lines = [
        line.removeprefix("data: ") for line in body.splitlines() if line.startswith("data: ")
    ]
    messages = [json.loads(line) for line in data_lines]
    assert [message["sequence"] for message in messages] == [1, 2]
