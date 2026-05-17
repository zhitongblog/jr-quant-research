@echo off
REM jr-dashboard dev-mode launcher. Double-click to start.
REM Starts FastAPI on :8765 + Vite on :1420, opens browser.
REM Close this window to stop both servers.
cd /d "%~dp0"
"%~dp0..\.venv\Scripts\python.exe" "%~dp0start_dev.py"
pause
