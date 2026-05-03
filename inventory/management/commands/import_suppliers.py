r"""
Import suppliers from a CSV file. Idempotent — uses `name` as upsert key.

Required columns: name
Optional columns: contact_name, email, phone, website,
                  typical_lead_time_days, notes, is_active

Usage:
    python manage.py import_suppliers path\to\suppliers.csv [--dry-run]
"""

from inventory.models import Supplier

from ._csv_base import CsvImportCommand


class Command(CsvImportCommand):
    help = "Import suppliers from a CSV file."
    required_columns = ("name",)
    optional_columns = (
        "contact_name", "email", "phone", "website",
        "typical_lead_time_days", "notes", "is_active",
    )

    def process_row(self, row, row_no):
        name = row.get("name", "").strip()
        if not name:
            raise ValueError("name is required")

        defaults = {
            "contact_name": row.get("contact_name", ""),
            "email": row.get("email", ""),
            "phone": row.get("phone", ""),
            "website": row.get("website", ""),
            "notes": row.get("notes", ""),
            "is_active": self.to_bool(row.get("is_active", ""), "is_active", default=True),
        }
        lt = row.get("typical_lead_time_days", "")
        if lt:
            defaults["typical_lead_time_days"] = self.to_int(lt, "typical_lead_time_days")

        obj, created = Supplier.objects.update_or_create(name=name, defaults=defaults)
        return "created" if created else "updated"
