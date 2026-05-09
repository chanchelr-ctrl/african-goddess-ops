"""Route smoke tests for v0.2."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from inventory.models import (
    BomLine,
    Brand,
    Product,
    ProductVariant,
    Project,
    ProjectItem,
    RawMaterial,
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


def _seed_minimal():
    s = Supplier.objects.create(name="Temu")
    b = Brand.objects.create(code="SBR", name="Sugar Bush")
    v = Variant.objects.create(code="SBR01", name="Tangerine & Orange", brand=b)
    p = Product.objects.create(
        code="SBR00EARR", name="Sugar Bush Earrings", brand=b,
        pillar="BODY_ADORNMENTS", default_retail_price_zar=Decimal("450"),
    )
    rm = RawMaterial.objects.create(
        sku="BEAD-1", name="Test bead", current_stock=Decimal("5"),
        reorder_point=Decimal("10"), pack_size=Decimal("100"),
        last_paid_unit_cost=Decimal("0.5"), preferred_supplier=s,
    )
    pv = ProductVariant.objects.create(product=p, variant=v, sku="SBR01-EARR")
    BomLine.objects.create(product_variant=pv, raw_material=rm, quantity=Decimal("1"))
    return {"supplier": s, "brand": b, "variant": v, "product": p, "rm": rm, "pv": pv}


class TestPublicRoutes:
    def test_healthz(self):
        r = Client().get("/healthz/")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    def test_dashboard_redirects_anon(self):
        r = Client().get("/")
        assert r.status_code == 302
        assert "/admin/login/" in r["Location"]


class TestDashboard:
    def test_empty(self, authed):
        r = authed.get("/")
        assert r.status_code == 200
        assert b"snapshot" in r.content.lower()

    def test_with_data(self, authed):
        _seed_minimal()
        r = authed.get("/")
        assert r.status_code == 200
        # The low-stock material should surface
        assert b"BEAD-1" in r.content


class TestWorkflowRoutes:
    def test_build_index(self, authed):
        _seed_minimal()
        r = authed.get("/build/")
        assert r.status_code == 200

    def test_build_check_no_selection(self, authed):
        _seed_minimal()
        r = authed.get("/build/check/")
        assert r.status_code == 200

    def test_build_check_with_selection(self, authed):
        _seed_minimal()
        r = authed.get("/build/check/?variant=SBR01-EARR&qty=3")
        assert r.status_code == 200
        # 5 stock vs need 3 -> sufficient. content should reflect that.
        assert b"SBR01-EARR" in r.content

    def test_track_index(self, authed):
        r = authed.get("/track/")
        assert r.status_code == 200

    def test_purchase_index(self, authed):
        _seed_minimal()
        r = authed.get("/purchase/")
        assert r.status_code == 200


class TestAdminLoads:
    @pytest.mark.parametrize("path", [
        "/admin/",
        "/admin/inventory/brand/",
        "/admin/inventory/variant/",
        "/admin/inventory/product/",
        "/admin/inventory/productvariant/",
        "/admin/inventory/rawmaterial/",
        "/admin/inventory/supplier/",
        "/admin/inventory/purchaseorder/",
        "/admin/inventory/productionrun/",
        "/admin/inventory/project/",
        "/admin/inventory/projectitem/",
        "/admin/inventory/stockmovement/",
    ])
    def test_loads(self, authed, path):
        r = authed.get(path)
        assert r.status_code == 200, f"{path}: {r.status_code}"
