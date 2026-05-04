"""
Django admin for African Goddess inventory & operations (v0.2).

Uses django-unfold's ModelAdmin/TabularInline for the themed visual treatment.
"""

from django.contrib import admin
from django.utils.html import format_html

from unfold.admin import ModelAdmin, TabularInline

from .models import (
    BomLine,
    Brand,
    ProductionRun,
    Product,
    ProductVariant,
    Project,
    ProjectItem,
    PurchaseOrder,
    PurchaseOrderLine,
    RawMaterial,
    Sale,
    StockMovement,
    Supplier,
    Variant,
)


# ---------------------------------------------------------------------------
# Brand
# ---------------------------------------------------------------------------


@admin.register(Brand)
class BrandAdmin(ModelAdmin):
    list_display = ("code", "name", "is_active", "products_count", "variants_count")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "description")
    list_editable = ("is_active",)

    @admin.display(description="Products")
    def products_count(self, obj):
        return obj.products.count()

    @admin.display(description="Variants")
    def variants_count(self, obj):
        return obj.variants.count()


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------


@admin.register(Supplier)
class SupplierAdmin(ModelAdmin):
    list_display = ("name", "contact_name", "email", "phone", "typical_lead_time_days", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "contact_name", "email")
    list_editable = ("is_active",)


# ---------------------------------------------------------------------------
# Raw materials
# ---------------------------------------------------------------------------


@admin.register(RawMaterial)
class RawMaterialAdmin(ModelAdmin):
    list_display = (
        "sku", "internal_id_code", "name", "colour", "item_size", "unit",
        "current_stock", "reorder_point", "needs_reorder_badge",
        "pack_size", "last_paid_unit_cost", "stock_value_zar_display",
        "preferred_supplier", "is_active",
    )
    list_filter = ("is_active", "unit", "preferred_supplier", "sub_brand")
    search_fields = ("sku", "internal_id_code", "alternative_id_code", "name",
                     "description", "colour", "shape", "finish")
    list_select_related = ("preferred_supplier",)
    autocomplete_fields = ("preferred_supplier",)
    list_editable = ("reorder_point",)
    list_per_page = 50

    fieldsets = (
        (None, {"fields": ("sku", "internal_id_code", "alternative_id_code",
                           "name", "is_active")}),
        ("Description", {"fields": ("item_size", "colour", "finish", "shape",
                                    "description", "sub_brand")}),
        ("Stock", {"fields": ("unit", "current_stock", "reorder_point", "reorder_quantity")}),
        ("Pricing & supplier", {
            "fields": ("preferred_supplier", "pack_size", "last_paid_pack_cost",
                       "import_duties_per_pack", "last_paid_unit_cost"),
        }),
        ("Notes", {"fields": ("notes",)}),
    )

    @admin.display(description="Reorder?")
    def needs_reorder_badge(self, obj):
        if obj.needs_reorder:
            return format_html(
                '<span style="color:#fff;background:#c0392b;padding:2px 8px;'
                'border-radius:4px;font-weight:600;">REORDER</span>'
            )
        return format_html('<span style="color:#27ae60;">OK</span>')

    @admin.display(description="Stock value")
    def stock_value_zar_display(self, obj):
        return f"R {obj.stock_value_zar:,.2f}"


# ---------------------------------------------------------------------------
# Variants
# ---------------------------------------------------------------------------


@admin.register(Variant)
class VariantAdmin(ModelAdmin):
    list_display = ("code", "name", "brand", "is_active", "product_variants_count")
    list_filter = ("brand", "is_active")
    search_fields = ("code", "name", "description")
    autocomplete_fields = ("brand",)
    list_editable = ("is_active",)

    @admin.display(description="Sellable SKUs")
    def product_variants_count(self, obj):
        return obj.product_variants.count()


# ---------------------------------------------------------------------------
# Products + ProductVariants
# ---------------------------------------------------------------------------


class ProductVariantInline(TabularInline):
    model = ProductVariant
    extra = 0
    autocomplete_fields = ("variant",)
    fields = ("sku", "variant", "retail_price_zar", "is_active")
    show_change_link = True


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ("code", "name", "brand", "pillar", "default_retail_price_zar",
                    "variants_count", "is_active")
    list_filter = ("brand", "pillar", "is_active")
    search_fields = ("code", "name", "notes")
    autocomplete_fields = ("brand",)
    list_editable = ("default_retail_price_zar",)
    inlines = (ProductVariantInline,)

    fieldsets = (
        (None, {"fields": ("code", "name", "brand", "pillar", "is_active")}),
        ("Default pricing", {"fields": ("default_retail_price_zar",)}),
        ("Notes", {"fields": ("notes",)}),
    )

    @admin.display(description="Variants")
    def variants_count(self, obj):
        return obj.variants.count()


class BomLineInline(TabularInline):
    model = BomLine
    extra = 1
    autocomplete_fields = ("raw_material",)
    fields = ("raw_material", "quantity", "notes")


@admin.register(ProductVariant)
class ProductVariantAdmin(ModelAdmin):
    list_display = ("sku", "product", "variant", "effective_price_display",
                    "material_cost_admin", "gross_margin_pct_admin",
                    "can_make_units_admin", "is_active")
    list_filter = ("product__brand", "product__pillar", "is_active")
    search_fields = ("sku", "product__name", "variant__name", "notes")
    autocomplete_fields = ("product", "variant")
    list_select_related = ("product", "variant", "product__brand")
    inlines = (BomLineInline,)

    fieldsets = (
        (None, {"fields": ("sku", "product", "variant", "is_active")}),
        ("Pricing", {"fields": ("retail_price_zar",),
                     "description": "Optional override of the parent product's default price."}),
        ("Notes", {"fields": ("notes",)}),
    )

    @admin.display(description="Retail")
    def effective_price_display(self, obj):
        return f"R {obj.effective_retail_price_zar:,.2f}"

    @admin.display(description="Material cost")
    def material_cost_admin(self, obj):
        return f"R {obj.material_cost_display:,.2f}"

    @admin.display(description="Margin %")
    def gross_margin_pct_admin(self, obj):
        pct = obj.gross_margin_pct
        return "—" if pct is None else f"{pct}%"

    @admin.display(description="Can make")
    def can_make_units_admin(self, obj):
        return f"{obj.can_make_units}"


@admin.register(BomLine)
class BomLineAdmin(ModelAdmin):
    list_display = ("product_variant", "raw_material", "quantity")
    list_filter = ("product_variant__product__brand", "product_variant__product__pillar")
    search_fields = ("product_variant__sku", "raw_material__sku", "raw_material__name")
    autocomplete_fields = ("product_variant", "raw_material")


# ---------------------------------------------------------------------------
# Purchase orders
# ---------------------------------------------------------------------------


class PurchaseOrderLineInline(TabularInline):
    model = PurchaseOrderLine
    extra = 1
    autocomplete_fields = ("raw_material",)
    fields = ("raw_material", "pack_size", "pack_count", "unit_cost",
              "units_total_admin", "line_total_admin")
    readonly_fields = ("units_total_admin", "line_total_admin")

    @admin.display(description="Units total")
    def units_total_admin(self, obj):
        return f"{obj.units_total}" if obj.pk else "—"

    @admin.display(description="Line total")
    def line_total_admin(self, obj):
        return f"R {obj.line_total:,.2f}" if obj.pk else "—"


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(ModelAdmin):
    list_display = ("reference", "supplier", "status", "expected_date",
                    "received_date", "total_cost_admin", "temu_order_id", "created_at")
    list_filter = ("status", "supplier")
    search_fields = ("reference", "supplier__name", "notes", "temu_order_id", "tracking_number")
    autocomplete_fields = ("supplier",)
    readonly_fields = ("reference", "ordered_at", "created_at", "updated_at")
    inlines = (PurchaseOrderLineInline,)
    date_hierarchy = "created_at"

    fieldsets = (
        (None, {"fields": ("reference", "supplier", "status")}),
        ("Temu integration", {"fields": ("temu_order_id", "tracking_number"),
                              "classes": ("collapse",)}),
        ("Dates", {"fields": ("ordered_at", "expected_date", "received_date")}),
        ("Notes", {"fields": ("notes",)}),
        ("Audit", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Total cost")
    def total_cost_admin(self, obj):
        return f"R {obj.total_cost:,.2f}"


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


class ProjectItemInline(TabularInline):
    model = ProjectItem
    extra = 1
    autocomplete_fields = ("product_variant",)
    fields = ("product_variant", "quantity_planned", "quantity_made", "notes")
    readonly_fields = ("quantity_made",)


@admin.register(Project)
class ProjectAdmin(ModelAdmin):
    list_display = ("name", "status", "total_planned_units", "total_made_units",
                    "started_at", "completed_at", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "notes")
    readonly_fields = ("created_at", "updated_at", "created_by")
    inlines = (ProjectItemInline,)

    fieldsets = (
        (None, {"fields": ("name", "status")}),
        ("Lifecycle", {"fields": ("started_at", "completed_at")}),
        ("Notes", {"fields": ("notes",)}),
        ("Audit", {"fields": ("created_at", "updated_at", "created_by"), "classes": ("collapse",)}),
    )

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ProjectItem)
class ProjectItemAdmin(ModelAdmin):
    list_display = ("project", "product_variant", "quantity_planned", "quantity_made", "remaining")
    list_filter = ("project__status",)
    search_fields = ("project__name", "product_variant__sku")
    autocomplete_fields = ("project", "product_variant")


# ---------------------------------------------------------------------------
# Production runs
# ---------------------------------------------------------------------------


@admin.register(ProductionRun)
class ProductionRunAdmin(ModelAdmin):
    list_display = ("run_date", "product_variant", "quantity", "project",
                    "created_at", "created_by")
    list_filter = ("product_variant__product__pillar", "product_variant__product__brand", "run_date")
    search_fields = ("product_variant__sku", "product_variant__product__name",
                     "project__name", "notes")
    autocomplete_fields = ("product_variant", "project", "project_item")
    readonly_fields = ("created_at", "created_by")
    date_hierarchy = "run_date"

    fieldsets = (
        (None, {"fields": ("product_variant", "quantity", "run_date")}),
        ("Project link", {"fields": ("project", "project_item")}),
        ("Notes", {"fields": ("notes",)}),
        ("Audit", {"fields": ("created_at", "created_by"), "classes": ("collapse",)}),
    )

    def has_change_permission(self, request, obj=None):
        return False if obj is not None else super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


# ---------------------------------------------------------------------------
# Sales
# ---------------------------------------------------------------------------


@admin.register(Sale)
class SaleAdmin(ModelAdmin):
    list_display = ("sale_date", "product_variant", "quantity", "unit_price_zar",
                    "total_zar_admin", "channel", "customer_name", "created_by")
    list_filter = ("channel", "sale_date", "product_variant__product__brand")
    search_fields = ("product_variant__sku", "customer_name", "notes")
    autocomplete_fields = ("product_variant",)
    readonly_fields = ("created_at", "created_by")
    date_hierarchy = "sale_date"

    fieldsets = (
        (None, {"fields": ("sale_date", "product_variant", "quantity",
                           "unit_price_zar", "channel")}),
        ("Customer", {"fields": ("customer_name",)}),
        ("Notes", {"fields": ("notes",)}),
        ("Audit", {"fields": ("created_at", "created_by"), "classes": ("collapse",)}),
    )

    @admin.display(description="Total")
    def total_zar_admin(self, obj):
        return f"R {obj.total_zar:,.2f}"

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
            material = obj.raw_material
            material.current_stock = material.current_stock + obj.delta
            material.save(update_fields=["current_stock", "updated_at"])
        super().save_model(request, obj, form, change)
