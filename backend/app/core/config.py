"""Environment-backed application settings without an extra dependency."""

from dataclasses import dataclass
from functools import lru_cache
from os import getenv


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    """Read a comma-separated environment variable and discard empty values."""
    return tuple(item.strip() for item in getenv(name, default).split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    app_version: str
    api_prefix: str
    cors_origins: tuple[str, ...]


@lru_cache
def get_settings() -> Settings:
    """Create settings once per process."""
    return Settings(
        app_name=getenv("APP_NAME", "株齿 2.5T 电驱桥下线测试上位机"),
        app_version=getenv("APP_VERSION", "0.1.0"),
        api_prefix=getenv("API_PREFIX", "/api/v1"),
        cors_origins=_csv_env(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ),
    )
