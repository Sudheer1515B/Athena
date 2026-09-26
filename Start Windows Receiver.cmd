@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Missing Python environment. See pwm_receiver\WINDOWS_MONITOR.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -u scripts\monitor_receiver.py --serve %*
pause
