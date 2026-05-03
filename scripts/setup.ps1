# African Goddess — One-time setup script
# Run from PowerShell in the project root: .\scripts\setup.ps1
#
# Prereq: Python 3.11+ installed and on PATH.
#         Download from https://www.python.org/downloads/
#         Tick "Add Python to PATH" during install.

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " African Goddess — One-time setup" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Move to project root (parent of scripts\)
Set-Location -Path "$PSScriptRoot\.."

# 1. Verify Python
Write-Host "[1/6] Checking Python..." -ForegroundColor Yellow
try {
    $pyver = & python --version 2>&1
    Write-Host "   Found: $pyver"
} catch {
    Write-Host "ERROR: Python is not installed or not on PATH." -ForegroundColor Red
    Write-Host "Install from https://www.python.org/downloads/ (tick 'Add Python to PATH')" -ForegroundColor Red
    exit 1
}

# 2. Create venv
Write-Host "[2/6] Creating virtual environment in .venv\ ..." -ForegroundColor Yellow
if (Test-Path .\.venv) {
    Write-Host "   .venv already exists — skipping creation."
} else {
    & python -m venv .venv
    Write-Host "   Created."
}

# 3. Activate venv + upgrade pip
Write-Host "[3/6] Installing dependencies (this may take a minute)..." -ForegroundColor Yellow
& .\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
Write-Host "   Dependencies installed."

# 4. Generate SECRET_KEY and persist to .env if not already set
Write-Host "[4/6] Generating Django secret key..." -ForegroundColor Yellow
if (-not (Test-Path .\.env)) {
    $secret = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(50))"
    "DJANGO_SECRET_KEY=$secret" | Out-File -Encoding utf8 .\.env
    "DJANGO_DEBUG=False"        | Add-Content -Encoding utf8 .\.env
    Write-Host "   Generated and saved to .env"
} else {
    Write-Host "   .env already exists — keeping existing secret."
}

# Load env into current process for the migration step
Get-Content .\.env | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}

# 5. Run migrations
Write-Host "[5/6] Setting up the database..." -ForegroundColor Yellow
& .\.venv\Scripts\python.exe manage.py migrate --no-input
Write-Host "   Database ready: db.sqlite3"

# 6. Create superuser interactively
Write-Host ""
Write-Host "[6/6] Time to create the admin user." -ForegroundColor Yellow
Write-Host "      Choose a username (suggest: tersia)." -ForegroundColor Yellow
Write-Host "      Email is optional." -ForegroundColor Yellow
Write-Host "      Pick a strong password and write it down somewhere safe." -ForegroundColor Yellow
Write-Host ""
& .\.venv\Scripts\python.exe manage.py createsuperuser

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host " Setup complete." -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "To start the app, run:" -ForegroundColor White
Write-Host "    .\scripts\start.ps1" -ForegroundColor Cyan
Write-Host ""
Write-Host "Then open in your browser:" -ForegroundColor White
Write-Host "    http://127.0.0.1:8000/" -ForegroundColor Cyan
Write-Host ""
