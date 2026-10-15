@echo off
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 goto nopython
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if not exist ".venv\Scripts\python.exe" goto novenv
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto pipfail
".venv\Scripts\python.exe" -m pianzhuang.bootstrap
if errorlevel 1 goto ffmpegfail
start "" ".venv\Scripts\pythonw.exe" "%~dp0main.py"
exit /b 0

:nopython
echo Python was not found. Install Python 3.11 or newer and check "Add python.exe to PATH".
pause
exit /b 1

:novenv
echo Could not create the virtual environment.
pause
exit /b 1

:pipfail
echo pip install failed.
pause
exit /b 1

:ffmpegfail
echo FFmpeg setup failed. Check the network and run this file again.
pause
exit /b 1
