"""
Tests for v0.2 schema: Brand, Variant, ProductVariant + BOM/PO/ProductionRun.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Sum

from inventory.models import (
    BomLine,
    Brand,
    InsufficientStockError,
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def supplier():
    return Supplier.objects.create(name="Temu")


@pytest.fixture
def brand_sb():
    return Brand.objects.create(code="SBR", name="Sugar Bush")


@pytest.fixture
def brand_agc():
    return Brand.objects.create(code="AGC", name="African Goddess")


@pytest.fixture
def variant_sbr01(brand_sb):
    return Variant.objects.create(code="SBR01", name="Tangerine & Orange", brand=brand_sb)


@pytest.fixture
def variant_sbr02(brand_sb):
    return Variant.objects.create(code="SBR02", name="Magenta & Coral", brand=brand_sb)


@pytest.fixture
def bead_red(supplier):
    return RawMaterial.objects.create(
        sku="BEAD-RED-6MM", name="6mm red bead", unit="piece",
        current_stock=Decimal("100"),
        reorder_point=Decimal("20"), reorder_quantity=Decimal("200"),
        pack_size=Decimal("100"),
        last_paid_pack_cost=Decimal("50"),
        last_paid_unit_cost=Decimal("0.5000"),
        preferred_supplier=supplier,
    )


@pytest.fixture
def bead_white(supplier):
    return RawMaterial.objects.create(
        sku="BEAD-WHITE-6MM", name="6mm white bead", unit="piece",
        current_stock=Decimal("50"),
        reorder_point=Decimal("10"),
        pack_size=Decimal("50"),
        last_paid_pack_cost=Decimal("37.50"),
        last_paid_unit_cost=Decimal("0.7500"),
        preferred_supplier=supplier,
    )


@pytest.fixture
def wire(supplier):
    return RawMaterial.objects.create(
        sku="WIRE-MEM-1MM", name="Memory wire 1mm", unit="metre",
        current_stock=Decimal("10"),
        reorder_point=Decimal("2"),
        pack_size=Decimal("1"),
        last_paid_unit_cost=Decimal("12"),
        preferred_supplier=supplier,
    )


@pytest.fixture
def product_earrings(brand_sb):
    return Product.objects.create(
        code="SBR00EARR", name="Sugar Bush Earrings", brand=brand_sb,
        pillar="BODY_ADORNMENTS", default_retail_price_zar=Decimal("450"),
    )


@pytest.fixture
def pv_sbr01_earr(product_earrings, variant_sbr01, bead_red, bead_white, wire):
    pv = ProductVariant.objects.create(
        product=product_earrings, variant=variant_sbr01, sku="SBR01-EARR",
    )
    BomLine.objects.create(product_variant=pv, raw_material=bead_red, quantity=Decimal("12"))
    BomLine.objects.create(product_variant=pv, raw_material=bead_white, quantity=Decimal("8"))
    BomLine.objects.create(product_variant=pv, raw_material=wire, quantity=Decimal("0.5"))
    return pv


@pytest.fixture
def admin_user():
    return get_user_model().objects.create_superuser(
        username="tersia", password="strong-test-password-1", email="t@example.com",
    )


# ---------------------------------------------------------------------------
# Reorder & stock value
# ---------------------------------------------------------------------------


class TestReorder:
    def test_above_threshold(self, bead_red):
        assert not bead_red.needs_reorder

    def test_at_threshold(self, bead_red):
        bead_red.current_stock = bead_red.reorder_point
        assert bead_red.needs_reorder

    def test_below_threshold(self, bead_red):
        bead_red.current_stock = bead_red.reorder_point - Decimal("0.0001")
        assert bead_red.needs_reorder

    def test_stock_value(self, bead_red):
        assert bead_red.stock_value_zar == Decimal("50.00")

    def test_packs_to_purchase(self, bead_red):
        # Above reorder + reorder_quantity threshold? target = 20 + 200 = 220.
        # have 100; deficit 120; pack_size 100; needs ceil(120/100) = 2 packs
        bead_red.current_stock = Decimal("100")
        assert bead_red.packs_to_purchase == Decimal("2")

    def test_packs_to_purchase_zero_when_well_stocked(self, bead_red):
        bead_red.current_stock = Decimal("500")
        assert bead_red.packs_to_purchase == Decimal("0")


# ---------------------------------------------------------------------------
# ProductVariant computed properties
# ---------------------------------------------------------------------------


class TestProductVariant:
    def test_material_cost_sums_bom(self, pv_sbr01_earr):
        # 12*0.5 + 8*0.75 + 0.5*12 = 6 + 6 + 6 = 18
        assert pv_sbr01_earr.material_cost == Decimal("18.0000")

    def test_effective_price_uses_product_default(self, pv_sbr01_earr):
        # No override on the variant; falls back to product default
        assert pv_sbr01_earr.effective_retail_price_zar == Decimal("450")

    def test_effective_price_override(self, pv_sbr01_earr):
        pv_sbr01_earr.retail_price_zar = Decimal("500")
        pv_sbr01_earr.save()
        assert pv_sbr01_earr.effective_retail_price_zar == Decimal("500")

    def test_gross_margin_pct(self, pv_sbr01_earr):
        # 450 - 18 = 432; 432/450 = 96.00
        assert pv_sbr01_earr.gross_margin_pct == Decimal("96.00")

    def test_can_make_units_bottlenecked(self, pv_sbr01_earr, bead_white):
        # white: 50/8 = 6 — bottleneck
        assert pv_sbr01_earr.can_make_units == 6

    def test_material_shortfalls(self, pv_sbr01_earr):
        sf = pv_sbr01_earr.material_shortfalls(7)
        assert any(s["material"].sku == "BEAD-WHITE-6MM" for s in sf)


# ---------------------------------------------------------------------------
# Production runs
# ---------------------------------------------------------------------------


class TestProductionRun:
    def test_deducts_correctly(self, pv_sbr01_earr, bead_red, bead_white, wire):
        ProductionRun.objects.create(product_variant=pv_sbr01_earr, quantity=2)
        bead_red.refresh_from_db()
        bead_white.refresh_from_db()
        wire.refresh_from_db()
        assert bead_red.current_stock == Decimal("76.0000")
        assert bead_white.current_stock == Decimal("34.0000")
        assert wire.current_stock == Decimal("9.0000")

    def test_emits_movement_per_line(self, pv_sbr01_earr):
        ProductionRun.objects.create(product_variant=pv_sbr01_earr, quantity=1)
        assert StockMovement.objects.filter(reason="PRODUCTION_CONSUMED").count() == 3

    def test_insufficient_stock_blocks(self, pv_sbr01_earr, bead_white):
        with pytest.raises(InsufficientStockError):
            ProductionRun.objects.create(product_variant=pv_sbr01_earr, quantity=7)
        bead_white.refresh_from_db()
        assert bead_white.current_stock == Decimal("50")

    def test_immutable(self, pv_sbr01_earr):
        run = ProductionRun.objects.create(product_variant=pv_sbr01_earr, quantity=1)
        run.notes = "x"
        with pytest.raises(ValidationError):
            run.save()

    def test_no_delete(self, pv_sbr01_earr):
        run = ProductionRun.objects.create(product_variant=pv_sbr01_earr, quantity=1)
        with pytest.raises(ValidationError):
            run.delete()

    def test_increments_project_item_made(self, pv_sbr01_earr):
        project = Project.objects.create(name="P1", status="IN_PROGRESS")
        item = ProjectItem.objects.create(
            project=project, product_variant=pv_sbr01_earr, quantity_planned=3,
        )
        ProductionRun.objects.create(
            product_variant=pv_sbr01_earr, quantity=2,
            project=project, project_item=item,
        )
        item.refresh_from_db()
        assert item.quantity_made == 2


# ---------------------------------------------------------------------------
# Purchase orders (pack-aware)
# ---------------------------------------------------------------------------


class TestPurchaseOrder:
    def test_draft_does_not_change_stock(self, supplier, bead_red):
        po = PurchaseOrder.objects.create(supplier=supplier, status="DRAFT")
        PurchaseOrderLine.objects.create(
            purchase_order=po, raw_material=bead_red,
            pack_size=Decimal("100"), pack_count=Decimal("2"), unit_cost=Decimal("0.45"),
        )
        bead_red.refresh_from_db()
        assert bead_red.current_stock == Decimal("100")

    def test_received_increments_stock_by_units_total(self, supplier, bead_red):
        po = PurchaseOrder.objects.create(supplier=supplier, status="DRAFT")
        PurchaseOrderLine.objects.create(
            purchase_order=po, raw_material=bead_red,
            pack_size=Decimal("100"), pack_count=Decimal("2"), unit_cost=Decimal("0.45"),
        )
        po.status = "RECEIVED"
        po.save()
        bead_red.refresh_from_db()
        # 100 starting + 2 packs * 100 size = 300
        assert bead_red.current_stock == Decimal("300")
        assert bead_red.last_paid_unit_cost == Decimal("0.4500")
        assert StockMovement.objects.filter(reason="PO_RECEIVED").count() == 1

    def test_total_cost(self, supplier, bead_red, bead_white):
        po = PurchaseOrder.objects.create(supplier=supplier)
        PurchaseOrderLine.objects.create(
            purchase_order=po, raw_material=bead_red,
            pack_size=Decimal("100"), pack_count=Decimal("1"), unit_cost=Decimal("0.50"),
        )
        PurchaseOrderLine.objects.create(
            purchase_order=po, raw_material=bead_white,
            pack_size=Decimal("50"), pack_count=Decimal("1"), unit_cost=Decimal("0.80"),
        )
        # 100*0.5 + 50*0.8 = 50 + 40 = 90
        assert po.total_cost == Decimal("90.00")

    def test_reference_auto_generated(self, supplier):
        po = PurchaseOrder.objects.create(supplier=supplier)
        assert po.reference.startswith("PO-")
        assert len(po.reference) == 15  # PO-YYYYMMDD-NNN


# ---------------------------------------------------------------------------
# Project model
# ---------------------------------------------------------------------------


class TestProject:
    def test_aggregate_shortfalls(self, pv_sbr01_earr, bead_white):
        project = Project.objects.create(name="Big build", status="PLANNED")
        ProjectItem.objects.create(
            project=project, product_variant=pv_sbr01_earr, quantity_planned=10,
        )
        # need 80 white beads, have 50 → short 30
        sf = project.aggregate_shortfalls()
        assert any(s["material"].sku == "BEAD-WHITE-6MM" and s["short"] == Decimal("30") for s in sf)

    def test_made_tracking(self, pv_sbr01_earr):
        project = Project.objects.create(name="Small", status="IN_PROGRESS")
        item = ProjectItem.objects.create(
            project=project, product_variant=pv_sbr01_earr, quantity_planned=2,
        )
        ProductionRun.objects.create(
            product_variant=pv_sbr01_earr, quantity=2, project=project, project_item=item,
        )
        item.refresh_from_db()
        project.refresh_from_db()
        assert project.total_made_units == 2
        assert project.is_complete


# ---------------------------------------------------------------------------
# Audit invariant: current_stock == sum(movements) for every material
# ---------------------------------------------------------------------------


class TestAuditInvariant:
    def test_after_lifecycle(self, supplier, pv_sbr01_earr, bead_red, bead_white, wire):
        for m in (bead_red, bead_white, wire):
            StockMovement.objects.create(
                raw_material=m, delta=m.current_stock,
                reason="INITIAL_STOCK", note="fixture initial",
            )
        po = PurchaseOrder.objects.create(supplier=supplier, status="DRAFT")
        PurchaseOrderLine.objects.create(
            purchase_order=po, raw_material=bead_red,
            pack_size=Decimal("100"), pack_count=Decimal("0.5"), unit_cost=Decimal("0.5"),
        )
        po.status = "RECEIVED"
        po.save()
        ProductionRun.objects.create(product_variant=pv_sbr01_earr, quantity=3)
        for m in (bead_red, bead_white, wire):
            m.refresh_from_db()
            total = m.movements.aggregate(s=Sum("delta"))["s"] or Decimal("0")
            assert m.current_stock == total, f"{m.sku}: stock={m.current_stock} sum={total}"
