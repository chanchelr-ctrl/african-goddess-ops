"""Tests for the Temu receipt parser."""

from decimal import Decimal

import pytest

from inventory.views import parse_temu_receipt


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
