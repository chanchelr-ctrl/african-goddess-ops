"""
Views for African Goddess operations (v0.2).

Process-flow nav top-level verbs:
- Dashboard (/)              - operations snapshot
- Build (/build/)            - start a new build / project
- Track (/track/)            - in-flight projects
- Purchase (/purchase/)      - reorder + Temu pipeline
- Sales (/sales/)            - record + log sales

Detail views and HTMX endpoints land under each verb.
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote_plus

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

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
# Helpers
# ---------------------------------------------------------------------------


TEMU_SEARCH_URL_TEMPLATE = "https://www.temu.com/search_result.html?search_key={q}"

# Cap on material-name length appended to the SKU. Keeps the Temu search box
# readable and avoids over-specific queries that return zero results.
TEMU_NAME_MAX = 80


def temu_search_key(material) -> str:
    """Build the Temu search query: '<SKU> <material name>' (name truncated).

    Falls back to just the SKU if the material has no name."""
    name = (getattr(material, "name", "") or "").strip()
    if not name:
        return material.sku
    if len(name) > TEMU_NAME_MAX:
        name = name[:TEMU_NAME_MAX].rstrip()
    return f"{material.sku} {name}"


def temu_search_url(material) -> str:
    """URL for opening Temu pre-loaded with a search for this material."""
    return TEMU_SEARCH_URL_TEMPLATE.format(q=quote_plus(temu_search_key(material)))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@login_required
def dashboard(request):
    """Operations home: KPIs + headline tables."""
    today = timezone.localdate()
    last_30 = today - timedelta(days=30)

    low_stock = RawMaterial.objects.filter(
        is_active=True, current_stock__lte=F("reorder_point"),
    ).select_related("preferred_supplier").order_by("name")

    open_pos = (
        PurchaseOrder.objects.filter(status__in=("DRAFT", "SENT"))
        .select_related("supplier").order_by("-created_at")[:10]
    )

    in_flight_projects = (
        Project.objects.filter(status__in=("PLANNED", "IN_PROGRESS"))
        .order_by("-created_at")[:10]
    )

    recent_runs = (
        ProductionRun.objects.select_related("product_variant", "product_variant__product")
        .order_by("-run_date", "-created_at")[:10]
    )

    sales_30d = Sale.objects.filter(sale_date__gte=last_30)
    sales_30d_total = sales_30d.aggregate(
        total=Sum(F("unit_price_zar") * F("quantity"))
    )["total"] or Decimal("0")
    sales_30d_units = sales_30d.aggregate(units=Sum("quantity"))["units"] or 0

    stock_value_zar = RawMaterial.objects.filter(is_active=True).aggregate(
        total=Sum(F("current_stock") * F("last_paid_unit_cost"))
    )["total"] or Decimal("0")

    on_order_value = PurchaseOrder.objects.filter(status__in=("DRAFT", "SENT")).aggregate(
        total=Sum(F("lines__pack_size") * F("lines__pack_count") * F("lines__unit_cost"))
    )["total"] or Decimal("0")

    return render(request, "inventory/dashboard.html", {
        "low_stock": low_stock,
        "low_stock_count": len(low_stock),
        "open_pos": open_pos,
        "open_pos_count": open_pos.count(),
        "in_flight_projects": in_flight_projects,
        "in_flight_projects_count": in_flight_projects.count(),
        "recent_runs": recent_runs,
        "stock_value_zar": stock_value_zar,
        "on_order_value_zar": on_order_value,
        "sales_30d_total": sales_30d_total,
        "sales_30d_units": sales_30d_units,
        "products_count": Product.objects.filter(is_active=True).count(),
        "variants_count": ProductVariant.objects.filter(is_active=True).count(),
        "materials_count": RawMaterial.objects.filter(is_active=True).count(),
    })


def healthz(request):
    return JsonResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# Build flow
# ---------------------------------------------------------------------------


@login_required
def build_index(request):
    """Entry point for the Build flow.
    Shows two paths: 'Build what we already can' (sufficient stock) and
    'Plan a new build' (any product variant)."""
    can_make = []
    cannot_make = []
    qs = ProductVariant.objects.filter(is_active=True).select_related(
        "product", "variant", "product__brand"
    )
    for pv in qs:
        item = {"pv": pv, "can_make": pv.can_make_units}
        (can_make if pv.can_make_units > 0 else cannot_make).append(item)

    can_make.sort(key=lambda x: -x["can_make"])
    return render(request, "inventory/build_index.html", {
        "can_make": can_make[:50],
        "cannot_make_count": len(cannot_make),
    })


@login_required
def build_check(request):
    """Sufficiency check for a (variant, qty) pair. Returns shortfall list."""
    sku = request.GET.get("variant") or request.POST.get("variant")
    try:
        qty = int(request.GET.get("qty") or request.POST.get("qty") or "1")
    except ValueError:
        qty = 1

    pv = get_object_or_404(ProductVariant, sku=sku) if sku else None
    shortfalls = []
    if pv and qty > 0:
        shortfalls = pv.material_shortfalls(qty)

    variants = ProductVariant.objects.filter(is_active=True).select_related(
        "product", "variant", "product__brand"
    ).order_by("product__brand", "product", "variant")

    return render(request, "inventory/build_check.html", {
        "variants": variants,
        "selected_pv": pv,
        "qty": qty,
        "shortfalls": shortfalls,
        "is_sufficient": pv is not None and qty > 0 and not shortfalls,
    })


@login_required
def build_start_project(request):
    """Convert (variant, qty) into a Project + ProjectItem and redirect to its tracking page."""
    if request.method != "POST":
        return redirect("build")
    sku = request.POST.get("variant")
    try:
        qty = int(request.POST.get("qty") or "1")
    except ValueError:
        qty = 1
    name = request.POST.get("name") or f"Build of {qty} x {sku}"

    pv = get_object_or_404(ProductVariant, sku=sku)
    project = Project.objects.create(
        name=name, status="IN_PROGRESS",
        started_at=timezone.now(), created_by=request.user,
    )
    ProjectItem.objects.create(project=project, product_variant=pv, quantity_planned=qty)
    messages.success(request, f"Started project: {project.name}")
    return redirect("project_detail", pk=project.pk)


# ---------------------------------------------------------------------------
# Track / Projects
# ---------------------------------------------------------------------------


@login_required
def track_index(request):
    """In-flight + recently completed projects."""
    in_flight = Project.objects.filter(
        status__in=("PLANNED", "IN_PROGRESS")
    ).order_by("-created_at")
    recent_completed = Project.objects.filter(
        status="COMPLETED"
    ).order_by("-completed_at")[:20]
    return render(request, "inventory/track_index.html", {
        "in_flight": in_flight,
        "recent_completed": recent_completed,
    })


@login_required
def project_detail(request, pk):
    project = get_object_or_404(Project, pk=pk)
    shortfalls = project.aggregate_shortfalls()
    return render(request, "inventory/project_detail.html", {
        "project": project,
        "items": project.items.select_related("product_variant", "product_variant__product",
                                              "product_variant__variant").all(),
        "shortfalls": shortfalls,
        "runs": project.production_runs.select_related("product_variant").order_by("-run_date"),
    })


@login_required
def project_record_run(request, pk):
    """Record a production run against a project item."""
    project = get_object_or_404(Project, pk=pk)
    if request.method != "POST":
        return redirect("project_detail", pk=pk)
    item_id = request.POST.get("item_id")
    try:
        qty = int(request.POST.get("qty") or "1")
    except ValueError:
        qty = 1
    item = get_object_or_404(ProjectItem, pk=item_id, project=project)
    try:
        ProductionRun.objects.create(
            product_variant=item.product_variant,
            quantity=qty,
            project=project,
            project_item=item,
            run_date=timezone.localdate(),
            created_by=request.user,
        )
        messages.success(request, f"Recorded production: {qty} x {item.product_variant.sku}")
    except Exception as e:
        messages.error(request, f"Could not record run: {e}")
    return redirect("project_detail", pk=pk)


@login_required
def project_complete(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if request.method == "POST":
        project.status = "COMPLETED"
        project.completed_at = timezone.now()
        project.save(update_fields=["status", "completed_at", "updated_at"])
        messages.success(request, f"Project '{project.name}' marked complete.")
    return redirect("project_detail", pk=pk)


# ---------------------------------------------------------------------------
# Purchase flow
# ---------------------------------------------------------------------------


@login_required
def purchase_index(request):
    """Reorder candidates + open POs + Temu helper."""
    low_stock = RawMaterial.objects.filter(
        is_active=True, current_stock__lte=F("reorder_point"),
    ).select_related("preferred_supplier").order_by("name")
    items = []
    for m in low_stock:
        items.append({
            "material": m,
            "packs": m.packs_to_purchase,
            "temu_url": temu_search_url(m),
        })
    open_pos = PurchaseOrder.objects.filter(
        status__in=("DRAFT", "SENT")
    ).select_related("supplier").order_by("-created_at")
    return render(request, "inventory/purchase_index.html", {
        "low_stock_items": items,
        "open_pos": open_pos,
    })


@login_required
def purchase_draft_po(request):
    """Auto-draft a single PO covering all currently-low materials with a
    common preferred supplier (Temu by default)."""
    if request.method != "POST":
        return redirect("purchase")

    supplier_id = request.POST.get("supplier")
    if supplier_id:
        supplier = get_object_or_404(Supplier, pk=supplier_id)
    else:
        supplier, _ = Supplier.objects.get_or_create(name="Temu")

    selected_skus = request.POST.getlist("sku")
    if not selected_skus:
        messages.warning(request, "No materials selected.")
        return redirect("purchase")

    po = PurchaseOrder.objects.create(supplier=supplier, status="DRAFT")
    for sku in selected_skus:
        m = RawMaterial.objects.filter(sku=sku).first()
        if not m:
            continue
        packs = m.packs_to_purchase or Decimal("1")
        PurchaseOrderLine.objects.create(
            purchase_order=po,
            raw_material=m,
            pack_size=m.pack_size or Decimal("1"),
            pack_count=packs,
            unit_cost=m.last_paid_unit_cost,
        )
    messages.success(request, f"Drafted {po.reference} with {len(selected_skus)} line(s).")
    return redirect("po_detail", pk=po.pk)


@login_required
def po_detail(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    lines = []
    for ln in po.lines.select_related("raw_material").all():
        lines.append({
            "line": ln,
            "temu_url": temu_search_url(ln.raw_material),
        })
    return render(request, "inventory/po_detail.html", {"po": po, "lines": lines})


@login_required
def po_mark_sent(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method == "POST":
        po.status = "SENT"
        po.temu_order_id = request.POST.get("temu_order_id", "").strip() or po.temu_order_id
        po.tracking_number = request.POST.get("tracking_number", "").strip() or po.tracking_number
        po.save()
        messages.success(request, f"Marked {po.reference} as sent.")
    return redirect("po_detail", pk=pk)


@login_required
def po_mark_received(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method == "POST":
        po.status = "RECEIVED"
        po.save()
        messages.success(request, f"Received {po.reference}. Stock updated.")
    return redirect("po_detail", pk=pk)


# ---------------------------------------------------------------------------
# Temu managed-browser helper (Playwright subprocess)
# ---------------------------------------------------------------------------


@login_required
def po_open_in_temu(request, pk):
    """Fire `manage.py temu_search --po <ref>` as a detached subprocess so a
    managed Chromium opens with all PO lines pre-searched. Tersia drives the
    cart and checkout in that window."""
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method != "POST":
        return redirect("po_detail", pk=pk)

    project_root = Path(settings.BASE_DIR)
    venv_python = project_root / ".venv" / "Scripts" / "python.exe"
    args = [str(venv_python), "manage.py", "temu_search", "--po", po.reference]
    try:
        # detached so the web request returns immediately
        subprocess.Popen(
            args, cwd=str(project_root),
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) |
                          getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        messages.success(request, "Opening Temu in a managed browser — give it a few seconds.")
    except Exception as e:
        messages.error(request, f"Could not launch managed browser: {e}")
    return redirect("po_detail", pk=pk)


# ---------------------------------------------------------------------------
# Receipt paste-and-parse
# ---------------------------------------------------------------------------


# Regex patterns for Temu order text. Best-effort — Temu's exact wording varies.
ORDER_ID_RE = re.compile(r"(?:Order\s*(?:ID|Number|#))[:\s]*([A-Z0-9\-]{6,})", re.IGNORECASE)
ORDER_ID_FALLBACK_RE = re.compile(r"\bO\d{15,}\b")
TRACKING_RE = re.compile(r"(?:Tracking\s*(?:Number|#)?)[:\s]+([A-Z0-9]{8,})", re.IGNORECASE)
TOTAL_RE = re.compile(r"(?:Order\s*Total|Total\s*Paid|Total)[:\s]*[A-Z$R]*\s*([\d,]+\.\d{2})",
                      re.IGNORECASE)


def parse_temu_receipt(text: str) -> dict:
    """Extract Temu order ID, tracking number, and total from pasted text.
    Returns {} if nothing recognisable."""
    out = {}
    if not text:
        return out
    m = ORDER_ID_RE.search(text)
    if m:
        out["order_id"] = m.group(1).strip()
    elif ORDER_ID_FALLBACK_RE.search(text):
        out["order_id"] = ORDER_ID_FALLBACK_RE.search(text).group(0)
    m = TRACKING_RE.search(text)
    if m:
        out["tracking_number"] = m.group(1).strip()
    m = TOTAL_RE.search(text)
    if m:
        try:
            out["total"] = Decimal(m.group(1).replace(",", ""))
        except Exception:
            pass
    return out


@login_required
def po_parse_receipt(request, pk):
    """Show a paste form; on POST, parse + auto-apply to the PO (with confirmation step)."""
    po = get_object_or_404(PurchaseOrder, pk=pk)
    parsed: dict = {}
    pasted_text = ""
    if request.method == "POST":
        pasted_text = request.POST.get("text", "")
        parsed = parse_temu_receipt(pasted_text)
        if request.POST.get("apply") == "1":
            if "order_id" in parsed:
                po.temu_order_id = parsed["order_id"]
            if "tracking_number" in parsed:
                po.tracking_number = parsed["tracking_number"]
            if po.status == "DRAFT":
                po.status = "SENT"
            po.save()
            messages.success(request, f"Applied parsed data to {po.reference}.")
            return redirect("po_detail", pk=pk)
    return render(request, "inventory/po_parse_receipt.html", {
        "po": po, "pasted": pasted_text, "parsed": parsed,
    })


# ---------------------------------------------------------------------------
# Sales
# ---------------------------------------------------------------------------


@login_required
def sales_index(request):
    sales = Sale.objects.select_related(
        "product_variant", "product_variant__product"
    ).order_by("-sale_date", "-created_at")[:200]
    return render(request, "inventory/sales_index.html", {"sales": sales})


@login_required
def sales_record(request):
    if request.method != "POST":
        variants = ProductVariant.objects.filter(is_active=True).select_related(
            "product", "variant"
        ).order_by("product", "variant")
        return render(request, "inventory/sales_record.html", {"variants": variants})

    sku = request.POST.get("variant")
    pv = get_object_or_404(ProductVariant, sku=sku)
    try:
        qty = int(request.POST.get("qty") or "1")
        unit_price = Decimal(request.POST.get("unit_price") or "0")
    except (ValueError, ArithmeticError):
        messages.error(request, "Invalid quantity or price.")
        return redirect("sales_record")
    Sale.objects.create(
        product_variant=pv,
        quantity=qty,
        unit_price_zar=unit_price,
        channel=request.POST.get("channel") or "WEBSITE",
        customer_name=request.POST.get("customer_name", "").strip(),
        notes=request.POST.get("notes", "").strip(),
        created_by=request.user,
    )
    messages.success(request, f"Recorded sale of {qty} x {pv.sku}.")
    return redirect("sales")
