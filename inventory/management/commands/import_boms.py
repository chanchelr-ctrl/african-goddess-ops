r"""
Import BOM lines (product → raw material recipes) from a CSV file.
Idempotent on (product_sku, material_sku) — re-running updates the quantity.

Required columns: product_sku, material_sku, quantity
Optional columns: notes

Usage:
    python manage.py import_boms path\to\boms.csv [--dry-run]
"""

from inventory.models import BomLine, Product, RawMaterial

from ._csv_base import CsvImportCommand


class Command(CsvImportCommand):
    help = "Import BOM lines from a CSV file."
    required_columns = ("product_sku", "material_sku", "quantity")
    optional_columns = ("notes",)

    def process_row(self, row, row_no):
        product_sku = row.get("product_sku", "").strip()
        material_sku = row.get("material_sku", "").strip()
        if not product_sku:
            raise ValueError("product_sku is required")
        if not material_sku:
            raise ValueError("material_sku is required")

        try:
            product = Product.objects.get(sku=product_sku)
        except Product.DoesNotExist as exc:
            raise ValueError(f"product_sku '{product_sku}' not found") from exc

        try:
            material = RawMaterial.objects.get(sku=material_sku)
        except RawMaterial.DoesNotExist as exc:
            raise ValueError(f"material_sku '{material_sku}' not found") from exc

        qty = self.to_decimal(row.get("quantity", ""), "quantity")
        if qty <= 0:
            raise ValueError(f"quantity must be > 0 (got {qty})")

        defaults = {"quantity": qty, "notes": row.get("notes", "")}
        obj, created = BomLine.objects.update_or_create(
            product=product, raw_material=material, defaults=defaults,
        )
        return "created" if created else "updated"
