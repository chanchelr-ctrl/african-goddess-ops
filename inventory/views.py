"""
Views for African Goddess operations (v0.2).

Process-flow nav top-level verbs:
- Dashboard (/)              - operations snapshot
- Build (/build/)            - start a new build / project
- Track (/track/)            - in-flight projects
- Purchase (/purchase/)      - reorder + Temu pipeline
- Data (/data/)              - export / import the master workbook

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
    DataChangeLog,
    ProductionRun,
    Product,
    ProductVariant,
    Project,
    ProjectItem,
    PurchaseOrder,
    PurchaseOrderLine,
    RawMaterial,
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
    """Workflow launchpad. Four rows — Build / Track / Purchase / Data —
    each with three KPIs. The whole row is the link to that workflow.
    """
    today = timezone.localdate()
    last_7 = today - timedelta(days=7)

    # ---- Build ---------------------------------------------------------
    pvs_qs = (ProductVariant.objects
              .filter(is_active=True)
              .prefetch_related("bom_lines__raw_material"))
    build_can_make = 0
    build_total_units = 0
    build_blocked = 0
    for pv in pvs_qs:
        n = pv.can_make_units
        if n > 0:
            build_can_make += 1
            build_total_units += n
        else:
            build_blocked += 1
    build_alert = build_can_make == 0 and build_blocked > 0

    # ---- Track ---------------------------------------------------------
    in_flight = (Project.objects
                 .filter(status__in=("PLANNED", "IN_PROGRESS"))
                 .prefetch_related("items"))
    track_in_flight = in_flight.count()
    track_planned = sum(p.total_planned_units for p in in_flight)
    track_made = sum(p.total_made_units for p in in_flight)
    track_progress_pct = (
        round(100 * track_made / track_planned) if track_planned else 0
    )
    track_runs_week = ProductionRun.objects.filter(run_date__gte=last_7).count()

    # ---- Purchase ------------------------------------------------------
    purchase_low_stock = RawMaterial.objects.filter(
        is_active=True, current_stock__lte=F("reorder_point"),
    ).count()
    open_pos = PurchaseOrder.objects.filter(status__in=("DRAFT", "SENT"))
    purchase_open_pos = open_pos.count()
    purchase_on_order_value = open_pos.aggregate(
        total=Sum(F("lines__pack_size") * F("lines__pack_count") * F("lines__unit_cost"))
    )["total"] or Decimal("0")
    purchase_alert = purchase_low_stock > 0

    # ---- Data ----------------------------------------------------------
    data_materials = RawMaterial.objects.filter(is_active=True).count()
    data_bom_lines = BomLine.objects.count()
    data_changes_today = DataChangeLog.objects.filter(timestamp__date=today).count()

    return render(request, "inventory/dashboard.html", {
        "build_can_make": build_can_make,
        "build_total_units": build_total_units,
        "build_blocked": build_blocked,
        "build_alert": build_alert,
        "track_in_flight": track_in_flight,
        "track_made": track_made,
        "track_planned": track_planned,
        "track_progress_pct": track_progress_pct,
        "track_runs_week": track_runs_week,
        "purchase_low_stock": purchase_low_stock,
        "purchase_open_pos": purchase_open_pos,
        "purchase_on_order_value": purchase_on_order_value,
        "purchase_alert": purchase_alert,
        "data_materials": data_materials,
        "data_bom_lines": data_bom_lines,
        "data_changes_today": data_changes_today,
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
    """Sufficiency check for a (variant, qty) pair. Returns the full BOM
    with need vs. have per material, plus a shortfall summary."""
    sku = request.GET.get("variant") or request.POST.get("variant")
    try:
        qty = int(request.GET.get("qty") or request.POST.get("qty") or "1")
    except ValueError:
        qty = 1

    pv = None
    if sku:
        pv = ProductVariant.objects.filter(sku=sku).first()

    shortfalls = []
    bom_lines = []
    if pv and qty > 0:
        shortfalls = pv.material_shortfalls(qty)
        for line in pv.bom_lines.select_related("raw_material").order_by("raw_material__name"):
            need = line.quantity * qty
            have = line.raw_material.current_stock
            bom_lines.append({
                "material": line.raw_material,
                "qty_per_unit": line.quantity,
                "need": need,
                "have": have,
                "short": max(need - have, 0),
                "sufficient": have >= need,
            })

    variants = ProductVariant.objects.filter(is_active=True).select_related(
        "product", "variant", "product__brand"
    ).order_by("product__brand", "product", "variant")

    # Pre-fill project name suggestion (operator can override)
    default_name = ""
    if pv and qty > 0:
        default_name = f"{qty} × {pv.product.name} — {pv.variant.name}"

    return render(request, "inventory/build_check.html", {
        "variants": variants,
        "selected_pv": pv,
        "qty": qty,
        "shortfalls": shortfalls,
        "bom_lines": bom_lines,
        "is_sufficient": pv is not None and qty > 0 and not shortfalls,
        "default_project_name": default_name,
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


@login_required
def project_cancel(request, pk):
    """Cancel a project. If any ProductionRuns were recorded, reverse the
    stock they consumed via ADJUSTMENT movements (the original PRODUCTION_CONSUMED
    movements stay — they're audit history). Two-step: GET shows confirm page
    with what will be reversed; POST commits."""
    from django.db import transaction
    project = get_object_or_404(Project, pk=pk)
    if project.status == "CANCELLED":
        messages.info(request, "Project is already cancelled.")
        return redirect("project_detail", pk=pk)

    # Compute what will be reversed = sum of (BOM × run.quantity) per material
    runs = list(project.production_runs.select_related("product_variant").all())
    to_restore: dict[int, dict] = {}
    for run in runs:
        for line in run.product_variant.bom_lines.select_related("raw_material").all():
            consumed = line.quantity * run.quantity
            entry = to_restore.setdefault(line.raw_material_id, {
                "material": line.raw_material,
                "qty": Decimal("0"),
            })
            entry["qty"] += consumed

    if request.method == "POST":
        with transaction.atomic():
            for entry in to_restore.values():
                m = entry["material"]
                qty = entry["qty"]
                m.current_stock = m.current_stock + qty
                m.save(update_fields=["current_stock", "updated_at"])
                StockMovement.objects.create(
                    raw_material=m, delta=qty, reason="ADJUSTMENT",
                    related_object_type="Project", related_object_id=project.pk,
                    note=f"Reversal: project '{project.name}' cancelled",
                    created_by=request.user,
                )
            project.status = "CANCELLED"
            project.save(update_fields=["status", "updated_at"])
        if to_restore:
            messages.success(
                request,
                f"Project cancelled. Restored {len(to_restore)} material(s) "
                f"across {len(runs)} reversed production run(s).",
            )
        else:
            messages.success(request, "Project cancelled (no production runs to reverse).")
        return redirect("project_detail", pk=pk)

    return render(request, "inventory/project_cancel.html", {
        "project": project,
        "runs": runs,
        "to_restore": list(to_restore.values()),
    })


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
def po_cancel(request, pk):
    """Cancel a PO. If status was RECEIVED, reverse the receipt with negative
    ADJUSTMENT movements per line. Two-step confirm page."""
    from django.db import transaction
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if po.status == "CANCELLED":
        messages.info(request, "PO is already cancelled.")
        return redirect("po_detail", pk=pk)

    # If RECEIVED, compute reversal lines
    to_remove: list[dict] = []
    if po.status == "RECEIVED":
        for line in po.lines.select_related("raw_material").all():
            qty_units = line.units_total
            if qty_units <= 0:
                continue
            to_remove.append({
                "material": line.raw_material,
                "qty": qty_units,
                "current_stock": line.raw_material.current_stock,
                "after_cancel": line.raw_material.current_stock - qty_units,
            })

    if request.method == "POST":
        with transaction.atomic():
            for entry in to_remove:
                m = entry["material"]
                qty = entry["qty"]
                m.current_stock = m.current_stock - qty
                m.save(update_fields=["current_stock", "updated_at"])
                StockMovement.objects.create(
                    raw_material=m, delta=-qty, reason="ADJUSTMENT",
                    related_object_type="PurchaseOrder", related_object_id=po.pk,
                    note=f"Reversal: PO {po.reference} receipt cancelled",
                    created_by=request.user,
                )
            po.status = "CANCELLED"
            po.save(update_fields=["status", "updated_at"])
        if to_remove:
            messages.success(
                request,
                f"PO {po.reference} cancelled. Reversed {len(to_remove)} material receipt(s).",
            )
        else:
            messages.success(request, f"PO {po.reference} cancelled.")
        return redirect("po_detail", pk=pk)

    return render(request, "inventory/po_cancel.html", {
        "po": po,
        "to_remove": to_remove,
    })


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
# Data — export / import master data .xlsx
# ---------------------------------------------------------------------------


# ---- Data BI dashboard: derived categorisations ---------------------------

# Order matters in each list: more specific patterns checked first
_FINDING_KEYWORDS = ("clasp", "extender", "bail", "spacer bead", "spacer",
                     "crimp", "stopper", "fishing", "tube bail", "wig clip",
                     "snap clip", "jump ring", "extender chain")
_WIRE_KEYWORDS = ("tiger tail", "beading wire", "chain")
_PENDANT_KEYWORDS = ("pendant", "charm", "lotus", "protea", "sunburst",
                     "logo round disc", "logo")
_PACKAGING_KEYWORDS = ("ziplock", "zipper", "pvc", "self-sealing", "bag")

# Bead-material sub-types (only meaningful for bead-form materials)
_BEAD_KEYWORDS = (
    ("Shell",          ("shell",)),
    ("Pearl",          ("pearl", "freshwater")),
    ("Crystal",        ("austrian crystal", "crystal", "czech")),
    ("Polymer / Clay", ("polymer clay", "soft clay", "clay disc")),
    ("Natural Stone",  ("natural stone", "amethyst", "howlite", "cats eye",
                        "cat eye", "agate", "chalcedony", "angelite",
                        "amazonite", "rose red")),
    ("Glass",          ("glass", "porcelain", "faceted", "rondelle")),
)

_COLOUR_FAMILY_MAP = (
    ("Multi / AB",       ("multi", "ab color", "ab electroplated", "rainbow")),
    ("Greys & Steels",   ("stainless steel", "grey", "gray", "silver", "gunmetal")),
    ("Whites & Creams",  ("white", "cream", "ivory", "porcelain", "natural shell")),
    ("Blacks",           ("black", "jet")),
    ("Browns & Earths",  ("brown", "sienna", "chocolate", "taupe", "bronze")),
    ("Yellows & Golds",  ("gold", "champagne", "yellow", "amber")),
    ("Oranges",          ("orange", "tangerine")),
    ("Reds & Pinks",     ("red", "pink", "coral", "magenta", "watermelon", "rose")),
    ("Purples",          ("amethyst", "purple", "lavender", "plum", "violet")),
    ("Greens",           ("green", "lime", "sage", "amazonite", "teal", "mint")),
    ("Blues",            ("blue", "turquoise", "periwinkle", "indigo")),
)


def _haystack(m):
    return " ".join([m.name or "", m.description or "", m.shape or "",
                     m.finish or "", m.colour or ""]).lower()


def _material_category(m) -> str:
    """All-materials high-level category. One of 8 buckets."""
    h = _haystack(m)
    if any(k in h for k in _PACKAGING_KEYWORDS):  return "Packaging"
    if any(k in h for k in _WIRE_KEYWORDS):       return "Wire & Cord"
    if any(k in h for k in _PENDANT_KEYWORDS):    return "Pendants & Charms"
    if any(k in h for k in _FINDING_KEYWORDS):    return "Findings"
    # Below this point we have a bead-form material — bucket by material:
    for label, kws in _BEAD_KEYWORDS:
        if any(k in h for k in kws):
            return label
    return "Other"


def _bead_category(m):
    """Bead-only sub-category. Returns None for findings/wire/packaging."""
    h = _haystack(m)
    if any(k in h for k in _PACKAGING_KEYWORDS): return None
    if any(k in h for k in _WIRE_KEYWORDS):      return None
    if any(k in h for k in _PENDANT_KEYWORDS):   return None
    if any(k in h for k in _FINDING_KEYWORDS):   return None
    for label, kws in _BEAD_KEYWORDS:
        if any(k in h for k in kws):
            return label
    return "Other beads"


def _colour_family(m) -> str:
    h = (m.colour or "").lower() + " " + (m.finish or "").lower()
    for label, kws in _COLOUR_FAMILY_MAP:
        if any(k in h for k in kws):
            return label
    return "Other"


def _size_band(m) -> str:
    s = (m.item_size or "").lower()
    if not s:
        return "n/a"
    import re as _re
    match = _re.search(r"(\d+(?:[.,]\d+)?)\s*mm", s)
    if not match:
        return "n/a"
    try:
        val = float(match.group(1).replace(",", "."))
    except ValueError:
        return "n/a"
    if val < 5:    return "4 mm"
    if val < 7:    return "6 mm"
    if val < 9:    return "8 mm"
    if val < 11:   return "10 mm"
    if val < 13:   return "12 mm"
    return "12 mm+"


def _stock_status(m) -> str:
    if m.current_stock <= 0:
        return "out"
    if m.current_stock <= m.reorder_point:
        return "low"
    return "ok"


@login_required
def data_index(request):
    """Inventory BI dashboard — 5 visualisations on top, searchable table
    in the middle (driven by chart filters), import/export + change log
    at the bottom.
    """
    import json
    from collections import Counter

    materials = list(
        RawMaterial.objects
        .filter(is_active=True)
        .select_related("preferred_supplier")
        .order_by("name")
    )

    # Derive + collect per-material attributes once
    enriched = []
    for m in materials:
        cat = _material_category(m)
        bead = _bead_category(m)
        size = _size_band(m)
        colour = _colour_family(m)
        status = _stock_status(m)
        stock_value = float(m.current_stock * m.last_paid_unit_cost)
        enriched.append({
            "sku": m.sku,
            "name": m.name,
            "item_size": m.item_size or "",
            "colour": m.colour or "",
            "shape": m.shape or "",
            "supplier": m.preferred_supplier.name if m.preferred_supplier else "",
            "unit": m.get_unit_display(),
            "current_stock": int(m.current_stock),
            "reorder_point": int(m.reorder_point),
            "unit_cost": round(float(m.last_paid_unit_cost), 2),
            "stock_value": round(stock_value, 2),
            "category": cat,
            "bead_category": bead,
            "size_band": size,
            "colour_family": colour,
            "stock_status": status,
        })

    # Chart aggregates
    stock_health_counter = Counter(e["stock_status"] for e in enriched)
    stock_health_data = [
        {"label": "OK",  "value": stock_health_counter.get("ok", 0),  "color": "#4d7a4d"},
        {"label": "Low", "value": stock_health_counter.get("low", 0), "color": "#b0794a"},
        {"label": "Out", "value": stock_health_counter.get("out", 0), "color": "#c84432"},
    ]

    category_counter = Counter(e["category"] for e in enriched)
    category_data = [
        {"label": k, "value": v} for k, v in category_counter.most_common()
    ]

    shape_counter = Counter((e["shape"] or "Other").strip() or "Other" for e in enriched)
    shape_data = [
        {"label": k, "value": v} for k, v in shape_counter.most_common(10)
    ]

    size_order = ["4 mm", "6 mm", "8 mm", "10 mm", "12 mm", "12 mm+", "n/a"]
    size_counter = Counter(e["size_band"] for e in enriched)
    size_data = [
        {"label": s, "value": size_counter.get(s, 0)}
        for s in size_order if size_counter.get(s, 0) > 0
    ]

    counts = {
        "materials": RawMaterial.objects.count(),
        "active_materials": RawMaterial.objects.filter(is_active=True).count(),
        "products": Product.objects.count(),
        "product_variants": ProductVariant.objects.count(),
        "bom_lines": BomLine.objects.count(),
        "change_log_entries": DataChangeLog.objects.count(),
    }

    return render(request, "inventory/data_index.html", {
        "materials_json":    json.dumps(enriched),
        "stock_health_json": json.dumps(stock_health_data),
        "category_json":     json.dumps(category_data),
        "shape_json":        json.dumps(shape_data),
        "size_json":         json.dumps(size_data),
        "recent_changes":    DataChangeLog.objects.select_related("user").order_by("-timestamp")[:50],
        "counts":            counts,
    })


@login_required
def data_export(request):
    """Stream a freshly-generated MasterData_v5.xlsx to the browser."""
    from datetime import datetime
    from .management.commands.export_master import export_to_bytes

    payload = export_to_bytes()
    filename = f"MasterData_{datetime.now():%Y-%m-%d_%H%M}.xlsx"
    response = HttpResponse(
        payload,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def data_import(request):
    """Accept an uploaded MasterData .xlsx and apply it to the DB."""
    if request.method != "POST":
        return redirect("data")

    upload = request.FILES.get("file")
    if not upload:
        messages.error(request, "Please choose a file to upload.")
        return redirect("data")

    # Save upload to a temp path (openpyxl needs a real path or file-like)
    import tempfile
    from pathlib import Path as _Path
    from django.core.management import call_command
    from io import StringIO

    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    try:
        for chunk in upload.chunks():
            tmp.write(chunk)
        tmp.close()

        args = [tmp.name]
        if request.POST.get("prune") == "on":
            args.append("--prune")
        out = StringIO()
        try:
            call_command("import_master", *args, stdout=out)
        except Exception as e:
            messages.error(request, f"Import failed: {e}")
            return redirect("data")

        report = out.getvalue()
        # Surface the summary as a single message
        summary_lines = [ln.strip() for ln in report.splitlines() if ln.strip()]
        messages.success(
            request,
            "Import complete. " + " · ".join(
                ln for ln in summary_lines
                if ln and ":" in ln and not ln.startswith("=")
            )[:500],
        )
    finally:
        try:
            _Path(tmp.name).unlink(missing_ok=True)
        except Exception:
            pass

    return redirect("data")
