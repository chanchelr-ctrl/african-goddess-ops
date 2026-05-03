r"""
Export every table to CSV inside a dated folder under `exports\`.
Useful for: accountant handover, periodic backup, data inspection.

Usage:
    python manage.py export_all
"""

import csv
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand

from inventory.models import (
    BomLine,
    ProductionRun,
    Product,
    PurchaseOrder,
    PurchaseOrderLine,
    RawMaterial,
    StockMovement,
    Supplier,
)


class Command(BaseCommand):
    help = r"Export every table to CSV files inside exports\YYYY-MM-DD_HHMM\."

    def handle(self, *args, **options):
        from django.conf import settings
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        out_dir = Path(settings.BASE_DIR) / "exports" / stamp
        out_dir.mkdir(parents=True, exist_ok=True)

        exporters = [
            ("suppliers", Supplier, [
                "name", "contact_name", "email", "phone", "website",
                "typical_lead_time_days", "notes", "is_active",
            ]),
            ("materials", RawMaterial, [
                "sku", "name", "unit", "current_stock", "reorder_point",
                "reorder_quantity", "last_paid_unit_cost",
                "preferred_supplier_name", "notes", "is_active",
            ]),
            ("products", Product, [
                "sku", "name", "pillar", "retail_price_zar",
                "material_cost", "gross_margin_zar", "gross_margin_pct",
                "can_make_units", "notes", "is_active",
            ]),
            ("boms", BomLine, ["product_sku", "material_sku", "quantity", "notes"]),
            ("purchase_orders", PurchaseOrder, [
                "reference", "supplier_name", "status",
                "expected_date", "received_date", "total_cost", "notes",
            ]),
            ("purchase_order_lines", PurchaseOrderLine, [
                "po_reference", "material_sku", "quantity", "unit_cost", "line_total",
            ]),
            ("production_runs", ProductionRun, [
                "run_date", "product_sku", "quantity", "notes", "created_at",
            ]),
            ("stock_movements", StockMovement, [
                "created_at", "material_sku", "delta", "reason",
                "related_object_type", "related_object_id", "note",
            ]),
        ]

        for fname, model, headers in exporters:
            path = out_dir / f"{fname}.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=headers)
                w.writeheader()
                count = 0
                for obj in model.objects.all():
                    w.writerow(self._serialise(obj, headers))
                    count += 1
            self.stdout.write(f"  {fname}: {count} rows -> {path.name}")

        self.stdout.write(self.style.SUCCESS(f"\nExport complete: {out_dir}"))

    @staticmethod
    def _serialise(obj, headers):
        out = {}
        for h in headers:
            if h == "preferred_supplier_name":
                out[h] = obj.preferred_supplier.name if obj.preferred_supplier else ""
            elif h == "supplier_name":
                out[h] = obj.supplier.name
            elif h == "po_reference":
                out[h] = obj.purchase_order.reference
            elif h == "product_sku":
                out[h] = obj.product.sku
            elif h == "material_sku":
                out[h] = obj.raw_material.sku
            else:
                val = getattr(obj, h, "")
                out[h] = "" if val is None else val
        return out
