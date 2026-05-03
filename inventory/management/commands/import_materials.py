r"""
Import raw materials from a CSV file. Idempotent — uses `sku` as upsert key.

Required columns: sku, name
Optional columns: unit, current_stock, reorder_point, reorder_quantity,
                  last_paid_unit_cost, preferred_supplier_name, notes, is_active

When current_stock is set on an INSERTED row, a corresponding StockMovement
of reason=INITIAL_STOCK is recorded so the audit trail invariant holds.

Usage:
    python manage.py import_materials path\to\materials.csv [--dry-run]
"""

from decimal import Decimal

from inventory.models import RawMaterial, StockMovement, Supplier

from ._csv_base import CsvImportCommand


class Command(CsvImportCommand):
    help = "Import raw materials from a CSV file."
    required_columns = ("sku", "name")
    optional_columns = (
        "unit", "current_stock", "reorder_point", "reorder_quantity",
        "last_paid_unit_cost", "preferred_supplier_name", "notes", "is_active",
    )

    def process_row(self, row, row_no):
        sku = row.get("sku", "").strip()
        name = row.get("name", "").strip()
        if not sku:
            raise ValueError("sku is required")
        if not name:
            raise ValueError("name is required")

        # Resolve preferred_supplier by name (optional)
        supplier = None
        sname = row.get("preferred_supplier_name", "").strip()
        if sname:
            try:
                supplier = Supplier.objects.get(name=sname)
            except Supplier.DoesNotExist as exc:
                raise ValueError(f"preferred_supplier_name '{sname}' not found") from exc

        unit = row.get("unit", "").strip() or "piece"
        valid_units = {choice[0] for choice in RawMaterial.UNIT_CHOICES}
        if unit not in valid_units:
            raise ValueError(
                f"unit '{unit}' not valid. Allowed: {', '.join(sorted(valid_units))}"
            )

        current_stock = self.to_decimal(row.get("current_stock", ""), "current_stock", default="0")
        reorder_point = self.to_decimal(row.get("reorder_point", ""), "reorder_point", default="0")
        reorder_quantity = self.to_decimal(row.get("reorder_quantity", ""), "reorder_quantity", default="0")
        last_paid_unit_cost = self.to_decimal(
            row.get("last_paid_unit_cost", ""), "last_paid_unit_cost", default="0"
        )

        defaults = {
            "name": name,
            "unit": unit,
            "reorder_point": reorder_point,
            "reorder_quantity": reorder_quantity,
            "last_paid_unit_cost": last_paid_unit_cost,
            "preferred_supplier": supplier,
            "notes": row.get("notes", ""),
            "is_active": self.to_bool(row.get("is_active", ""), "is_active", default=True),
        }

        obj, created = RawMaterial.objects.update_or_create(sku=sku, defaults=defaults)

        if created:
            # Set initial stock and emit an audit movement
            if current_stock != Decimal("0"):
                obj.current_stock = current_stock
                obj.save(update_fields=["current_stock", "updated_at"])
                StockMovement.objects.create(
                    raw_material=obj,
                    delta=current_stock,
                    reason="INITIAL_STOCK",
                    note="Set during CSV import",
                )
            return "created"
        else:
            # On update we do NOT silently overwrite current_stock — that would
            # bypass the audit trail. Instead, if the CSV value differs, emit
            # an ADJUSTMENT movement.
            if current_stock != obj.current_stock:
                delta = current_stock - obj.current_stock
                obj.current_stock = current_stock
                obj.save(update_fields=["current_stock", "updated_at"])
                StockMovement.objects.create(
                    raw_material=obj,
                    delta=delta,
                    reason="ADJUSTMENT",
                    note=f"Adjustment via CSV import (row {row_no})",
                )
                return "updated (with stock adjustment)"
            return "updated"
