# African Goddess — Daily launcher
# Double-click this file (or run from PowerShell) to start the app.
#
# The app will be available at http://127.0.0.1:8000/
# Close this window when you're done for the day.

$ErrorActionPreference = "Stop"

Set-Location -Path "$PSScriptRoot\.."

if (-not (Test-Path .\.venv)) {
    Write-Host "ERROR: .venv\ not found. Run .\scripts\setup.ps1 first." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

# Load env
if (Test-Path .\.env) {
    Get-Content .\.env | ForEach-Object {
        if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
    }
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " African Goddess — Operations" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Starting server at http://127.0.0.1:8000/" -ForegroundColor Green
Write-Host "Leave this window open while you work." -ForegroundColor Yellow
Write-Host "Close it when you're done for the day." -ForegroundColor Yellow
Write-Host ""

# Open the browser after a short delay (in the background)
Start-Job -ScriptBlock {
    Start-Sleep -Seconds 2
    Start-Process "http://127.0.0.1:8000/"
} | Out-Null

# Run with Waitress (production-grade WSGI for Windows)
& .\.venv\Scripts\python.exe -m waitress --listen=127.0.0.1:8000 config.wsgi:application
