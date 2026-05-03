"""
Tests for the load-bearing logic of the inventory app.

Coverage:
- BOM deduction on ProductionRun.save()
- PurchaseOrder receipt → stock increment + StockMovement
- Reorder threshold detection
- Stock-movement / current-stock invariant
- Production-run guardrails (no negative stock, immutable, no delete)
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Sum

from inventory.models import (
    BomLine,
    InsufficientStockError,
    Product,
    ProductionRun,
    PurchaseOrder,
    PurchaseOrderLine,
    RawMaterial,
    StockMovement,
    Supplier,
)


pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def supplier():
    return Supplier.objects.create(name="Local Bead Co.", typical_lead_time_days=7)


@pytest.fixture
def bead_red(supplier):
    return RawMaterial.objects.create(
        sku="BEAD-RED-6MM",
        name="6mm red bead",
        unit="piece",
        current_stock=Decimal("100"),
        reorder_point=Decimal("20"),
        reorder_quantity=Decimal("200"),
        last_paid_unit_cost=Decimal("0.5000"),
        preferred_supplier=supplier,
    )


@pytest.fixture
def bead_white(supplier):
    return RawMaterial.objects.create(
        sku="BEAD-WHITE-6MM",
        name="6mm white bead",
        unit="piece",
        current_stock=Decimal("50"),
        reorder_point=Decimal("10"),
        last_paid_unit_cost=Decimal("0.7500"),
        preferred_supplier=supplier,
    )


@pytest.fixture
def wire(supplier):
    return RawMaterial.objects.create(
        sku="WIRE-MEM-1MM",
        name="Memory wire 1mm",
        unit="metre",
        current_stock=Decimal("10.0000"),
        reorder_point=Decimal("2.0000"),
        last_paid_unit_cost=Decimal("12.0000"),
        preferred_supplier=supplier,
    )


@pytest.fixture
def necklace(bead_red, bead_white, wire):
    p = Product.objects.create(
        sku="NECK-001",
        name="Beaded Necklace v1",
        pillar="BODY_ADORNMENTS",
        retail_price_zar=Decimal("450.00"),
    )
    BomLine.objects.create(product=p, raw_material=bead_red, quantity=Decimal("12"))
    BomLine.objects.create(product=p, raw_material=bead_white, quantity=Decimal("8"))
    BomLine.objects.create(product=p, raw_material=wire, quantity=Decimal("0.5"))
    return p


@pytest.fixture
def admin_user():
    return get_user_model().objects.create_superuser(
        username="tersia", password="strong-test-password-1", email="t@example.com",
    )


# ---------------------------------------------------------------------------
# RawMaterial behaviours
# ---------------------------------------------------------------------------


class TestReorderDetection:
    def test_above_threshold_no_reorder(self, bead_red):
        assert bead_red.needs_reorder is False

    def test_at_threshold_triggers_reorder(self, bead_red):
        bead_red.current_stock = bead_red.reorder_point
        assert bead_red.needs_reorder is True

    def test_below_threshold_triggers_reorder(self, bead_red):
        bead_red.current_stock = bead_red.reorder_point - Decimal("0.0001")
        assert bead_red.needs_reorder is True

    def test_stock_value_calculation(self, bead_red):
        # 100 × 0.5000 = 50.00
        assert bead_red.stock_value_zar == Decimal("50.00")


# ---------------------------------------------------------------------------
# Product / BOM behaviours
# ---------------------------------------------------------------------------


class TestProductMaterialCost:
    def test_material_cost_sums_bom(self, necklace):
        # 12*0.5 + 8*0.75 + 0.5*12 = 6 + 6 + 6 = 18.00
        assert necklace.material_cost == Decimal("18.0000")
        assert necklace.material_cost_display == Decimal("18.00")

    def test_gross_margin(self, necklace):
        # 450 - 18 = 432
        assert necklace.gross_margin_zar == Decimal("432.00")
        # 432/450 = 96%
        assert necklace.gross_margin_pct == Decimal("96.00")

    def test_zero_price_returns_none_margin_pct(self, necklace):
        necklace.retail_price_zar = Decimal("0")
        assert necklace.gross_margin_pct is None


class TestCanMakeUnits:
    def test_bottleneck_drives_max(self, necklace, bead_red, bead_white, wire):
        # red: 100/12 = 8 (bottleneck depending on others)
        # white: 50/8 = 6  ← bottleneck
        # wire: 10/0.5 = 20
        assert necklace.can_make_units == 6

    def test_zero_stock_in_one_material_caps_at_zero(self, necklace, bead_white):
        bead_white.current_stock = Decimal("0")
        bead_white.save()
        assert necklace.can_make_units == 0

    def test_no_bom_returns_zero(self):
        p = Product.objects.create(
            sku="EMPTY-1", name="No BOM", retail_price_zar=Decimal("10")
        )
        assert p.can_make_units == 0


class TestBomLineValidation:
    def test_zero_quantity_rejected(self, necklace, bead_red):
        # use a different material to avoid the unique_together conflict
        new_mat = RawMaterial.objects.create(
            sku="X", name="x", current_stock=Decimal("1"), last_paid_unit_cost=Decimal("1")
        )
        line = BomLine(product=necklace, raw_material=new_mat, quantity=Decimal("0"))
        with pytest.raises(ValidationError):
            line.full_clean()


# ---------------------------------------------------------------------------
# Production runs — the BOM deduction trigger
# ---------------------------------------------------------------------------


class TestProductionRunDeduction:
    def test_single_run_deducts_correctly(self, necklace, bead_red, bead_white, wire):
        ProductionRun.objects.create(product=necklace, quantity=2)

        bead_red.refresh_from_db()
        bead_white.refresh_from_db()
        wire.refresh_from_db()

        # 100 - 2*12 = 76
        assert bead_red.current_stock == Decimal("76.0000")
        # 50 - 2*8 = 34
        assert bead_white.current_stock == Decimal("34.0000")
        # 10 - 2*0.5 = 9.0
        assert wire.current_stock == Decimal("9.0000")

    def test_movements_emitted_for_each_bom_line(self, necklace):
        ProductionRun.objects.create(product=necklace, quantity=1)
        movements = StockMovement.objects.filter(reason="PRODUCTION_CONSUMED")
        assert movements.count() == 3
        # all deltas are negative
        assert all(m.delta < 0 for m in movements)

    def test_insufficient_stock_blocks_run(self, necklace, bead_white):
        # only 50 white beads; needs 8 per unit → can make 6, 7 should fail
        with pytest.raises(InsufficientStockError):
            ProductionRun.objects.create(product=necklace, quantity=7)
        # Confirm no partial deduction happened
        bead_white.refresh_from_db()
        assert bead_white.current_stock == Decimal("50")
        assert StockMovement.objects.filter(reason="PRODUCTION_CONSUMED").count() == 0

    def test_zero_quantity_rejected(self, necklace):
        run = ProductionRun(product=necklace, quantity=0)
        with pytest.raises(ValidationError):
            run.full_clean()

    def test_run_is_immutable(self, necklace):
        run = ProductionRun.objects.create(product=necklace, quantity=1)
        run.notes = "edited"
        with pytest.raises(ValidationError):
            run.save()

    def test_run_cannot_be_deleted(self, necklace):
        run = ProductionRun.objects.create(product=necklace, quantity=1)
        with pytest.raises(ValidationError):
            run.delete()

    def test_user_recorded_when_provided(self, necklace, admin_user):
        run = ProductionRun.objects.create(
            product=necklace, quantity=1, created_by=admin_user
        )
        movements = StockMovement.objects.filter(
            reason="PRODUCTION_CONSUMED", related_object_id=run.pk
        )
        assert all(m.created_by_id == admin_user.id for m in movements)


# ---------------------------------------------------------------------------
# Purchase orders — the receipt trigger
# ---------------------------------------------------------------------------


class TestPurchaseOrderReceipt:
    def test_draft_po_does_not_change_stock(self, supplier, bead_red):
        po = PurchaseOrder.objects.create(supplier=supplier, status="DRAFT")
        PurchaseOrderLine.objects.create(
            purchase_order=po, raw_material=bead_red,
            quantity=Decimal("100"), unit_cost=Decimal("0.45"),
        )
        bead_red.refresh_from_db()
        assert bead_red.current_stock == Decimal("100")

    def test_marking_received_increments_stock(self, supplier, bead_red):
        po = PurchaseOrder.objects.create(supplier=supplier, status="DRAFT")
        PurchaseOrderLine.objects.create(
            purchase_order=po, raw_material=bead_red,
            quantity=Decimal("100"), unit_cost=Decimal("0.45"),
        )
        po.status = "RECEIVED"
        po.save()
        bead_red.refresh_from_db()
        assert bead_red.current_stock == Decimal("200")
        assert bead_red.last_paid_unit_cost == Decimal("0.4500")
        assert StockMovement.objects.filter(reason="PO_RECEIVED").count() == 1

    def test_receipt_is_idempotent_on_resave(self, supplier, bead_red):
        po = PurchaseOrder.objects.create(supplier=supplier, status="RECEIVED")
        PurchaseOrderLine.objects.create(
            purchase_order=po, raw_material=bead_red,
            quantity=Decimal("100"), unit_cost=Decimal("0.45"),
        )
        # The line was added AFTER the receipt; so first save with status already
        # RECEIVED applied no receipt (transition was None → RECEIVED at create
        # but no lines existed). Re-save should NOT re-fire because status
        # didn't transition.
        po.notes = "edited"
        po.save()
        # No movement created from the resave (no transition)
        assert StockMovement.objects.filter(reason="PO_RECEIVED").count() == 0

    def test_reference_auto_generated(self, supplier):
        po = PurchaseOrder.objects.create(supplier=supplier)
        assert po.reference.startswith("PO-")
        # Format: PO-YYYYMMDD-NNN  →  3 + 8 + 1 + 3 = 15 chars
        assert len(po.reference) == 15

    def test_reference_increments_within_day(self, supplier):
        a = PurchaseOrder.objects.create(supplier=supplier)
        b = PurchaseOrder.objects.create(supplier=supplier)
        assert a.reference != b.reference
        # Both share the date prefix
        assert a.reference[:11] == b.reference[:11]

    def test_total_cost(self, supplier, bead_red, bead_white):
        po = PurchaseOrder.objects.create(supplier=supplier)
        PurchaseOrderLine.objects.create(
            purchase_order=po, raw_material=bead_red,
            quantity=Decimal("100"), unit_cost=Decimal("0.50"),
        )
        PurchaseOrderLine.objects.create(
            purchase_order=po, raw_material=bead_white,
            quantity=Decimal("50"), unit_cost=Decimal("0.80"),
        )
        # 100*0.5 + 50*0.8 = 50 + 40 = 90
        assert po.total_cost == Decimal("90.00")


# ---------------------------------------------------------------------------
# Audit invariant: current_stock must equal sum(movements) for every material
# ---------------------------------------------------------------------------


class TestStockInvariant:
    def test_invariant_holds_after_lifecycle(self, supplier, necklace, bead_red, bead_white, wire):
        # Initial stock recorded as INITIAL_STOCK movements (we do this for
        # the test materials retroactively to model real-world usage).
        for m in (bead_red, bead_white, wire):
            StockMovement.objects.create(
                raw_material=m,
                delta=m.current_stock,
                reason="INITIAL_STOCK",
                note="Test fixture initial stock",
            )

        # PO receipt
        po = PurchaseOrder.objects.create(supplier=supplier, status="DRAFT")
        PurchaseOrderLine.objects.create(
            purchase_order=po, raw_material=bead_red,
            quantity=Decimal("50"), unit_cost=Decimal("0.5"),
        )
        po.status = "RECEIVED"
        po.save()

        # Production run
        ProductionRun.objects.create(product=necklace, quantity=3)

        # Now: every material's current_stock should equal sum(its movements)
        for m in (bead_red, bead_white, wire):
            m.refresh_from_db()
            total = m.movements.aggregate(s=Sum("delta"))["s"] or Decimal("0")
            assert m.current_stock == total, (
                f"{m.sku}: current_stock={m.current_stock} but movements sum to {total}"
            )
