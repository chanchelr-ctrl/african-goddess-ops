r"""
Import products from a CSV file. Idempotent — uses `sku` as upsert key.

Required columns: sku, name
Optional columns: pillar, retail_price_zar, notes, is_active

Usage:
    python manage.py import_products path\to\products.csv [--dry-run]
"""

from inventory.models import Product

from ._csv_base import CsvImportCommand


class Command(CsvImportCommand):
    help = "Import products from a CSV file."
    required_columns = ("sku", "name")
    optional_columns = ("pillar", "retail_price_zar", "notes", "is_active")

    def process_row(self, row, row_no):
        sku = row.get("sku", "").strip()
        name = row.get("name", "").strip()
        if not sku:
            raise ValueError("sku is required")
        if not name:
            raise ValueError("name is required")

        pillar = row.get("pillar", "").strip() or "BODY_ADORNMENTS"
        valid_pillars = {choice[0] for choice in Product.PILLAR_CHOICES}
        if pillar not in valid_pillars:
            raise ValueError(
                f"pillar '{pillar}' not valid. Allowed: {', '.join(sorted(valid_pillars))}"
            )

        defaults = {
            "name": name,
            "pillar": pillar,
            "retail_price_zar": self.to_decimal(
                row.get("retail_price_zar", ""), "retail_price_zar", default="0"
            ),
            "notes": row.get("notes", ""),
            "is_active": self.to_bool(row.get("is_active", ""), "is_active", default=True),
        }

        obj, created = Product.objects.update_or_create(sku=sku, defaults=defaults)
        return "created" if created else "updated"
