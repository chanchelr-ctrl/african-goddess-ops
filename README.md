# African Goddess — Inventory & Operations App

> Internal-ops web app for African Goddess. Tracks raw materials, products, bills of materials, suppliers, purchase orders, and production runs. Self-hosted on Tersia's Windows desktop. Single-user. SQLite. No cloud dependencies.

## Quick start (one-time install)

**Prerequisite:** Install Python 3.11+ from https://www.python.org/downloads/. During install, **check "Add Python to PATH"**.

Open PowerShell in this folder and run:

```powershell
.\scripts\setup.ps1
```

The script will:
1. Create a Python virtual environment in `.venv\`
2. Install all dependencies
3. Create the SQLite database and run migrations
4. Prompt you to create a Tersia admin user (pick a strong password — write it down)
5. Print the URL to open

## Daily use

Double-click `scripts\start.ps1` (or run from PowerShell). The launcher opens a window — leave it open while you work — and your default browser at:

```
http://127.0.0.1:8000/
```

When you're done for the day, close the launcher window. Your work is saved in `db.sqlite3`.

## What's where

| Path | Purpose |
|---|---|
| `db.sqlite3` | All your data. **This is the file to back up.** |
| `backups/` | Dated copies of `db.sqlite3` (created by `backup.ps1`) |
| `config/` | Django project config (settings, urls) |
| `inventory/` | The application code (models, admin, dashboard) |
| `scripts/setup.ps1` | One-time install |
| `scripts/start.ps1` | Daily launcher |
| `scripts/backup.ps1` | Copy `db.sqlite3` to a dated backup |
| `docs/` | User guide, runbook, architecture |
| `fixtures/` | Sample data for testing |
| `requirements.txt` | Python dependencies |

## Backups

**Manual:** double-click `scripts\backup.ps1`.

**Automatic:** Task Scheduler is configured during setup to run `backup.ps1` daily. Backups go to `backups\db_YYYY-MM-DD_HHMM.sqlite3`. Recommended: copy this folder into a OneDrive-mirrored location for offsite redundancy.

## Restore from backup

Stop the launcher (close the PowerShell window). Replace `db.sqlite3` with the chosen backup file (renamed). Restart `start.ps1`.

## Versions

- Python 3.11+
- Django 5.x
- SQLite (bundled with Python)

## Support

Consultant: Chanchel Ramjathan. See `docs/RUNBOOK.md` for emergency-maintenance instructions and escrow plan.

## License

Single-tenant proprietary build for African Goddess. Not for redistribution.
