"""
Data model for African Goddess inventory & operations.

Design principles:
- Decimal precision = 4 places everywhere quantities or unit-costs appear
- StockMovement is append-only; current_stock on RawMaterial is denormalised
  for speed but reconcilable from the movement log
- Side-effects (BOM deduction, PO receive) happen inside model.save() with
  explicit transactions; no Django signals
- Production runs are immutable; corrections happen via ADJUSTMENT movements
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

ZERO = Decimal("0")


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------


class Supplier(models.Model):
    name = models.CharField(max_length=200, unique=True)
    contact_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    website = models.URLField(blank=True)
    typical_lead_time_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Average days from order placed to receipt.",
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# Raw materials
# ---------------------------------------------------------------------------


class RawMaterial(models.Model):
    UNIT_CHOICES = [
        ("piece", "pieces"),
        ("gram", "grams"),
        ("kg", "kilograms"),
        ("metre", "metres"),
        ("cm", "centimetres"),
        ("ml", "millilitres"),
        ("litre", "litres"),
        ("strand", "strands"),
        ("pack", "packs"),
        ("set", "sets"),
        ("other", "other"),
    ]

    sku = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    unit = models.CharField(max_length=16, choices=UNIT_CHOICES, default="piece")

    current_stock = models.DecimalField(
        max_digits=14, decimal_places=4, default=ZERO,
        help_text="Denormalised running total. Reconcilable from StockMovement log.",
    )
    reorder_point = models.DecimalField(
        max_digits=14, decimal_places=4, default=ZERO,
        help_text="When current_stock <= this, the material flags as needing reorder.",
    )
    reorder_quantity = models.DecimalField(
        max_digits=14, decimal_places=4, default=ZERO,
        help_text="Suggested order quantity when below reorder_point.",
    )
    last_paid_unit_cost = models.DecimalField(
        max_digits=12, decimal_places=4, default=ZERO,
        help_text="Most recent unit cost paid (ZAR). Used for COGS calculation.",
    )

    preferred_supplier = models.ForeignKey(
        Supplier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="materials",
    )

    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return f"{self.name} ({self.sku})"

    @property
    def needs_reorder(self) -> bool:
        return self.current_stock <= self.reorder_point

    @property
    def stock_value_zar(self) -> Decimal:
        return (self.current_stock * self.last_paid_unit_cost).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Products + BOMs
# ---------------------------------------------------------------------------


class Product(models.Model):
    # Orgonite intentionally excluded from this build per client direction
    # (2026-05-02). Re-add in a future migration if scope expands back to it.
    PILLAR_CHOICES = [
        ("BODY_ADORNMENTS", "Body Adornments"),
        ("SACRED_TOOLS", "Sacred Tools"),
        ("BAMBOO_CLOTHING", "Bamboo Clothing"),
        ("OTHER", "Other"),
    ]

    sku = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    pillar = models.CharField(max_length=24, choices=PILLAR_CHOICES, default="BODY_ADORNMENTS")
    retail_price_zar = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("pillar", "name")

    def __str__(self) -> str:
        return f"{self.name} ({self.sku})"

    @property
    def material_cost(self) -> Decimal:
        """Sum of (BOM line quantity × material last-paid unit cost). ZAR."""
        total = ZERO
        for line in self.bom_lines.select_related("raw_material").all():
            total += (line.quantity * line.raw_material.last_paid_unit_cost)
        return total.quantize(Decimal("0.0001"))

    @property
    def material_cost_display(self) -> Decimal:
        return self.material_cost.quantize(Decimal("0.01"))

    @property
    def gross_margin_zar(self) -> Decimal:
        return (self.retail_price_zar - self.material_cost).quantize(Decimal("0.01"))

    @property
    def gross_margin_pct(self) -> Optional[Decimal]:
        if self.retail_price_zar == 0:
            return None
        ratio = (self.retail_price_zar - self.material_cost) / self.retail_price_zar
        return (ratio * 100).quantize(Decimal("0.01"))

    @property
    def can_make_units(self) -> int:
        """Max whole units producible from current raw-material stock.

        Bottleneck = the BOM line whose ratio (current_stock / required_per_unit)
        is smallest. Returns 0 if any required material has zero qty.
        """
        lines = list(self.bom_lines.select_related("raw_material").all())
        if not lines:
            return 0
        max_units: Optional[int] = None
        for line in lines:
            if line.quantity <= 0:
                continue
            possible = int(line.raw_material.current_stock // line.quantity)
            if max_units is None or possible < max_units:
                max_units = possible
        return max(max_units or 0, 0)


class BomLine(models.Model):
    """One ingredient in a Product's bill of materials."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="bom_lines")
    raw_material = models.ForeignKey(RawMaterial, on_delete=models.PROTECT, related_name="bom_lines")
    quantity = models.DecimalField(
        max_digits=14, decimal_places=4,
        help_text="Quantity of raw_material consumed per unit of product.",
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = (("product", "raw_material"),)
        ordering = ("product", "raw_material")

    def __str__(self) -> str:
        return f"{self.product.sku}: {self.quantity} × {self.raw_material.sku}"

    def clean(self) -> None:
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({"quantity": "BOM quantity must be greater than zero."})


# ---------------------------------------------------------------------------
# Stock movements (append-only audit log)
# ---------------------------------------------------------------------------


class StockMovement(models.Model):
    REASON_CHOICES = [
        ("PO_RECEIVED", "Purchase order received"),
        ("PRODUCTION_CONSUMED", "Production run consumed"),
        ("ADJUSTMENT", "Manual adjustment"),
        ("INITIAL_STOCK", "Initial / opening stock"),
    ]

    raw_material = models.ForeignKey(
        RawMaterial,
        on_delete=models.PROTECT,
        related_name="movements",
    )
    delta = models.DecimalField(
        max_digits=14, decimal_places=4,
        help_text="Signed change to current_stock. Positive = received, negative = consumed.",
    )
    reason = models.CharField(max_length=32, choices=REASON_CHOICES)
    related_object_type = models.CharField(max_length=64, blank=True)
    related_object_id = models.PositiveBigIntegerField(null=True, blank=True)
    note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["raw_material", "-created_at"]),
            models.Index(fields=["reason", "-created_at"]),
        ]

    def __str__(self) -> str:
        sign = "+" if self.delta > 0 else ""
        return f"{self.raw_material.sku}: {sign}{self.delta} ({self.get_reason_display()})"


# ---------------------------------------------------------------------------
# Purchase orders
# ---------------------------------------------------------------------------


class PurchaseOrder(models.Model):
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("SENT", "Sent to supplier"),
        ("RECEIVED", "Received"),
        ("CANCELLED", "Cancelled"),
    ]

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    reference = models.CharField(max_length=64, unique=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="DRAFT", db_index=True)

    expected_date = models.DateField(null=True, blank=True)
    received_date = models.DateField(null=True, blank=True)

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.reference or 'PO?'} — {self.supplier.name} [{self.get_status_display()}]"

    @property
    def total_cost(self) -> Decimal:
        total = ZERO
        for line in self.lines.all():
            total += (line.quantity * line.unit_cost)
        return total.quantize(Decimal("0.01"))

    def save(self, *args, **kwargs) -> None:
        # Auto-generate reference on first save
        if not self.reference:
            self.reference = self._generate_reference()

        is_new = self._state.adding
        prior_status: Optional[str] = None
        if not is_new:
            prior_status = type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()

        # Default received_date when status flips to RECEIVED
        if self.status == "RECEIVED" and self.received_date is None:
            self.received_date = timezone.localdate()

        with transaction.atomic():
            super().save(*args, **kwargs)
            # Side-effect: when status transitions INTO RECEIVED, create stock movements
            if self.status == "RECEIVED" and prior_status != "RECEIVED":
                self._apply_receipt_to_stock()

    def _generate_reference(self) -> str:
        prefix = "PO-" + timezone.localdate().strftime("%Y%m%d")
        existing = type(self).objects.filter(reference__startswith=prefix).count()
        return f"{prefix}-{existing + 1:03d}"

    def _apply_receipt_to_stock(self) -> None:
        """Increment raw-material stock for every line on this PO. Idempotent
        because the StockMovement audit log preserves history; we guard against
        double-applying by only firing on the DRAFT/SENT → RECEIVED transition.
        """
        for line in self.lines.select_related("raw_material").all():
            if line.quantity <= 0:
                continue
            material = line.raw_material
            material.current_stock = (material.current_stock + line.quantity)
            material.last_paid_unit_cost = line.unit_cost
            material.save(update_fields=["current_stock", "last_paid_unit_cost", "updated_at"])
            StockMovement.objects.create(
                raw_material=material,
                delta=line.quantity,
                reason="PO_RECEIVED",
                related_object_type="PurchaseOrder",
                related_object_id=self.pk,
                note=f"Received on PO {self.reference} from {self.supplier.name}",
            )


class PurchaseOrderLine(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    raw_material = models.ForeignKey(RawMaterial, on_delete=models.PROTECT, related_name="po_lines")
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=4)

    class Meta:
        ordering = ("purchase_order", "raw_material")

    def __str__(self) -> str:
        return f"{self.raw_material.sku}: {self.quantity} @ R{self.unit_cost}"

    @property
    def line_total(self) -> Decimal:
        return (self.quantity * self.unit_cost).quantize(Decimal("0.01"))

    def clean(self) -> None:
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({"quantity": "PO line quantity must be greater than zero."})
        if self.unit_cost is not None and self.unit_cost < 0:
            raise ValidationError({"unit_cost": "Unit cost cannot be negative."})


# ---------------------------------------------------------------------------
# Production runs (the BOM-deduction trigger)
# ---------------------------------------------------------------------------


class InsufficientStockError(ValidationError):
    """Raised when a production run would drive raw-material stock negative."""


class ProductionRun(models.Model):
    """Tersia recording 'I made N units of product X today'.

    On save, each BOM ingredient is decremented by (line.quantity * run.quantity)
    inside a single transaction, and StockMovement rows are written.
    Production runs are immutable once saved — corrections happen via a
    StockMovement.ADJUSTMENT entered manually.
    """

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="production_runs")
    quantity = models.PositiveIntegerField(help_text="Number of finished units produced.")
    run_date = models.DateField(default=timezone.localdate)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="production_runs",
    )

    class Meta:
        ordering = ("-run_date", "-created_at")

    def __str__(self) -> str:
        return f"{self.run_date}: {self.quantity} × {self.product.sku}"

    def clean(self) -> None:
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({"quantity": "Production quantity must be greater than zero."})
        if self.product_id and self.quantity:
            self._check_stock_available()

    def _check_stock_available(self) -> None:
        shortfalls = []
        for line in self.product.bom_lines.select_related("raw_material").all():
            need = line.quantity * self.quantity
            have = line.raw_material.current_stock
            if need > have:
                short = need - have
                shortfalls.append(
                    f"{line.raw_material.name} ({line.raw_material.sku}): "
                    f"need {need}, have {have}, short by {short}"
                )
        if shortfalls:
            raise InsufficientStockError(
                {"quantity": ["Not enough raw materials. " + "; ".join(shortfalls)]}
            )

    def save(self, *args, **kwargs) -> None:
        is_new = self._state.adding
        if not is_new:
            raise ValidationError(
                "Production runs are immutable once saved. "
                "Record a StockMovement.ADJUSTMENT to correct stock."
            )
        # Re-check stock before mutation (defence-in-depth: clean() is not always
        # called, e.g. raw .objects.create()).
        self._check_stock_available()

        with transaction.atomic():
            super().save(*args, **kwargs)
            for line in self.product.bom_lines.select_related("raw_material").all():
                consumed = line.quantity * self.quantity
                material = line.raw_material
                material.current_stock = material.current_stock - consumed
                material.save(update_fields=["current_stock", "updated_at"])
                StockMovement.objects.create(
                    raw_material=material,
                    delta=-consumed,
                    reason="PRODUCTION_CONSUMED",
                    related_object_type="ProductionRun",
                    related_object_id=self.pk,
                    note=f"Consumed by production of {self.quantity} × {self.product.sku}",
                    created_by=self.created_by,
                )

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Production runs cannot be deleted. "
            "Record a StockMovement.ADJUSTMENT to correct stock."
        )
