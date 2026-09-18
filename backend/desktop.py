"""Windows desktop launcher for the bundled FastAPI + Vue application."""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
from contextlib import suppress
from urllib.request import Request, urlopen

import uvicorn

from app.core.config import get_settings
from app.main import create_app

HOST = "127.0.0.1"
STARTUP_TIMEOUT_SECONDS = 15.0
SHUTDOWN_TIMEOUT_SECONDS = 10.0


class UvicornThread(threading.Thread):
    """Run Uvicorn in the background while PyWebView owns the main thread."""

    def __init__(self, server: uvicorn.Server, listener: socket.socket) -> None:
        super().__init__(name="uvicorn-desktop", daemon=True)
        self.server = server
        self.listener = listener
        self.error: Exception | None = None

    def run(self) -> None:
        try:
            self.server.run(sockets=[self.listener])
        except Exception as error:  # pragma: no cover - defensive GUI startup path
            self.error = error


def reserve_local_port() -> tuple[socket.socket, int]:
    """Bind an OS-assigned port and keep the socket reserved for Uvicorn."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((HOST, 0))
    listener.set_inheritable(True)
    port = int(listener.getsockname()[1])
    return listener, port


def wait_until_started(server: uvicorn.Server, thread: UvicornThread) -> None:
    """Wait until Uvicorn is accepting requests or fail with a useful error."""
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS

    while not server.started:
        if thread.error is not None:
            raise RuntimeError("Uvicorn failed to start") from thread.error
        if not thread.is_alive():
            raise RuntimeError("Uvicorn stopped before the desktop window opened")
        if time.monotonic() >= deadline:
            raise TimeoutError("Timed out while waiting for the local backend to start")
        time.sleep(0.05)


def stop_server(
    server: uvicorn.Server,
    thread: UvicornThread,
    listener: socket.socket,
) -> None:
    """Request graceful shutdown and release the reserved socket."""
    server.should_exit = True
    thread.join(timeout=SHUTDOWN_TIMEOUT_SECONDS)

    if thread.is_alive():
        server.force_exit = True
        thread.join(timeout=1.0)

    with suppress(OSError):
        listener.close()


def verify_local_server(base_url: str) -> None:
    """Exercise bundled frontend, REST, health, and SSE routes without opening a GUI."""
    checks = (
        ("/", "text/html"),
        ("/health", "application/json"),
        ("/api/v1/axle/status", "application/json"),
        ("/api/v1/axle/stream", "text/event-stream"),
    )

    for path, expected_content_type in checks:
        request = Request(f"{base_url}{path}", headers={"Accept": expected_content_type})
        with urlopen(request, timeout=5.0) as response:  # noqa: S310 - fixed loopback URL
            content_type = response.headers.get_content_type()
            if expected_content_type == "text/event-stream":
                data = response.readline()
                if not data:
                    raise RuntimeError("SSE stream returned empty initial data")
            else:
                response.read()
            if response.status != 200 or content_type != expected_content_type:
                raise RuntimeError(
                    f"Smoke test failed for {path}: "
                    f"status={response.status}, content-type={content_type}"
                )


def main(*, smoke_test: bool = False) -> None:
    """Start the bundled API and show its Vue frontend in a native window."""
    settings = get_settings()
    application = create_app(serve_frontend=True)
    listener, port = reserve_local_port()
    config = uvicorn.Config(
        application,
        host=HOST,
        port=port,
        # A windowed PyInstaller process has no sys.stdout/sys.stderr. Disable
        # Uvicorn's stream handlers; use a --console build while diagnosing.
        log_config=None,
        log_level=None,
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = UvicornThread(server, listener)
    thread.start()

    try:
        wait_until_started(server, thread)
        base_url = f"http://{HOST}:{port}"
        import webview

        if smoke_test:
            verify_local_server(base_url)
            return

        webview.create_window(
            settings.app_name,
            base_url,
            width=1200,
            height=800,
            min_size=(900, 600),
            resizable=True,
        )
        # PyWebView requires its GUI event loop to run on the main thread.
        webview.start()
    finally:
        stop_server(server, thread, listener)


def show_startup_error(error: Exception) -> None:
    """Make startup failures visible even in a windowed PyInstaller build."""
    message = f"应用启动失败：\n\n{error}"
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "启动失败", 0x10)
    else:  # pragma: no cover - this launcher primarily targets Windows
        print(message, file=sys.stderr)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch the FastAPI + Vue desktop application.")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Verify bundled HTTP routes and exit without opening a window.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    try:
        main(smoke_test=arguments.smoke_test)
    except Exception as startup_error:  # pragma: no cover - top-level GUI guard
        if arguments.smoke_test:
            if sys.stderr is not None:
                print(f"Smoke test failed: {startup_error}", file=sys.stderr)
        else:
            show_startup_error(startup_error)
        raise SystemExit(1) from startup_error
