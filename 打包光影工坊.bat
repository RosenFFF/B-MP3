@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo 未检测到虚拟环境，请先运行「安装并启动.bat」配置环境。
    pause
    exit /b 1
)
".venv\Scripts\python.exe" build_exe.py
pause
