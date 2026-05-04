"""Tests for project + PO cancel flows with stock reversal."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.test import Client

from inventory.models import (
    BomLine,
    Brand,
    Product,
    ProductionRun,
    ProductVariant,
    Project,
    ProjectItem,
    PurchaseOrder,
    PurchaseOrderLine,
    RawMaterial,
    StockMovement,
    Supplier,
    Variant,
)


pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return get_user_model().objects.create_superuser(
        username="tersia", password="strong-test-password-1", email="t@example.com",
    )


@pytest.fixture
def authed(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def setup():
    s = Supplier.objects.create(name="Temu")
    b = Brand.objects.create(code="SBR", name="Sugar Bush")
    v = Variant.objects.create(code="SBR01", name="Tangerine", brand=b)
    p = Product.objects.create(code="SBR00EARR", name="Earrings", brand=b,
                               default_retail_price_zar=Decimal("450"))
    rm = RawMaterial.objects.create(
        sku="BEAD-1", name="Test bead", current_stock=Decimal("100"),
        reorder_point=Decimal("20"), pack_size=Decimal("100"),
        last_paid_unit_cost=Decimal("0.5"), preferred_supplier=s,
    )
    pv = ProductVariant.objects.create(product=p, variant=v, sku="SBR01EARR")
    BomLine.objects.create(product_variant=pv, raw_material=rm, quantity=Decimal("10"))
    return {"supplier": s, "rm": rm, "pv": pv}


# ---------------------------------------------------------------------------
# Project cancel
# ---------------------------------------------------------------------------


class TestProjectCancel:
    def test_cancel_with_no_runs_no_stock_change(self, authed, setup):
        rm = setup["rm"]
        before = rm.current_stock
        project = Project.objects.create(name="P1", status="IN_PROGRESS")
        ProjectItem.objects.create(project=project, product_variant=setup["pv"], quantity_planned=3)

        # GET shows confirm page
        r = authed.get(f"/track/project/{project.pk}/cancel/")
        assert r.status_code == 200

        # POST commits
        r = authed.post(f"/track/project/{project.pk}/cancel/")
        assert r.status_code == 302

        project.refresh_from_db()
        rm.refresh_from_db()
        assert project.status == "CANCELLED"
        assert rm.current_stock == before
        # No ADJUSTMENT movement was emitted
        assert StockMovement.objects.filter(reason="ADJUSTMENT").count() == 0

    def test_cancel_with_runs_restores_stock(self, authed, setup):
        rm = setup["rm"]
        pv = setup["pv"]
        project = Project.objects.create(name="P1", status="IN_PROGRESS")
        item = ProjectItem.objects.create(project=project, product_variant=pv, quantity_planned=3)
        # Record 2 production runs: 1 unit and 2 units. Total consumed = 30 beads.
        ProductionRun.objects.create(product_variant=pv, quantity=1,
                                     project=project, project_item=item)
        ProductionRun.objects.create(product_variant=pv, quantity=2,
                                     project=project, project_item=item)
        rm.refresh_from_db()
        assert rm.current_stock == Decimal("70")  # 100 - 30

        # Cancel
        authed.post(f"/track/project/{project.pk}/cancel/")
        project.refresh_from_db()
        rm.refresh_from_db()
        assert project.status == "CANCELLED"
        assert rm.current_stock == Decimal("100")  # restored
        # An ADJUSTMENT was emitted for the bead with delta = +30
        adj = StockMovement.objects.filter(reason="ADJUSTMENT", raw_material=rm)
        assert adj.count() == 1
        assert adj.first().delta == Decimal("30")

    def test_cancel_preserves_audit_invariant(self, authed, setup):
        """current_stock should still equal sum(movements) after cancel."""
        rm = setup["rm"]
        StockMovement.objects.create(raw_material=rm, delta=rm.current_stock,
                                     reason="INITIAL_STOCK", note="seed")
        project = Project.objects.create(name="P1", status="IN_PROGRESS")
        item = ProjectItem.objects.create(project=project, product_variant=setup["pv"], quantity_planned=2)
        ProductionRun.objects.create(product_variant=setup["pv"], quantity=2,
                                     project=project, project_item=item)
        authed.post(f"/track/project/{project.pk}/cancel/")
        rm.refresh_from_db()
        total = rm.movements.aggregate(s=Sum("delta"))["s"]
        assert rm.current_stock == total

    def test_already_cancelled_is_idempotent(self, authed, setup):
        project = Project.objects.create(name="P1", status="CANCELLED")
        r = authed.post(f"/track/project/{project.pk}/cancel/")
        assert r.status_code == 302  # redirects with info message

    def test_production_runs_remain_in_audit_log(self, authed, setup):
        """Cancelling does NOT delete the original ProductionRuns — they stay
        as immutable audit history."""
        project = Project.objects.create(name="P1", status="IN_PROGRESS")
        item = ProjectItem.objects.create(project=project, product_variant=setup["pv"], quantity_planned=1)
        ProductionRun.objects.create(product_variant=setup["pv"], quantity=1,
                                     project=project, project_item=item)
        authed.post(f"/track/project/{project.pk}/cancel/")
        # Run still exists
        assert project.production_runs.count() == 1


# ---------------------------------------------------------------------------
# PO cancel
# ---------------------------------------------------------------------------


class TestPoCancel:
    def test_cancel_draft_no_stock_change(self, authed, setup):
        po = PurchaseOrder.objects.create(supplier=setup["supplier"], status="DRAFT")
        PurchaseOrderLine.objects.create(
            purchase_order=po, raw_material=setup["rm"],
            pack_size=Decimal("100"), pack_count=Decimal("1"), unit_cost=Decimal("0.5"),
        )
        before = setup["rm"].current_stock
        authed.post(f"/purchase/po/{po.pk}/cancel/")
        po.refresh_from_db()
        setup["rm"].refresh_from_db()
        assert po.status == "CANCELLED"
        assert setup["rm"].current_stock == before

    def test_cancel_sent_no_stock_change(self, authed, setup):
        po = PurchaseOrder.objects.create(supplier=setup["supplier"], status="SENT")
        PurchaseOrderLine.objects.create(
            purchase_order=po, raw_material=setup["rm"],
            pack_size=Decimal("100"), pack_count=Decimal("1"), unit_cost=Decimal("0.5"),
        )
        before = setup["rm"].current_stock
        authed.post(f"/purchase/po/{po.pk}/cancel/")
        po.refresh_from_db()
        setup["rm"].refresh_from_db()
        assert po.status == "CANCELLED"
        assert setup["rm"].current_stock == before

    def test_cancel_received_reverses_stock(self, authed, setup):
        po = PurchaseOrder.objects.create(supplier=setup["supplier"], status="DRAFT")
        PurchaseOrderLine.objects.create(
            purchase_order=po, raw_material=setup["rm"],
            pack_size=Decimal("100"), pack_count=Decimal("2"), unit_cost=Decimal("0.5"),
        )
        po.status = "RECEIVED"
        po.save()  # Adds 200 units
        setup["rm"].refresh_from_db()
        assert setup["rm"].current_stock == Decimal("300")  # was 100, +200

        # Cancel — should remove the 200
        authed.post(f"/purchase/po/{po.pk}/cancel/")
        po.refresh_from_db()
        setup["rm"].refresh_from_db()
        assert po.status == "CANCELLED"
        assert setup["rm"].current_stock == Decimal("100")
        # An ADJUSTMENT with delta = -200
        adj = StockMovement.objects.filter(
            reason="ADJUSTMENT", raw_material=setup["rm"], related_object_id=po.pk,
        )
        assert adj.count() == 1
        assert adj.first().delta == Decimal("-200")

    def test_already_cancelled_is_idempotent(self, authed, setup):
        po = PurchaseOrder.objects.create(supplier=setup["supplier"], status="CANCELLED")
        r = authed.post(f"/purchase/po/{po.pk}/cancel/")
        assert r.status_code == 302
