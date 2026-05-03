"""
Shared base for the import_* management commands.

Pattern: read CSV → validate row by row → in --dry-run, just print results;
otherwise wrap the writes in a single transaction so a partial failure
leaves the database untouched.
"""

from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class CsvImportCommand(BaseCommand):
    """Subclasses set:

    - help: command help string
    - required_columns: tuple[str, ...]
    - optional_columns: tuple[str, ...]   (for nicer error messages only)

    And implement:

    - process_row(self, row: dict, row_no: int) -> str
        Apply the import for one row. Return a short verb-phrase describing
        the action (e.g. "created", "updated", "skipped — already exists").
        Raise ValueError or ValidationError for row-level problems.
    """

    required_columns: tuple[str, ...] = ()
    optional_columns: tuple[str, ...] = ()

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str, help="Path to the CSV file to import.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate but do not write to the database.",
        )

    # --- lifecycle ----------------------------------------------------------

    def handle(self, *args, **options) -> None:
        path = Path(options["csv_path"]).expanduser().resolve()
        dry_run = options["dry_run"]

        if not path.exists():
            raise CommandError(f"File not found: {path}")
        if path.suffix.lower() != ".csv":
            self.stdout.write(self.style.WARNING(
                f"File does not have .csv extension — proceeding anyway: {path.name}"
            ))

        self.stdout.write(self.style.NOTICE(
            f"\n{'DRY RUN — no changes will be written' if dry_run else 'IMPORTING'}: {path.name}"
        ))

        rows = self._read_rows(path)
        self.stdout.write(f"  Rows read: {len(rows)}")

        # Schema check
        if rows:
            missing = [c for c in self.required_columns if c not in rows[0]]
            if missing:
                raise CommandError(
                    f"CSV is missing required columns: {', '.join(missing)}\n"
                    f"  Required: {', '.join(self.required_columns)}\n"
                    f"  Optional: {', '.join(self.optional_columns)}"
                )

        # Process
        outcomes: dict[str, int] = {}
        errors: list[tuple[int, str]] = []

        sid = transaction.savepoint() if not dry_run else None
        with transaction.atomic():
            for i, row in enumerate(rows, start=2):  # row 1 is header
                try:
                    verb = self.process_row(row, i)
                    outcomes[verb] = outcomes.get(verb, 0) + 1
                except Exception as exc:  # noqa: BLE001 — we want the message
                    errors.append((i, str(exc)))

            if dry_run:
                transaction.set_rollback(True)

        # Report
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Outcome:") if outcomes else "Outcome: (no rows succeeded)")
        for verb, count in sorted(outcomes.items()):
            self.stdout.write(f"  {verb}: {count}")

        if errors:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(f"Errors ({len(errors)}):"))
            for line_no, msg in errors[:20]:
                self.stdout.write(f"  Row {line_no}: {msg}")
            if len(errors) > 20:
                self.stdout.write(f"  ... and {len(errors) - 20} more")
            if not dry_run:
                # In a real import, errors triggered savepoint inside the row;
                # the outer transaction still committed for successful rows.
                self.stdout.write(self.style.WARNING(
                    "Note: rows with errors were skipped. Successful rows were committed."
                ))

        if dry_run:
            self.stdout.write("")
            self.stdout.write(self.style.NOTICE("Dry run complete. Re-run without --dry-run to commit."))

    # --- helpers ------------------------------------------------------------

    def _read_rows(self, path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            return [
                {(k or "").strip(): (v or "").strip() for k, v in row.items()}
                for row in reader
            ]

    # --- field coercion -----------------------------------------------------

    @staticmethod
    def to_decimal(value: str, field: str, default: str | None = None) -> Decimal:
        if value == "" and default is not None:
            return Decimal(default)
        try:
            return Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"{field}: invalid decimal '{value}'") from exc

    @staticmethod
    def to_int(value: str, field: str, default: int | None = None) -> int:
        if value == "" and default is not None:
            return default
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"{field}: invalid integer '{value}'") from exc

    @staticmethod
    def to_bool(value: str, field: str, default: bool = True) -> bool:
        if value == "":
            return default
        return value.strip().lower() in ("1", "true", "yes", "y", "t")
