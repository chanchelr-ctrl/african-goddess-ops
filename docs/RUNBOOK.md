# Runbook — African Goddess Operations

> Written for the consultant or any future maintainer. Operations procedures, common-issue diagnostics, and the bus-factor / handover plan. The user-facing version is in [USER_GUIDE.md](USER_GUIDE.md).

## What this app is

- Internal operations app for African Goddess (single-tenant, single-user).
- Self-hosted on Tersia's Windows desktop.
- Tracks raw materials, products, BOMs, suppliers, purchase orders, production runs.
- **Out of scope: WooCommerce sync, customer-facing components.**

## Stack at a glance

- Python 3.11+ (development verified on 3.12.10)
- Django 5.1.x
- SQLite (file-based, single-file: `db.sqlite3`)
- Waitress WSGI server, listening on `127.0.0.1:8000` (loopback only)
- Pico.css + HTMX 2 for the dashboard; Django Admin for CRUD
- pytest + pytest-django for tests

## Filesystem layout

```
african-goddess-ops/
├── .venv/                  ← Python virtualenv (not committed)
├── .env                    ← SECRET_KEY etc (NOT committed)
├── db.sqlite3              ← Production database
├── backups/                ← Dated SQLite copies (auto-pruned to 30)
├── exports/                ← CSV dumps from `export_all`
├── fixtures/sample_african_goddess.json
├── config/                 ← Django project (settings, urls, wsgi)
├── inventory/              ← The app (models, admin, views, management commands, tests)
├── scripts/                ← setup.ps1, start.ps1, backup.ps1
└── docs/                   ← This runbook + USER_GUIDE.md + ARCHITECTURE.md
```

## Daily operations

| Task | Command |
|---|---|
| Start the app | `.\start.bat` (double-click) or `.\scripts\start.ps1` (PowerShell) |
| Stop the app | Close the launcher window (or `Ctrl-C` in it) |
| Manual backup | `.\backup.bat` (double-click) or `.\scripts\backup.ps1` (PowerShell) |
| Check Django config | `.\.venv\Scripts\python.exe manage.py check` |
| Run all tests | `.\.venv\Scripts\python.exe -m pytest` |
| Open Django shell | `.\.venv\Scripts\python.exe manage.py shell` |
| Reconcile stock invariant | `.\.venv\Scripts\python.exe manage.py reconcile_stock` |
| Recompute stock from audit log | `.\.venv\Scripts\python.exe manage.py reconcile_stock --fix` |
| Export everything to CSV | `.\.venv\Scripts\python.exe manage.py export_all` |

## Bulk import procedure (data migration day)

1. Take a manual backup first: `.\scripts\backup.ps1`.
2. Validate each CSV with `--dry-run` first. Order matters: **suppliers → materials → products → BOMs.**
3. Read every dry-run report carefully. Fix CSV issues. Re-run.
4. When green: re-run each command without `--dry-run` to commit.
5. Confirm the dashboard loads and material counts look right.
6. Run `reconcile_stock` to confirm the audit invariant holds.

CSV schemas — see [USER_GUIDE.md → Bulk import](USER_GUIDE.md#bulk-import-from-spreadsheet).

## Restore from backup

```powershell
# 1. Stop the app — close the launcher window
# 2. Move current db aside (in case the chosen backup is wrong)
Move-Item .\db.sqlite3 .\db.sqlite3.before-restore
# 3. Copy chosen backup into place
Copy-Item .\backups\db_2026-05-03_1800.sqlite3 .\db.sqlite3
# 4. Verify integrity
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe -m pytest
# 5. Restart
.\scripts\start.ps1
```

## Schema migrations (when models.py changes)

```powershell
.\.venv\Scripts\python.exe manage.py makemigrations inventory
.\.venv\Scripts\python.exe -m pytest                       # confirm nothing broke
.\.venv\Scripts\python.exe manage.py migrate
```

Always commit the migration files (`inventory/migrations/0002_*.py` etc.) into git.

## Tasks Scheduler — daily backup

The setup script does NOT install a scheduled task automatically. To wire one up:

1. Open Task Scheduler.
2. Create Basic Task → "African Goddess Backup".
3. Trigger: Daily at 18:00 (or whenever Tersia is usually finished).
4. Action: Start a program → `powershell.exe`.
5. Add arguments: `-NoProfile -ExecutionPolicy Bypass -File "C:\Users\chanr\Desktop\african-goddess-ops\scripts\backup.ps1"`.
6. Tick "Run whether user is logged on or not" if you want it to run when the desktop is locked.

## Bus-factor mitigations (handover plan)

This was an explicit engagement requirement. As of `v0.1.0-mvp`:

1. **Source code in git.** Repo is at `african-goddess-ops/`. Initial commit tagged `v0.1.0-mvp`. Push to a private GitHub repo with the consultant *and* a fiduciary holder of credentials (recommend: client's email + a sealed envelope with the GitHub access token).
2. **Documentation alongside code.** `README.md` (entry-point), `docs/USER_GUIDE.md` (operator), `docs/RUNBOOK.md` (this doc), `docs/ARCHITECTURE.md` (engineering reference, copy of [knowledge-repo architecture doc](../../Inventory%20%26%20Sales%20Management/07_Custom_Build/architecture.md)).
3. **Automated tests for load-bearing logic.** All BOM-deduction, PO-receipt, reorder-threshold, audit-invariant, and importer logic is covered. Any future maintainer running `pytest` gets immediate feedback if a change breaks operational correctness.
4. **No external runtime dependencies.** SQLite, no Postgres server. Waitress, no nginx. Loopback-only, no public DNS. Anyone with Python 3.11+ on a Windows desktop can rebuild from scratch in 10 minutes.
5. **Backup procedure documented and automatic.** A maintainer arriving cold can restore from any of 30 days of backups in ~30 seconds.
6. **Reconciliation tool.** `reconcile_stock` lets a maintainer detect and fix drift between the denormalised `current_stock` and the audit-trail invariant. The audit log is the source of truth.

### Code-escrow recommendation

Until the consultant explicitly hands over to a salaried developer or the client is comfortable forking themselves:
- Repo lives on GitHub under the consultant's account, with the client added as a Collaborator.
- Credentials (GitHub repo URL, deploy SSH key if any, Tersia's admin password) are documented in a sealed file held by the client OR by an escrow service.
- A 1-page "if Chanchel becomes unavailable" runbook lives in the client's records: it should name the consultant's preferred handover developer, or instruct the client to engage any Django-fluent freelance developer.

## Common-issue diagnostics

### `start.ps1` "cannot be loaded because running scripts is disabled on this system"
Windows default execution policy is `Restricted`. Two fixes:
- **One-off:** `powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1`
- **Permanent (per-user):** `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`
- **Best for end-users:** double-click `start.bat` instead — it wraps the .ps1 with `-ExecutionPolicy Bypass` already.

### "ImportError: couldn't import Django"
Activate the venv: `.\.venv\Scripts\python.exe ...`. If the venv is missing, re-run `.\setup.bat`.

### "Port 8000 in use"
Another instance is already running, or another app is using the port. Kill it:
```powershell
$conn = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($conn) { Stop-Process -Id $conn.OwningProcess -Force }
```
Or change the port in `start.ps1` (search for `--listen=`).

### Dashboard shows wrong stock numbers
Run `reconcile_stock`. If it reports drift, run with `--fix` to recompute from the audit log. If drift recurs after a fix, there's a bug — investigate which code path is mutating `current_stock` outside `model.save()`.

### Production run was made by mistake
Production runs cannot be deleted. Add equal-and-opposite stock movements (one per BOM line) with reason=ADJUSTMENT and a note like "Reversing accidental Production Run #N".

### "OperationalError: database is locked"
SQLite single-writer constraint. Should be rare in practice (single user). If it persists: ensure only one Python process is open against the db. Restart the app.

### Tests fail after pulling new commits
Always run `manage.py migrate` after pulling — schema may have changed.

### Master data import failed / corrupted file
The `Import Data` button accepts a `.xlsx` matching the schema written by `Export Data`. Required sheets: `MaterialMaster`, `ProductSpec`. The `ChangeLog` sheet (if present) is ignored — it's an output-only audit trail.

```powershell
# Dry-run from the CLI to see what would change
.\.venv\Scripts\python.exe manage.py import_master "path\to\file.xlsx" --dry-run

# Real import (default: additive — does not delete missing rows)
.\.venv\Scripts\python.exe manage.py import_master "path\to\file.xlsx"

# Strict import: deactivate materials and delete BOM lines not in the file
.\.venv\Scripts\python.exe manage.py import_master "path\to\file.xlsx" --prune
```

The old `migrate_bom_xlsx` command (reads the original 3-file client spreadsheets) is preserved for bootstrap-from-scratch only. Day-to-day imports should use `import_master`.

### Audit log (`DataChangeLog`)
Every CREATE / UPDATE / DELETE on master/spec models (RawMaterial, Product, ProductVariant, Variant, Brand, BomLine, Supplier) writes a row. View at `/admin/inventory/datachangelog/` or as the `ChangeLog` sheet in any export.

User attribution comes from `inventory.middleware.CurrentUserMiddleware`, which stores `request.user` in a thread-local that signals read on save. Edits made from the shell or via management commands have `user=NULL`.

### Suspected db corruption
```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; c = sqlite3.connect('db.sqlite3'); print(c.execute('PRAGMA integrity_check').fetchall())"
```
If anything other than `[('ok',)]` is returned, restore from a known-good backup.

## Performance ceilings (you'll hit them at...)

SQLite handles this scale comfortably:
- ~10k raw materials, ~10k products, ~100k BOM lines: zero issue
- ~1M stock movements: still fine; consider archive-to-CSV after a year
- Read concurrency: many; write concurrency: 1 (the single user)

Migration to Postgres only becomes interesting when:
- Multiple users editing concurrently
- Hosted off-desktop
- Aggregate queries over millions of rows

## Security posture (intentional)

- Loopback only (`127.0.0.1`); not exposed to the network. To expose to the LAN, change `ALLOWED_HOSTS` and the Waitress `--listen` flag in `start.ps1`. **Don't expose to the public internet without adding HTTPS, rate limiting, and stronger auth — this app was not designed for that.**
- HTTPS-related security warnings are silenced in `settings.SILENCED_SYSTEM_CHECKS`. If exposing publicly, remove those silences and configure SSL.
- `SECRET_KEY` is generated on first install and lives in `.env` (gitignored).
- DEBUG=False by default.
- Single superuser model (Tersia). Add additional users via `manage.py createsuperuser` if needed.

## Version history

- `v0.1.0-mvp` (2026-05-04 target): initial MVP. Core data model, admin, dashboard, importers, exporter, reconciler, sample fixture, full test suite. Single-tenant, single-user, loopback-only, ZAR.
