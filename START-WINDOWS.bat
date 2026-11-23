@echo off
REM Executive Hub launcher for Windows. Double-click to start.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-windows.ps1"
pause
