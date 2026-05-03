@echo off
REM African Goddess - manual backup
REM Double-click this to copy db.sqlite3 to backups\db_YYYY-MM-DD_HHMM.sqlite3

cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\backup.ps1"
echo.
pause
