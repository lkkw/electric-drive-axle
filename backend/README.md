# 后端

FastAPI + 周立功 USBCAN 驱动，使用 [uv](https://docs.astral.sh/uv/) 管理依赖。

```powershell
uv sync
uv run main.py        # 开发模式，http://127.0.0.1:8000/docs
uv run pytest         # 测试
uv run ruff check .   # 代码检查
```

桌面程序入口为 `desktop.py`，打包脚本为 `build.py`；`static/`、`build/`、`release/` 为打包生成目录。

完整说明见根目录 [README.md](../README.md) 与 [docs/技术文档.md](../docs/技术文档.md)。
