"""运行日志与安全事件日志的落盘配置。

打包后的窗口程序没有控制台，未配置处理器时所有告警都会丢失。这里统一配置：

- ``app.log``：全部 INFO 及以上日志（含 uvicorn），按天轮转保留 30 天，用于排障；
- ``events.log``：仅 ``app.events`` 记录的连接、急停、自动停机、链路故障、循环测试与
  安全配置变更等关键事件，按天轮转保留 365 天，用于产线追溯。
"""

import logging
import sys
import threading
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from types import TracebackType

EVENT_LOGGER_NAME = "app.events"
APP_LOG_BACKUP_DAYS = 30
EVENT_LOG_BACKUP_DAYS = 365

_CONFIGURED_ATTR = "_axle_logging_configured"
_LOG_FORMAT = "%(asctime)s.%(msecs)03d %(levelname)-7s [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _file_handler(path: Path, backup_days: int) -> TimedRotatingFileHandler:
    handler = TimedRotatingFileHandler(
        path,
        when="midnight",
        backupCount=backup_days,
        encoding="utf-8",
        delay=True,
    )
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))
    return handler


def _install_excepthooks() -> None:
    """未捕获异常同样写入日志，避免窗口程序静默崩溃。"""
    logger = logging.getLogger("app.crash")
    previous_hook = sys.excepthook

    def log_exception(
        exc_type: type[BaseException],
        exc: BaseException,
        tb: TracebackType | None,
    ) -> None:
        if not issubclass(exc_type, KeyboardInterrupt):
            logger.critical("未捕获异常", exc_info=(exc_type, exc, tb))
        previous_hook(exc_type, exc, tb)

    def log_thread_exception(args: threading.ExceptHookArgs) -> None:
        if args.exc_value is not None:
            logger.critical(
                "线程 %s 未捕获异常",
                args.thread.name if args.thread else "?",
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )

    sys.excepthook = log_exception
    threading.excepthook = log_thread_exception


def configure_logging(log_dir: Path) -> None:
    """配置文件日志（幂等：同一进程内重复调用不会重复添加处理器）。"""
    root = logging.getLogger()
    if getattr(root, _CONFIGURED_ATTR, False):
        return

    log_dir.mkdir(parents=True, exist_ok=True)
    root.setLevel(logging.INFO)
    root.addHandler(_file_handler(log_dir / "app.log", APP_LOG_BACKUP_DAYS))

    # 开发模式下保留控制台输出；窗口程序的 stderr 为 None。
    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))
        root.addHandler(console)

    events = logging.getLogger(EVENT_LOGGER_NAME)
    events.setLevel(logging.INFO)
    events.addHandler(_file_handler(log_dir / "events.log", EVENT_LOG_BACKUP_DAYS))

    _install_excepthooks()
    setattr(root, _CONFIGURED_ATTR, True)
    logging.getLogger("app").info("日志目录: %s", log_dir)
