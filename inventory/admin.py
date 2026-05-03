"""
Django admin for African Goddess inventory & operations.

This is Tersia's primary CRUD interface. Optimised for at-a-glance
operational signal: needs-reorder badges, stock value, what-can-I-make,
and one-line summaries on every list page.

Uses django-unfold's ModelAdmin/TabularInline base classes for the
themed visual treatment (matches the brand palette configured in
settings.UNFOLD).
"""

from django.contrib import admin
from django.db.models import Sum, F
from django.utils.html import format_html

from unfold.admin import ModelAdmin, TabularInline

from .models import (
    BomLine,
    ProductionRun,
    Product,
    PurchaseOrder,
    PurchaseOrderLine,
    RawMaterial,
    StockMovement,
    Supplier,
)


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------


@admin.register(Supplier)
class SupplierAdmin(ModelAdmin):
    list_display = ("name", "contact_name", "email", "phone",
                    "typical_lead_time_days", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "contact_name", "email")
    list_editable = ("is_active",)
    fieldsets = (
        (None, {"fields": ("name", "is_active")}),
        ("Contact", {"fields": ("contact_name", "email", "phone", "website")}),
        ("Operations", {"fields": ("typical_lead_time_days", "notes")}),
    )


# ---------------------------------------------------------------------------
# Raw materials
# ---------------------------------------------------------------------------


@admin.register(RawMaterial)
class RawMaterialAdmin(ModelAdmin):
    list_display = (
        "sku", "name", "unit",
        "current_stock", "reorder_point",
        "needs_reorder_badge",
        "last_paid_unit_cost", "stock_value_zar_display",
        "preferred_supplier", "is_active",
    )
    list_filter = ("is_active", "unit", "preferred_supplier")
    search_fields = ("sku", "name", "notes")
    list_select_related = ("preferred_supplier",)
    autocomplete_fields = ("preferred_supplier",)
    list_editable = ("reorder_point",)

    fieldsets = (
        (None, {"fields": ("sku", "name", "unit", "is_active")}),
        ("Stock", {"fields": ("current_stock", "reorder_point", "reorder_quantity")}),
        ("Cost & supplier", {"fields": ("last_paid_unit_cost", "preferred_supplier")}),
        ("Notes", {"fields": ("notes",)}),
    )

    @admin.display(description="Reorder?")
    def needs_reorder_badge(self, obj: RawMaterial) -> str:
        if obj.needs_reorder:
            return format_html(
                '<span style="color:#fff;background:#c0392b;padding:2px 8px;'
                'border-radius:4px;font-weight:600;">REORDER</span>'
            )
        return format_html('<span style="color:#27ae60;">OK</span>')

    @admin.display(description="Stock value", ordering="current_stock")
    def stock_value_zar_display(self, obj: RawMaterial) -> str:
        return f"R {obj.stock_value_zar:,.2f}"


# ---------------------------------------------------------------------------
# Products + BOMs
# ---------------------------------------------------------------------------


class BomLineInline(TabularInline):
    model = BomLine
    extra = 1
    autocomplete_fields = ("raw_material",)
    fields = ("raw_material", "quantity", "notes")


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = (
        "sku", "name", "pillar",
        "retail_price_zar",
        "material_cost_admin", "gross_margin_pct_admin",
        "can_make_units_admin",
        "is_active",
    )
    list_filter = ("pillar", "is_active")
    search_fields = ("sku", "name", "notes")
    list_editable = ("retail_price_zar",)
    inlines = (BomLineInline,)

    fieldsets = (
        (None, {"fields": ("sku", "name", "pillar", "is_active")}),
        ("Pricing", {"fields": ("retail_price_zar",)}),
        ("Notes", {"fields": ("notes",)}),
    )

    @admin.display(description="Material cost")
    def material_cost_admin(self, obj: Product) -> str:
        return f"R {obj.material_cost_display:,.2f}"

    @admin.display(description="Margin %")
    def gross_margin_pct_admin(self, obj: Product) -> str:
        pct = obj.gross_margin_pct
        if pct is None:
            return "—"
        return f"{pct}%"

    @admin.display(description="Can make")
    def can_make_units_admin(self, obj: Product) -> str:
        return f"{obj.can_make_units} units"


@admin.register(BomLine)
class BomLineAdmin(ModelAdmin):
    list_display = ("product", "raw_material", "quantity")
    list_filter = ("product__pillar",)
    search_fields = ("product__sku", "product__name", "raw_material__sku", "raw_material__name")
    autocomplete_fields = ("product", "raw_material")


# ---------------------------------------------------------------------------
# Purchase orders
# ---------------------------------------------------------------------------


class PurchaseOrderLineInline(TabularInline):
    model = PurchaseOrderLine
    extra = 1
    autocomplete_fields = ("raw_material",)
    fields = ("raw_material", "quantity", "unit_cost", "line_total_admin")
    readonly_fields = ("line_total_admin",)

    @admin.display(description="Line total")
    def line_total_admin(self, obj: PurchaseOrderLine) -> str:
        if obj.pk:
            return f"R {obj.line_total:,.2f}"
        return "—"


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(ModelAdmin):
    list_display = ("reference", "supplier", "status", "expected_date",
                    "received_date", "total_cost_admin", "created_at")
    list_filter = ("status", "supplier")
    search_fields = ("reference", "supplier__name", "notes")
    autocomplete_fields = ("supplier",)
    readonly_fields = ("reference", "created_at", "updated_at")
    inlines = (PurchaseOrderLineInline,)
    date_hierarchy = "created_at"

    fieldsets = (
        (None, {"fields": ("reference", "supplier", "status")}),
        ("Dates", {"fields": ("expected_date", "received_date")}),
        ("Notes", {"fields": ("notes",)}),
        ("Audit", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Total cost", ordering="reference")
    def total_cost_admin(self, obj: PurchaseOrder) -> str:
        return f"R {obj.total_cost:,.2f}"


# ---------------------------------------------------------------------------
# Production runs
# ---------------------------------------------------------------------------


@admin.register(ProductionRun)
class ProductionRunAdmin(ModelAdmin):
    list_display = ("run_date", "product", "quantity", "created_at", "created_by")
    list_filter = ("product__pillar", "run_date")
    search_fields = ("product__sku", "product__name", "notes")
    autocomplete_fields = ("product",)
    readonly_fields = ("created_at", "created_by")
    date_hierarchy = "run_date"

    fieldsets = (
        (None, {"fields": ("product", "quantity", "run_date")}),
        ("Notes", {"fields": ("notes",)}),
        ("Audit", {"fields": ("created_at", "created_by"), "classes": ("collapse",)}),
    )

    def has_change_permission(self, request, obj=None):
        # Production runs are immutable once saved.
        return False if obj is not None else super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


# ---------------------------------------------------------------------------
# Stock movements (read-mostly audit log)
# ---------------------------------------------------------------------------


@admin.register(StockMovement)
class StockMovementAdmin(ModelAdmin):
    list_display = ("created_at", "raw_material", "delta", "reason",
                    "related_object_type", "related_object_id", "created_by")
    list_filter = ("reason", "raw_material", "created_at")
    search_fields = ("raw_material__sku", "raw_material__name", "note")
    autocomplete_fields = ("raw_material",)
    readonly_fields = ("created_at", "created_by", "raw_material", "delta", "reason",
                       "related_object_type", "related_object_id")
    date_hierarchy = "created_at"

    fieldsets = (
        (None, {"fields": ("raw_material", "delta", "reason", "note")}),
        ("Source", {"fields": ("related_object_type", "related_object_id")}),
        ("Audit", {"fields": ("created_at", "created_by")}),
    )

    def has_add_permission(self, request):
        # ADJUSTMENTs are added via a dedicated action below; everything else
        # comes from system events.
        return True

    def has_change_permission(self, request, obj=None):
        return False if obj is not None else super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if not change:
            if not obj.reason:
                obj.reason = "ADJUSTMENT"
            if not obj.created_by_id:
                obj.created_by = request.user
            # Apply the adjustment to the running stock total.
            material = obj.raw_material
            material.current_stock = material.current_stock + obj.delta
            material.save(update_fields=["current_stock", "updated_at"])
        super().save_model(request, obj, form, change)
