"""
Data model for African Goddess inventory & operations — v0.2.

Schema reflects the actual client data shape:
- Two brand families: African Goddess (AGC) + Sugar Bush (SBR — a bikini brand
  AG produces adornments for as a channel partner).
- Colour-combination variants (e.g. "SBR01 - Tangerine & Orange",
  "AGC - Aqua Flow") — each variant of the same product type has a different BOM.
- Pack-aware purchasing (suppliers ship in packs; pack_size + last_paid_pack_cost
  are first-class).
- Project model for "build N of variant X (and M of variant Y) as one job".
- Sale model for manual sales tracking (WooCommerce sync deferred).

Design principles (carried forward from v0.1):
- Decimal precision = 4 places everywhere quantities or unit-costs appear
- StockMovement is append-only; current_stock denormalised but reconcilable
- Side-effects (BOM deduction, PO receive) live in model.save() with explicit
  transactions; production runs are immutable post-save
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
# Brand
# ---------------------------------------------------------------------------


class Brand(models.Model):
    """A trading-name / channel under which products are sold.
    e.g. 'African Goddess' (AGC), 'Sugar Bush' (SBR).
    """

    code = models.CharField(max_length=8, unique=True, db_index=True)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------


class Supplier(models.Model):
    name = models.CharField(max_length=200, unique=True)
    contact_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    website = models.URLField(blank=True)
    typical_lead_time_days = models.PositiveIntegerField(null=True, blank=True)
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
    internal_id_code = models.CharField(max_length=32, blank=True, db_index=True,
                                        help_text="Client-internal short code (e.g. 10D, 11D).")
    alternative_id_code = models.CharField(max_length=64, blank=True,
                                           help_text="Alternative supplier SKU.")
    name = models.CharField(max_length=255)

    # Descriptive metadata (from the spreadsheet)
    item_size = models.CharField(max_length=64, blank=True)
    colour = models.CharField(max_length=128, blank=True)
    finish = models.CharField(max_length=128, blank=True)
    shape = models.CharField(max_length=128, blank=True)
    description = models.TextField(blank=True)
    sub_brand = models.CharField(max_length=64, blank=True,
                                 help_text="Sub-brand of supplier (e.g. EFREY, SUPERDANT).")

    unit = models.CharField(max_length=16, choices=UNIT_CHOICES, default="piece")

    # Stock
    current_stock = models.DecimalField(max_digits=14, decimal_places=4, default=ZERO)
    reorder_point = models.DecimalField(max_digits=14, decimal_places=4, default=ZERO)
    reorder_quantity = models.DecimalField(max_digits=14, decimal_places=4, default=ZERO)

    # Pack-aware purchasing
    pack_size = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("1"),
                                    help_text="Units per supplier pack.")
    last_paid_pack_cost = models.DecimalField(max_digits=12, decimal_places=4, default=ZERO,
                                              help_text="Most recent pack cost (ZAR).")
    import_duties_per_pack = models.DecimalField(max_digits=12, decimal_places=4, default=ZERO)
    last_paid_unit_cost = models.DecimalField(
        max_digits=12, decimal_places=4, default=ZERO,
        help_text="Effective unit cost = (pack_cost + duties) / pack_size. Used for COGS.",
    )

    preferred_supplier = models.ForeignKey(
        Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="materials",
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

    @property
    def packs_to_purchase(self) -> Decimal:
        """Whole packs needed to bring stock back to reorder_point + reorder_quantity."""
        if self.pack_size <= 0:
            return ZERO
        target = self.reorder_point + self.reorder_quantity
        deficit = target - self.current_stock
        if deficit <= 0:
            return ZERO
        # Round up to the nearest whole pack
        from math import ceil
        return Decimal(int(ceil(float(deficit) / float(self.pack_size))))

    def recompute_unit_cost(self) -> None:
        """Derive last_paid_unit_cost from pack cost + duties / pack size. Caller saves."""
        if self.pack_size and self.pack_size > 0:
            total = self.last_paid_pack_cost + self.import_duties_per_pack
            self.last_paid_unit_cost = (total / self.pack_size).quantize(Decimal("0.0001"))


# ---------------------------------------------------------------------------
# Products and variants
# ---------------------------------------------------------------------------


class Product(models.Model):
    """A product 'type' — Earrings, Double Necklace, Back Piece, etc.
    The actual sellable SKU is a ProductVariant = (Product, Variant)."""

    PILLAR_CHOICES = [
        ("BODY_ADORNMENTS", "Body Adornments"),
        ("SACRED_TOOLS", "Sacred Tools"),
        ("BAMBOO_CLOTHING", "Bamboo Clothing"),
        ("OTHER", "Other"),
    ]

    code = models.CharField(max_length=32, unique=True, db_index=True,
                            help_text="Code from the spreadsheet, e.g. SBR00EARR.")
    name = models.CharField(max_length=255)
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="products")
    pillar = models.CharField(max_length=24, choices=PILLAR_CHOICES, default="BODY_ADORNMENTS")
    default_retail_price_zar = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("brand", "name")

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class Variant(models.Model):
    """A colour-combination / palette / collection.
    e.g. 'SBR01 - Tangerine & Orange', 'AGC - Aqua Flow'.
    A Variant belongs to a Brand and is paired with Products to form ProductVariants.
    """

    code = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="variants")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("brand", "code")

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class ProductVariant(models.Model):
    """The actual sellable SKU = (Product type) x (Variant colour-combo).
    Carries its own BOM (via BomLine) and its own retail price (optional override).
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    variant = models.ForeignKey(Variant, on_delete=models.CASCADE, related_name="product_variants")
    sku = models.CharField(max_length=64, unique=True, db_index=True,
                           help_text="Sellable SKU, e.g. SBR01-EARR.")
    retail_price_zar = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Override of Product.default_retail_price_zar. Blank = use product default.",
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("product", "variant")
        unique_together = (("product", "variant"),)

    def __str__(self) -> str:
        return f"{self.sku}"

    @property
    def effective_retail_price_zar(self) -> Decimal:
        return self.retail_price_zar if self.retail_price_zar is not None else self.product.default_retail_price_zar

    @property
    def material_cost(self) -> Decimal:
        total = ZERO
        for line in self.bom_lines.select_related("raw_material").all():
            total += line.quantity * line.raw_material.last_paid_unit_cost
        return total.quantize(Decimal("0.0001"))

    @property
    def material_cost_display(self) -> Decimal:
        return self.material_cost.quantize(Decimal("0.01"))

    @property
    def gross_margin_zar(self) -> Decimal:
        return (self.effective_retail_price_zar - self.material_cost).quantize(Decimal("0.01"))

    @property
    def gross_margin_pct(self) -> Optional[Decimal]:
        retail = self.effective_retail_price_zar
        if retail == 0:
            return None
        return ((retail - self.material_cost) / retail * 100).quantize(Decimal("0.01"))

    @property
    def can_make_units(self) -> int:
        lines = list(self.bom_lines.select_related("raw_material").all())
        if not lines:
            return 0
        possible_runs = []
        for line in lines:
            if line.quantity <= 0:
                continue
            possible_runs.append(int(line.raw_material.current_stock // line.quantity))
        return max(min(possible_runs) if possible_runs else 0, 0)

    def material_shortfalls(self, qty: int) -> list[dict]:
        """Return [{material, need, have, short}, ...] for any material short for `qty` units.
        Empty list = sufficient stock."""
        out = []
        for line in self.bom_lines.select_related("raw_material").all():
            need = line.quantity * qty
            have = line.raw_material.current_stock
            if need > have:
                out.append({
                    "material": line.raw_material,
                    "need": need,
                    "have": have,
                    "short": need - have,
                })
        return out


class BomLine(models.Model):
    """A single ingredient in a ProductVariant's bill of materials."""

    product_variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE,
                                        related_name="bom_lines")
    raw_material = models.ForeignKey(RawMaterial, on_delete=models.PROTECT,
                                     related_name="bom_lines")
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = (("product_variant", "raw_material"),)
        ordering = ("product_variant", "raw_material")

    def __str__(self) -> str:
        return f"{self.product_variant.sku}: {self.quantity} x {self.raw_material.sku}"

    def clean(self) -> None:
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({"quantity": "BOM quantity must be greater than zero."})


# ---------------------------------------------------------------------------
# Stock movements (audit log)
# ---------------------------------------------------------------------------


class StockMovement(models.Model):
    REASON_CHOICES = [
        ("PO_RECEIVED", "Purchase order received"),
        ("PRODUCTION_CONSUMED", "Production run consumed"),
        ("ADJUSTMENT", "Manual adjustment"),
        ("INITIAL_STOCK", "Initial / opening stock"),
    ]

    raw_material = models.ForeignKey(RawMaterial, on_delete=models.PROTECT, related_name="movements")
    delta = models.DecimalField(max_digits=14, decimal_places=4)
    reason = models.CharField(max_length=32, choices=REASON_CHOICES)
    related_object_type = models.CharField(max_length=64, blank=True)
    related_object_id = models.PositiveBigIntegerField(null=True, blank=True)
    note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="stock_movements",
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

    # Temu integration
    temu_order_id = models.CharField(max_length=64, blank=True, db_index=True,
                                     help_text="Temu's own order ID, when linked.")
    tracking_number = models.CharField(max_length=64, blank=True)

    ordered_at = models.DateTimeField(null=True, blank=True,
                                      help_text="Set when status moves DRAFT -> SENT.")
    expected_date = models.DateField(null=True, blank=True)
    received_date = models.DateField(null=True, blank=True)

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.reference or 'PO?'} - {self.supplier.name} [{self.get_status_display()}]"

    @property
    def total_cost(self) -> Decimal:
        total = ZERO
        for line in self.lines.all():
            total += line.line_total
        return total.quantize(Decimal("0.01"))

    def save(self, *args, **kwargs) -> None:
        if not self.reference:
            self.reference = self._generate_reference()

        is_new = self._state.adding
        prior_status: Optional[str] = None
        if not is_new:
            prior_status = type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()

        if self.status == "SENT" and self.ordered_at is None:
            self.ordered_at = timezone.now()
        if self.status == "RECEIVED" and self.received_date is None:
            self.received_date = timezone.localdate()

        with transaction.atomic():
            super().save(*args, **kwargs)
            if self.status == "RECEIVED" and prior_status != "RECEIVED":
                self._apply_receipt_to_stock()

    def _generate_reference(self) -> str:
        prefix = "PO-" + timezone.localdate().strftime("%Y%m%d")
        existing = type(self).objects.filter(reference__startswith=prefix).count()
        return f"{prefix}-{existing + 1:03d}"

    def _apply_receipt_to_stock(self) -> None:
        for line in self.lines.select_related("raw_material").all():
            qty_units = line.units_total
            if qty_units <= 0:
                continue
            material = line.raw_material
            material.current_stock = material.current_stock + qty_units
            # Update pack-cost + duties + recompute unit cost
            if line.unit_cost > 0:
                material.last_paid_unit_cost = line.unit_cost
                if line.pack_size > 0:
                    material.pack_size = line.pack_size
                    material.last_paid_pack_cost = (line.unit_cost * line.pack_size).quantize(Decimal("0.0001"))
            material.save(update_fields=["current_stock", "last_paid_unit_cost",
                                         "pack_size", "last_paid_pack_cost", "updated_at"])
            StockMovement.objects.create(
                raw_material=material,
                delta=qty_units,
                reason="PO_RECEIVED",
                related_object_type="PurchaseOrder",
                related_object_id=self.pk,
                note=f"Received on PO {self.reference} from {self.supplier.name}",
            )


class PurchaseOrderLine(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    raw_material = models.ForeignKey(RawMaterial, on_delete=models.PROTECT, related_name="po_lines")
    pack_size = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("1"),
                                    help_text="Units per pack ordered.")
    pack_count = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("1"),
                                     help_text="Number of packs ordered.")
    unit_cost = models.DecimalField(max_digits=12, decimal_places=4, default=ZERO,
                                    help_text="Effective unit cost (ZAR).")

    class Meta:
        ordering = ("purchase_order", "raw_material")

    def __str__(self) -> str:
        return f"{self.raw_material.sku}: {self.pack_count} x {self.pack_size} units"

    @property
    def units_total(self) -> Decimal:
        return (self.pack_size * self.pack_count).quantize(Decimal("0.0001"))

    @property
    def line_total(self) -> Decimal:
        return (self.units_total * self.unit_cost).quantize(Decimal("0.01"))

    def clean(self) -> None:
        if self.pack_size is not None and self.pack_size <= 0:
            raise ValidationError({"pack_size": "pack_size must be > 0."})
        if self.pack_count is not None and self.pack_count <= 0:
            raise ValidationError({"pack_count": "pack_count must be > 0."})
        if self.unit_cost is not None and self.unit_cost < 0:
            raise ValidationError({"unit_cost": "unit_cost cannot be negative."})


# ---------------------------------------------------------------------------
# Projects (multi-product builds) + Production Runs
# ---------------------------------------------------------------------------


class Project(models.Model):
    """A 'build' job — make N of variant X (and M of variant Y) as one job.
    Lifecycle: PLANNED -> IN_PROGRESS -> COMPLETED (or CANCELLED).
    """

    STATUS_CHOICES = [
        ("PLANNED", "Planned"),
        ("IN_PROGRESS", "In progress"),
        ("COMPLETED", "Completed"),
        ("CANCELLED", "Cancelled"),
    ]

    name = models.CharField(max_length=200)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="PLANNED", db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="projects",
    )

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.name} [{self.get_status_display()}]"

    @property
    def total_planned_units(self) -> int:
        return sum(item.quantity_planned for item in self.items.all())

    @property
    def total_made_units(self) -> int:
        return sum(item.quantity_made for item in self.items.all())

    @property
    def is_complete(self) -> bool:
        return self.total_made_units >= self.total_planned_units and self.total_planned_units > 0

    def aggregate_shortfalls(self) -> list[dict]:
        """Across all items still pending, what raw materials are short?"""
        from collections import defaultdict
        need_per_material: dict[int, dict] = defaultdict(lambda: {"material": None, "need": ZERO})
        for item in self.items.select_related("product_variant").all():
            remaining = item.quantity_planned - item.quantity_made
            if remaining <= 0:
                continue
            for line in item.product_variant.bom_lines.select_related("raw_material").all():
                entry = need_per_material[line.raw_material_id]
                entry["material"] = line.raw_material
                entry["need"] += line.quantity * remaining
        out = []
        for entry in need_per_material.values():
            material = entry["material"]
            need = entry["need"]
            have = material.current_stock
            if need > have:
                out.append({"material": material, "need": need, "have": have, "short": need - have})
        return out


class ProjectItem(models.Model):
    """A line within a project: 'make N of this ProductVariant'."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="items")
    product_variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT,
                                        related_name="project_items")
    quantity_planned = models.PositiveIntegerField()
    quantity_made = models.PositiveIntegerField(default=0)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("project", "product_variant")

    def __str__(self) -> str:
        return f"{self.project.name}: {self.quantity_planned} x {self.product_variant.sku}"

    @property
    def remaining(self) -> int:
        return max(self.quantity_planned - self.quantity_made, 0)


class InsufficientStockError(ValidationError):
    pass


class ProductionRun(models.Model):
    """Tersia recording 'I made N units of variant X today'.

    On save: deduct BOM x quantity, write StockMovement records, optionally
    increment ProjectItem.quantity_made.
    Production runs are immutable once saved.
    """

    product_variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT,
                                        related_name="production_runs")
    quantity = models.PositiveIntegerField()
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="production_runs")
    project_item = models.ForeignKey(ProjectItem, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="production_runs")
    run_date = models.DateField(default=timezone.localdate)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="production_runs",
    )

    class Meta:
        ordering = ("-run_date", "-created_at")

    def __str__(self) -> str:
        return f"{self.run_date}: {self.quantity} x {self.product_variant.sku}"

    def clean(self) -> None:
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({"quantity": "Production quantity must be greater than zero."})
        if self.product_variant_id and self.quantity:
            self._check_stock_available()

    def _check_stock_available(self) -> None:
        shortfalls = self.product_variant.material_shortfalls(self.quantity)
        if shortfalls:
            msg_parts = [
                f"{s['material'].name} ({s['material'].sku}): "
                f"need {s['need']}, have {s['have']}, short by {s['short']}"
                for s in shortfalls
            ]
            raise InsufficientStockError(
                {"quantity": ["Not enough raw materials. " + "; ".join(msg_parts)]}
            )

    def save(self, *args, **kwargs) -> None:
        is_new = self._state.adding
        if not is_new:
            raise ValidationError(
                "Production runs are immutable once saved. "
                "Record a StockMovement.ADJUSTMENT to correct stock."
            )
        self._check_stock_available()

        with transaction.atomic():
            super().save(*args, **kwargs)
            for line in self.product_variant.bom_lines.select_related("raw_material").all():
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
                    note=f"Consumed by production of {self.quantity} x {self.product_variant.sku}",
                    created_by=self.created_by,
                )
            # Increment ProjectItem.quantity_made if linked
            if self.project_item_id:
                ProjectItem.objects.filter(pk=self.project_item_id).update(
                    quantity_made=models.F("quantity_made") + self.quantity
                )

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Production runs cannot be deleted. "
            "Record a StockMovement.ADJUSTMENT to correct stock."
        )


# ---------------------------------------------------------------------------
# Sales (lightweight manual tracking)
# ---------------------------------------------------------------------------


class DataChangeLog(models.Model):
    """Append-only audit log of edits to master/spec data. Distinct from
    StockMovement (which logs only stock deltas). Each row records one
    field-level change to a tracked model.
    """

    ACTION_CHOICES = [
        ("CREATE", "Created"),
        ("UPDATE", "Updated"),
        ("DELETE", "Deleted"),
    ]

    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="data_change_logs",
    )
    action = models.CharField(max_length=16, choices=ACTION_CHOICES, db_index=True)
    model_name = models.CharField(max_length=64, db_index=True)
    object_pk = models.PositiveBigIntegerField(null=True, blank=True)
    sku = models.CharField(max_length=128, blank=True, db_index=True,
                           help_text="SKU/code of the changed object, if applicable.")
    field = models.CharField(max_length=64, blank=True)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ("-timestamp",)
        indexes = [
            models.Index(fields=["model_name", "object_pk"]),
            models.Index(fields=["sku", "-timestamp"]),
        ]

    def __str__(self) -> str:
        who = self.user.username if self.user else "system"
        return (f"{self.timestamp:%Y-%m-%d %H:%M} {who} "
                f"{self.action} {self.model_name}.{self.field or '*'} "
                f"({self.sku or self.object_pk})")


