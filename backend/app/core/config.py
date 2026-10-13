"""Environment-backed application settings without an extra dependency."""

from dataclasses import dataclass
from functools import lru_cache
from os import getenv
from pathlib import Path

from app import __version__


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    """Read a comma-separated environment variable and discard empty values."""
    return tuple(item.strip() for item in getenv(name, default).split(",") if item.strip())


def _default_data_dir() -> Path:
    """用户级数据目录：Windows 下位于 %APPDATA%，打包后的 EXE 无需写入安装目录。"""
    appdata = getenv("APPDATA")
    base = Path(appdata) if appdata else Path.home() / ".config"
    return base / "electric-drive-axle"


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    app_version: str
    api_prefix: str
    cors_origins: tuple[str, ...]
    data_dir: Path

    @property
    def safety_config_path(self) -> Path:
        """自动停机阈值持久化文件路径。"""
        return self.data_dir / "safety_config.json"

    @property
    def log_dir(self) -> Path:
        """运行日志与安全事件日志目录。"""
        return self.data_dir / "logs"


@lru_cache
def get_settings() -> Settings:
    """Create settings once per process."""
    data_dir_env = getenv("AXLE_DATA_DIR")
    return Settings(
        app_name=getenv("APP_NAME", "株齿 2.5T 电驱桥下线测试上位机"),
        app_version=__version__,
        api_prefix=getenv("API_PREFIX", "/api/v1"),
        cors_origins=_csv_env(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ),
        data_dir=Path(data_dir_env) if data_dir_env else _default_data_dir(),
    )
