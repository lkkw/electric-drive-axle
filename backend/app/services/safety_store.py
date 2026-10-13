"""自动停机阈值的本地 JSON 持久化。

阈值属于台架现场标定结果，进程重启后必须保持；读取失败时回退到默认值，
保证安全监控始终以合法配置启动。
"""

import logging
import os
from pathlib import Path

from pydantic import ValidationError

from app.schemas.axle import AxleSafetyConfig

logger = logging.getLogger("app.safety_store")


def load_safety_config(path: Path | None) -> AxleSafetyConfig:
    """读取持久化配置；文件不存在、损坏或字段越界时使用默认配置。"""
    if path is None or not path.is_file():
        return AxleSafetyConfig()
    try:
        return AxleSafetyConfig.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ValidationError) as err:
        logger.warning("安全配置文件 %s 无法读取，已使用默认阈值: %s", path, err)
        return AxleSafetyConfig()


def save_safety_config(path: Path | None, config: AxleSafetyConfig) -> None:
    """原子写入配置：先写临时文件再替换，避免掉电时留下半截 JSON。"""
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp_path, path)
