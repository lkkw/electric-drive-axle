@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo =======================================================
echo          株齿电驱桥上位机系统 - Windows 打包程序
echo =======================================================
echo.

set "ROOT_DIR=%~dp0"
set "BACKEND_DIR=%ROOT_DIR%backend"

cd /d "%BACKEND_DIR%" || (
    echo [错误] 找不到 backend 目录！
    pause
    exit /b 1
)

echo [1/3] 正在同步桌面打包环境依赖 (uv sync --group desktop)...
call uv sync --group desktop
if errorlevel 1 (
    echo [错误] uv sync 失败，请检查网络或 uv 配置！
    pause
    exit /b 1
)

echo.
echo 请选择打包模式：
echo   [1] 单文件模式 (Onefile) - 推荐交付，单个独立可执行文件 (默认)
echo   [2] 目录模式 (Onedir)   - 启动更快，带控制台日志，适合现场调试
echo.
set /p MODE_CHOICE="请输入选项 [1 或 2，直接回车默认 1]: "

if "%MODE_CHOICE%"=="2" (
    echo.
    echo [2/3] 开始构建前端并打包为目录模式 (带控制台日志)...
    call uv run --group desktop python build.py --mode onedir --console --smoke-test
    set "OUT_PATH=%BACKEND_DIR%\release\Electric-Drive-Axle\Electric-Drive-Axle.exe"
) else (
    echo.
    echo [2/3] 开始构建前端并打包为独立单文件 EXE...
    call uv run --group desktop python build.py --mode onefile --smoke-test
    set "OUT_PATH=%BACKEND_DIR%\release\Electric-Drive-Axle.exe"
)

if errorlevel 1 (
    echo.
    echo [错误] 打包失败，请查看上方错误信息！
    pause
    exit /b 1
)

echo.
echo [3/3] 打包完成！
echo 可执行文件路径:
echo   !OUT_PATH!
echo.
pause
