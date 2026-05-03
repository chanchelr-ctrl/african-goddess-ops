# African Goddess — SQLite backup
# Copies db.sqlite3 to backups\db_YYYY-MM-DD_HHMM.sqlite3
# Schedule daily via Windows Task Scheduler.

$ErrorActionPreference = "Stop"

Set-Location -Path "$PSScriptRoot\.."

if (-not (Test-Path .\db.sqlite3)) {
    Write-Host "ERROR: db.sqlite3 not found. Has setup been run yet?" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path .\backups)) {
    New-Item -ItemType Directory -Path .\backups | Out-Null
}

$timestamp = Get-Date -Format "yyyy-MM-dd_HHmm"
$dest = ".\backups\db_$timestamp.sqlite3"

Copy-Item -Path .\db.sqlite3 -Destination $dest -Force

Write-Host "Backup saved: $dest" -ForegroundColor Green

# Retention: keep last 30 backups, delete older
Get-ChildItem -Path .\backups\db_*.sqlite3 |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 30 |
    Remove-Item -Force
