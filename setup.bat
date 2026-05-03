@echo off
REM African Goddess - one-time setup
REM Double-click this to install. Wraps scripts\setup.ps1 with execution-policy bypass
REM so it works on a stock Windows machine without changing system settings.

cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\setup.ps1"
echo.
pause
