"""
Route-level smoke tests. Confirms the URL surface is wired and the
templates render without crashing.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from inventory.models import (
    BomLine,
    ProductionRun,
    Product,
    PurchaseOrder,
    PurchaseOrderLine,
    RawMaterial,
    Supplier,
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


class TestPublicRoutes:
    def test_healthz_unauthenticated(self):
        c = Client()
        r = c.get("/healthz/")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    def test_dashboard_redirects_when_anonymous(self):
        c = Client()
        r = c.get("/")
        # login_required redirects to LOGIN_URL with ?next=
        assert r.status_code == 302
        assert "/admin/login/" in r["Location"]


class TestDashboardRendersForAuthedUser:
    def test_dashboard_empty_state(self, authed):
        r = authed.get("/")
        assert r.status_code == 200
        assert b"Today's snapshot" in r.content
        # Empty-state copy for low-stock
        assert b"Everything is above its reorder point" in r.content

    def test_dashboard_with_data(self, authed):
        s = Supplier.objects.create(name="ACME")
        rm = RawMaterial.objects.create(
            sku="X-1", name="Test material", unit="piece",
            current_stock=Decimal("5"), reorder_point=Decimal("10"),
            last_paid_unit_cost=Decimal("1"),
        )
        p = Product.objects.create(
            sku="P-1", name="Test product", pillar="BODY_ADORNMENTS",
            retail_price_zar=Decimal("100"),
        )
        BomLine.objects.create(product=p, raw_material=rm, quantity=Decimal("1"))
        po = PurchaseOrder.objects.create(supplier=s)
        PurchaseOrderLine.objects.create(
            purchase_order=po, raw_material=rm,
            quantity=Decimal("10"), unit_cost=Decimal("1"),
        )

        r = authed.get("/")
        assert r.status_code == 200
        assert b"Test material" in r.content
        # The REORDER badge for the low-stock material
        assert b"REORDER" in r.content
        # The PO reference
        assert po.reference.encode() in r.content


class TestAdminLoads:
    def test_admin_index_loads_for_superuser(self, authed):
        r = authed.get("/admin/")
        assert r.status_code == 200

    def test_raw_material_changelist(self, authed):
        r = authed.get("/admin/inventory/rawmaterial/")
        assert r.status_code == 200

    def test_product_changelist(self, authed):
        r = authed.get("/admin/inventory/product/")
        assert r.status_code == 200

    def test_purchase_order_changelist(self, authed):
        r = authed.get("/admin/inventory/purchaseorder/")
        assert r.status_code == 200

    def test_production_run_changelist(self, authed):
        r = authed.get("/admin/inventory/productionrun/")
        assert r.status_code == 200

    def test_supplier_changelist(self, authed):
        r = authed.get("/admin/inventory/supplier/")
        assert r.status_code == 200

    def test_stock_movement_changelist(self, authed):
        r = authed.get("/admin/inventory/stockmovement/")
        assert r.status_code == 200
