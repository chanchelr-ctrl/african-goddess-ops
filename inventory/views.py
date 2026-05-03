"""
Views for the operations dashboard. Day 2 builds these out fully; Day 1
ships placeholders so the URL surface is wired and `start.ps1` opens to
something meaningful (rather than a 404).
"""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.db.models import Sum, F

from .models import (
    Product,
    ProductionRun,
    PurchaseOrder,
    RawMaterial,
)


@login_required
def dashboard(request):
    """Operations home. Tile counts + low-stock list. HTMX-enhanced on Day 2."""
    low_stock = RawMaterial.objects.filter(
        is_active=True,
        current_stock__lte=F("reorder_point"),
    ).select_related("preferred_supplier").order_by("name")

    open_pos = (
        PurchaseOrder.objects
        .filter(status__in=("DRAFT", "SENT"))
        .select_related("supplier")
        .order_by("-created_at")[:10]
    )

    recent_runs = (
        ProductionRun.objects
        .select_related("product")
        .order_by("-run_date", "-created_at")[:10]
    )

    stock_value_qs = RawMaterial.objects.filter(is_active=True).aggregate(
        total=Sum(F("current_stock") * F("last_paid_unit_cost"))
    )
    stock_value = stock_value_qs["total"] or 0

    products_count = Product.objects.filter(is_active=True).count()
    materials_count = RawMaterial.objects.filter(is_active=True).count()

    return render(
        request,
        "inventory/dashboard.html",
        {
            "low_stock": low_stock,
            "low_stock_count": len(low_stock),
            "open_pos": open_pos,
            "open_pos_count": open_pos.count(),
            "recent_runs": recent_runs,
            "stock_value": stock_value,
            "products_count": products_count,
            "materials_count": materials_count,
        },
    )


def healthz(request):
    """Liveness probe for start.ps1."""
    return JsonResponse({"status": "ok"})
