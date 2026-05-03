"""Tests for the reconcile_stock management command."""

from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from inventory.models import RawMaterial, StockMovement


pytestmark = pytest.mark.django_db


class TestReconcile:
    def test_clean_data_reports_no_problems(self):
        m = RawMaterial.objects.create(sku="X", name="x", current_stock=Decimal("10"))
        StockMovement.objects.create(raw_material=m, delta=Decimal("10"), reason="INITIAL_STOCK")
        out = StringIO()
        call_command("reconcile_stock", stdout=out)
        assert "reconcile cleanly" in out.getvalue()

    def test_drift_detected(self):
        m = RawMaterial.objects.create(sku="X", name="x", current_stock=Decimal("99"))
        StockMovement.objects.create(raw_material=m, delta=Decimal("10"), reason="INITIAL_STOCK")
        out = StringIO()
        call_command("reconcile_stock", stdout=out)
        assert "diff=" in out.getvalue()
        assert "X" in out.getvalue()

    def test_fix_recomputes_from_movements(self):
        m = RawMaterial.objects.create(sku="X", name="x", current_stock=Decimal("99"))
        StockMovement.objects.create(raw_material=m, delta=Decimal("10"), reason="INITIAL_STOCK")
        StockMovement.objects.create(raw_material=m, delta=Decimal("-3"), reason="ADJUSTMENT")
        call_command("reconcile_stock", "--fix", stdout=StringIO())
        m.refresh_from_db()
        # 10 + (-3) = 7
        assert m.current_stock == Decimal("7")
