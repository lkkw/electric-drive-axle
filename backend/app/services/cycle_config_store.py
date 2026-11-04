"""自动控制工况配置的本地 JSON 持久化。

操作员编辑的步骤序列在进程重启后必须保持；读取失败时返回 None，
由前端回退到默认工况。
"""

import logging
import os
from pathlib import Path

from pydantic import ValidationError

from app.schemas.axle import CycleTestConfig

logger = logging.getLogger("app.cycle_config_store")


def load_cycle_config(path: Path | None) -> CycleTestConfig | None:
    """读取持久化配置；文件不存在、损坏或字段非法时返回 None。"""
    if path is None or not path.is_file():
        return None
    try:
        return CycleTestConfig.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ValidationError) as err:
        logger.warning("工况配置文件 %s 无法读取，已使用默认工况: %s", path, err)
        return None


def save_cycle_config(path: Path | None, config: CycleTestConfig) -> None:
    """原子写入配置：先写临时文件再替换，避免掉电时留下半截 JSON。"""
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp_path, path)
