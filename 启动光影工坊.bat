@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "%~dp0dist\光影工坊\光影工坊.exe" (
    start "" "%~dp0dist\光影工坊\光影工坊.exe" --import %*
    exit /b 0
)
set "PY=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%PY%" goto missing
start "" "%PY%" "%~dp0main.py" --import %*
exit /b 0

:missing
echo 未检测到编译好的程序或 Python 环境，请先双击运行「安装并启动.bat」。
pause
exit /b 1
