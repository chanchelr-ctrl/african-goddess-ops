@echo off
REM African Goddess - daily launcher
REM Double-click this to start the app. The launcher window opens; close it when done for the day.

cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start.ps1"
