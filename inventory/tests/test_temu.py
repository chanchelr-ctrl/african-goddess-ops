"""Tests for the Temu integration helpers."""

from decimal import Decimal

import pytest

from inventory.models import RawMaterial
from inventory.views import parse_temu_receipt, temu_search_key, temu_search_url


pytestmark = pytest.mark.django_db


class TestParseTemuReceipt:
    def test_extracts_order_id(self):
        text = """
        Thank you for your order!
        Order ID: O123456789012345
        Estimated delivery: 14 days
        """
        out = parse_temu_receipt(text)
        assert out.get("order_id") == "O123456789012345"

    def test_extracts_tracking_number(self):
        text = """
        Order Number: O999000111222333
        Tracking Number: ABC123XYZ456
        Total: R 540.00
        """
        out = parse_temu_receipt(text)
        assert out.get("order_id") == "O999000111222333"
        assert out.get("tracking_number") == "ABC123XYZ456"
        assert out.get("total") == Decimal("540.00")

    def test_handles_empty_input(self):
        assert parse_temu_receipt("") == {}
        assert parse_temu_receipt(None) == {}

    def test_handles_unrecognised_text(self):
        out = parse_temu_receipt("just some random text")
        assert out == {}


class TestTemuSearchKey:
    def test_combines_sku_and_name(self):
        m = RawMaterial(sku="DB4914290", name="4mm Faceted Rondelle Yellow Amber")
        assert temu_search_key(m) == "DB4914290 4mm Faceted Rondelle Yellow Amber"

    def test_falls_back_to_sku_only_when_no_name(self):
        m = RawMaterial(sku="DB4914290", name="")
        assert temu_search_key(m) == "DB4914290"

    def test_truncates_long_names(self):
        long_name = "x" * 200
        m = RawMaterial(sku="ABC123", name=long_name)
        key = temu_search_key(m)
        # SKU + space + at most 80 chars of name
        assert key.startswith("ABC123 ")
        assert len(key) <= len("ABC123 ") + 80

    def test_url_encodes_spaces(self):
        m = RawMaterial(sku="ABC123", name="Two words")
        url = temu_search_url(m)
        # quote_plus encodes spaces as +
        assert "search_key=ABC123+Two+words" in url
