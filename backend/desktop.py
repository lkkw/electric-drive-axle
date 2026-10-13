"""Windows desktop launcher for the bundled FastAPI + Vue application."""

from __future__ import annotations

import argparse
import ctypes
import logging
import socket
import sys
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from urllib.request import Request, urlopen

import uvicorn

from app.core.config import get_settings
from app.core.logging_setup import configure_logging
from app.main import create_app
from app.services.axle_manager import AxleManager, peek_axle_manager

HOST = "127.0.0.1"
STARTUP_TIMEOUT_SECONDS = 15.0
SHUTDOWN_TIMEOUT_SECONDS = 10.0

# 同一登录会话内只允许一个实例，避免两个窗口争用 USBCAN 或先后控制电驱桥。
SINGLE_INSTANCE_MUTEX_NAME = "Local\\ZhuChi-ElectricDriveAxle-EOL"
ERROR_ALREADY_EXISTS = 183

CLOSE_CONFIRM_MESSAGE = (
    "电驱桥仍在运行（MCU 已使能或循环测试未结束）。\n\n"
    "关闭程序将发送停机帧并断开 CAN 通信，确定要关闭吗？"
)

logger = logging.getLogger("app.desktop")


def acquire_single_instance(name: str = SINGLE_INSTANCE_MUTEX_NAME) -> int | None:
    """创建命名互斥量；已有实例持有时返回 None。

    返回的句柄需在进程生命周期内保持，进程退出时由系统自动释放。
    """
    if sys.platform != "win32":  # pragma: no cover - this launcher targets Windows
        return 0

    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        raise OSError(ctypes.get_last_error(), "创建单实例互斥量失败")
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return None
    return int(handle)


def release_single_instance(handle: int | None) -> None:
    """释放互斥量句柄（正常退出时进程也会自动释放，主要用于测试）。"""
    if handle and sys.platform == "win32":
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(handle))


def activate_existing_window(title: str) -> bool:
    """把已运行实例的窗口还原并切到前台。"""
    if sys.platform != "win32":  # pragma: no cover
        return False
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False
    sw_restore = 9
    user32.ShowWindow(hwnd, sw_restore)
    user32.SetForegroundWindow(hwnd)
    return True


def ask_close_confirmation(title: str) -> bool:
    """原生是/否对话框，默认焦点在“否”，防止误触关闭。"""
    if sys.platform != "win32":  # pragma: no cover
        return True
    mb_yesno, mb_iconwarning, mb_defbutton2 = 0x04, 0x30, 0x100
    mb_setforeground, mb_topmost, idyes = 0x10000, 0x40000, 6
    flags = mb_yesno | mb_iconwarning | mb_defbutton2 | mb_setforeground | mb_topmost
    return ctypes.windll.user32.MessageBoxW(None, CLOSE_CONFIRM_MESSAGE, title, flags) == idyes


def make_closing_handler(
    title: str,
    get_manager: Callable[[], AxleManager | None] = peek_axle_manager,
    confirm: Callable[[str], bool] = ask_close_confirmation,
) -> Callable[[], bool]:
    """生成 PyWebView ``closing`` 事件处理函数：返回 False 即取消关闭。"""

    def on_closing() -> bool:
        manager = get_manager()
        if manager is None or not manager.requires_close_confirmation:
            return True
        allowed = confirm(title)
        if not allowed:
            logger.info("操作员取消关闭程序（电驱桥仍在运行）")
        return allowed

    return on_closing


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
    configure_logging(settings.log_dir)

    # 冒烟测试在打包流水线中运行，不参与单实例判定。
    instance_handle = None
    if not smoke_test:
        instance_handle = acquire_single_instance()
        if instance_handle is None:
            logger.warning("程序已在运行，切换到已打开的窗口")
            if not activate_existing_window(settings.app_name):
                show_message("程序已在运行，请在任务栏中切换到已打开的窗口。", "提示")
            return

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

        window = webview.create_window(
            settings.app_name,
            base_url,
            width=1200,
            height=800,
            min_size=(900, 600),
            resizable=True,
        )
        # 电机运行中关闭窗口需二次确认；closing 事件在界面线程同步执行，返回 False 取消关闭。
        window.events.closing += make_closing_handler(settings.app_name)
        # PyWebView requires its GUI event loop to run on the main thread.
        webview.start()
    finally:
        stop_server(server, thread, listener)
        release_single_instance(instance_handle)


def show_message(message: str, title: str, *, error: bool = False) -> None:
    """窗口程序没有控制台，用原生消息框提示操作员。"""
    if sys.platform == "win32":
        mb_iconerror, mb_iconinformation = 0x10, 0x40
        icon = mb_iconerror if error else mb_iconinformation
        ctypes.windll.user32.MessageBoxW(None, message, title, icon)
    else:  # pragma: no cover - this launcher primarily targets Windows
        print(message, file=sys.stderr)


def show_startup_error(error: Exception) -> None:
    """Make startup failures visible even in a windowed PyInstaller build."""
    logger.critical("应用启动失败", exc_info=error)
    show_message(f"应用启动失败：\n\n{error}", "启动失败", error=True)


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
