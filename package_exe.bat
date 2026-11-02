@echo off
chcp 65001 > nul

echo =======================================================
echo          株齿电驱桥上位机系统 - Windows 打包程序
echo =======================================================
echo.

cd /d "%~dp0backend" || (
    echo [错误] 找不到 backend 目录！
    pause
    exit /b 1
)

echo [1/2] 正在同步打包环境依赖 (uv sync --group desktop)...
call uv sync --group desktop
if errorlevel 1 (
    echo [错误] uv sync 失败，请检查网络或 uv 配置！
    pause
    exit /b 1
)

echo.
echo [2/2] 正在构建前端并打包...
call uv run --group desktop python build.py --smoke-test
if errorlevel 1 (
    echo.
    echo [错误] 打包失败，请查看上方错误信息！
    pause
    exit /b 1
)

echo.
echo 打包完成！把下面整个文件夹拷到工控机，运行其中的 Electric-Drive-Axle.exe：
echo   %~dp0backend\dist\Electric-Drive-Axle
echo.
pause
