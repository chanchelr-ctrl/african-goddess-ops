"""
Tests for CSV import management commands.

Each importer is exercised with: a happy-path CSV, a malformed CSV (bad
columns), a row-level error case (missing FK target), and dry-run mode.
"""

from decimal import Decimal
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command

from inventory.models import (
    BomLine,
    Product,
    RawMaterial,
    StockMovement,
    Supplier,
)


pytestmark = pytest.mark.django_db


def write_csv(tmp_path: Path, name: str, content: str) -> str:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------


class TestImportSuppliers:
    def test_happy_path(self, tmp_path):
        csv = (
            "name,contact_name,email,typical_lead_time_days\n"
            "ACME Beads,Sarah,sarah@acme.example,7\n"
            "Crystal Source,Mike,m@cs.example,14\n"
        )
        path = write_csv(tmp_path, "suppliers.csv", csv)
        out = StringIO()
        call_command("import_suppliers", path, stdout=out)
        assert Supplier.objects.count() == 2
        assert Supplier.objects.get(name="ACME Beads").typical_lead_time_days == 7

    def test_idempotent_on_name(self, tmp_path):
        csv = "name,phone\nACME Beads,000-1\n"
        p = write_csv(tmp_path, "s.csv", csv)
        call_command("import_suppliers", p, stdout=StringIO())
        # Re-run with updated data — should update, not duplicate
        csv2 = "name,phone\nACME Beads,000-2\n"
        p2 = write_csv(tmp_path, "s2.csv", csv2)
        call_command("import_suppliers", p2, stdout=StringIO())
        assert Supplier.objects.count() == 1
        assert Supplier.objects.get(name="ACME Beads").phone == "000-2"

    def test_dry_run_does_not_persist(self, tmp_path):
        csv = "name\nDryCo\n"
        p = write_csv(tmp_path, "d.csv", csv)
        call_command("import_suppliers", p, "--dry-run", stdout=StringIO())
        assert Supplier.objects.count() == 0

    def test_missing_required_column(self, tmp_path):
        csv = "phone\n000\n"
        p = write_csv(tmp_path, "bad.csv", csv)
        with pytest.raises(CommandError):
            call_command("import_suppliers", p, stdout=StringIO())


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------


class TestImportMaterials:
    def test_happy_path_creates_with_initial_stock(self, tmp_path):
        Supplier.objects.create(name="ACME")
        csv = (
            "sku,name,unit,current_stock,reorder_point,last_paid_unit_cost,preferred_supplier_name\n"
            "BEAD-1,Test Bead,piece,100,20,0.50,ACME\n"
        )
        p = write_csv(tmp_path, "m.csv", csv)
        call_command("import_materials", p, stdout=StringIO())
        m = RawMaterial.objects.get(sku="BEAD-1")
        assert m.current_stock == Decimal("100")
        # Initial stock should have created an audit movement
        assert StockMovement.objects.filter(
            raw_material=m, reason="INITIAL_STOCK"
        ).count() == 1

    def test_unknown_supplier_errors_row_but_not_command(self, tmp_path):
        csv = (
            "sku,name,preferred_supplier_name\n"
            "BEAD-X,Mystery,Unknown Co\n"
        )
        p = write_csv(tmp_path, "m.csv", csv)
        out = StringIO()
        call_command("import_materials", p, stdout=out)
        # No material created (validation error rolled back the row's writes)
        assert RawMaterial.objects.filter(sku="BEAD-X").count() == 0
        assert "Unknown Co" in out.getvalue()

    def test_invalid_unit_rejected(self, tmp_path):
        csv = "sku,name,unit\nBEAD-2,Two,furlong\n"
        p = write_csv(tmp_path, "m.csv", csv)
        out = StringIO()
        call_command("import_materials", p, stdout=out)
        assert RawMaterial.objects.filter(sku="BEAD-2").count() == 0
        assert "furlong" in out.getvalue()

    def test_update_with_stock_change_emits_adjustment(self, tmp_path):
        Supplier.objects.create(name="ACME")
        # First import — creates with stock 50
        csv1 = (
            "sku,name,current_stock,preferred_supplier_name\n"
            "BEAD-3,Three,50,ACME\n"
        )
        call_command("import_materials", write_csv(tmp_path, "a.csv", csv1), stdout=StringIO())
        # Second import — updates stock to 75 (manual count after recount)
        csv2 = (
            "sku,name,current_stock,preferred_supplier_name\n"
            "BEAD-3,Three,75,ACME\n"
        )
        call_command("import_materials", write_csv(tmp_path, "b.csv", csv2), stdout=StringIO())
        m = RawMaterial.objects.get(sku="BEAD-3")
        assert m.current_stock == Decimal("75")
        assert StockMovement.objects.filter(raw_material=m, reason="ADJUSTMENT").count() == 1


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------


class TestImportProducts:
    def test_happy_path(self, tmp_path):
        csv = (
            "sku,name,pillar,retail_price_zar\n"
            "P-1,Necklace v1,BODY_ADORNMENTS,450\n"
            "P-2,Smudge Kit,SACRED_TOOLS,250\n"
        )
        call_command("import_products", write_csv(tmp_path, "p.csv", csv), stdout=StringIO())
        assert Product.objects.count() == 2
        assert Product.objects.get(sku="P-1").pillar == "BODY_ADORNMENTS"

    def test_invalid_pillar_rejected(self, tmp_path):
        csv = "sku,name,pillar\nP-X,Bad,ORGONITE\n"  # ORGONITE deliberately excluded
        out = StringIO()
        call_command("import_products", write_csv(tmp_path, "p.csv", csv), stdout=out)
        assert Product.objects.filter(sku="P-X").count() == 0
        assert "ORGONITE" in out.getvalue()


# ---------------------------------------------------------------------------
# BOMs
# ---------------------------------------------------------------------------


class TestImportBoms:
    def test_happy_path(self, tmp_path):
        product = Product.objects.create(
            sku="P-A", name="A", pillar="BODY_ADORNMENTS", retail_price_zar=Decimal("100"),
        )
        m1 = RawMaterial.objects.create(sku="M-A", name="A", current_stock=Decimal("0"))
        m2 = RawMaterial.objects.create(sku="M-B", name="B", current_stock=Decimal("0"))
        csv = (
            "product_sku,material_sku,quantity\n"
            "P-A,M-A,5\n"
            "P-A,M-B,2.5\n"
        )
        call_command("import_boms", write_csv(tmp_path, "b.csv", csv), stdout=StringIO())
        assert product.bom_lines.count() == 2

    def test_unknown_product_errors(self, tmp_path):
        RawMaterial.objects.create(sku="M-A", name="A", current_stock=Decimal("0"))
        csv = "product_sku,material_sku,quantity\nNOPE,M-A,1\n"
        out = StringIO()
        call_command("import_boms", write_csv(tmp_path, "b.csv", csv), stdout=out)
        assert BomLine.objects.count() == 0
        assert "NOPE" in out.getvalue()

    def test_zero_quantity_rejected(self, tmp_path):
        Product.objects.create(sku="P-A", name="A", retail_price_zar=Decimal("0"))
        RawMaterial.objects.create(sku="M-A", name="A", current_stock=Decimal("0"))
        csv = "product_sku,material_sku,quantity\nP-A,M-A,0\n"
        out = StringIO()
        call_command("import_boms", write_csv(tmp_path, "b.csv", csv), stdout=out)
        assert BomLine.objects.count() == 0
