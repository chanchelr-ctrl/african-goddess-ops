"""
Post-import verification for MasterData_v6.

Confirms that the DB matches the v6 ground truth we built — counts,
spot-checks of specific BOM additions and removals, brand assignment,
and stock totals.

Run on PA (or locally):
    python scripts/_verify_v6_data.py
"""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from inventory.models import (
    Brand, BomLine, DataChangeLog, ProductVariant, RawMaterial,
    StockMovement, Supplier,
)


# Expected ground truth from MasterData_v6.xlsx
EXPECT_MATERIALS = 81
EXPECT_PVS       = 60
EXPECT_BOM_LINES = 1457  # if --prune was used; otherwise 1515 (= 1477 + 38)
EXPECT_BRANDS    = {"African Goddess": 24, "Sugar Bush": 36}  # PV counts by brand

# A) Lines that v6 ADDED — should be present in DB after import
ADDED_BOM = [
    ("SBA02BK",  "DX2470749_6_x_4mm_Natural_Pearl",                 1),
    ("SBA04BK",  "DX2470749_6_x_4mm_Natural_Pearl",                 1),
    ("SBA06BK",  "DX2470749_6_x_4mm_Natural_Pearl",                 1),
    ("SBA02NL",  "DX2470749_6_x_4mm_Natural_Pearl",                 4),
    ("SBA02EARR","AP52616_4mm_White_Spun_Golden",                   4),
    ("SBA04EARR","AP52616_4mm_White_Spun_Golden",                   4),
    ("SBA06EARR","AP52616_4mm_White_Spun_Golden",                   4),
    ("SBR06EARR","AM10184748_4mm_Clear_AB_Colour",                  4),
    ("SBR06EARR","CJ2582417_4mm_Glossy_White_Agate_Beads",          6),
    ("SBR06EARR","KM1941718_4mm_Beige",                             6),
    ("SBR06DNL", "AM10184748_4mm_Clear_AB_Colour",                  17),
    ("SBR01DANK","YU400654_10_5_x_11cm_Clear_PVC",                  1),
]

# B) Lines that v6 REMOVED — should NOT be present in DB IF --prune was used.
#    Without --prune, these would still exist (import is additive).
REMOVED_BOM = [
    ("SBA02BK",  "GG630368_6_x_3mm_Stainless_Steel"),
    ("SBA02BK",  "JE6344233_4mm_Rose_Red_Chalcedony_Red_Angelite"),
    ("SBR01DANK","MT6491134_8_x_8cm_Clear_PVC"),
    ("SBA02EARR","RY449141_16_x_17cm_Burgundy_Colour_Tassle_Gold_Pearl"),
]

# C) Lines whose QUANTITY changed in v6 — confirm DB has the NEW qty
QTY_CHANGED = [
    ("SBR01DNL", "DB4914290_4mm_Solid_yellow_amber",                4),     # was 16
    ("SBR01DNL", "RW4228862_4mm_Orange_Cats_Eye_Fiber_Optic",       17),    # was 4
    ("SBA02WC",  "EL18546_4mm_AB_Watermelon_Red",                   24),    # was 12
    ("SBR04DNL", "JF181267_4mm_AB_Green",                           16),    # was 4
    ("SBR05EARR","PU3080792_4mm_Ink_Blue",                          6),     # was 10
]


def section(t: str):
    print()
    print("=" * 64)
    print(t)
    print("=" * 64)


def check(label: str, ok: bool, detail: str = ""):
    icon = "OK  " if ok else "FAIL"
    suffix = f"   {detail}" if detail else ""
    print(f"  [{icon}] {label}{suffix}")
    return ok


def main():
    failures = 0

    section("Top-level counts")
    mats = RawMaterial.objects.count()
    bom = BomLine.objects.count()
    pvs = ProductVariant.objects.count()
    brands = Brand.objects.count()
    suppliers = Supplier.objects.count()
    moves = StockMovement.objects.count()
    log = DataChangeLog.objects.count()

    failures += 0 if check(f"Materials count == {EXPECT_MATERIALS}",
                           mats == EXPECT_MATERIALS,
                           f"actual {mats}") else 1
    failures += 0 if check(f"ProductVariants count == {EXPECT_PVS}",
                           pvs == EXPECT_PVS,
                           f"actual {pvs}") else 1

    if bom == EXPECT_BOM_LINES:
        check(f"BOM lines == {EXPECT_BOM_LINES} (prune was used)", True,
              f"actual {bom}")
    elif bom == 1515:
        check(f"BOM lines == 1515 (prune NOT used; 58 stale lines remain)",
              True, f"actual {bom} — re-import with --prune to clean")
        failures += 1
    else:
        check(f"BOM lines in expected range", False,
              f"actual {bom} (expected 1457 with prune, 1515 without)")
        failures += 1

    print(f"\n  Brands={brands}   Suppliers={suppliers}   "
          f"StockMovements={moves}   ChangeLog entries={log}")

    section("Brand assignment per ProductVariant")
    for brand_name, expected in EXPECT_BRANDS.items():
        count = ProductVariant.objects.filter(product__brand__name=brand_name).count()
        failures += 0 if check(f'{brand_name}: {expected} PVs',
                               count == expected,
                               f"actual {count}") else 1

    section("Spot check: BOM lines v6 ADDED (must exist with correct qty)")
    for pv_sku, mat_sku, exp_qty in ADDED_BOM:
        line = BomLine.objects.filter(
            product_variant__sku=pv_sku, raw_material__sku=mat_sku
        ).first()
        if not line:
            failures += 1
            check(f"{pv_sku:14s} <- {mat_sku}", False, "MISSING")
        else:
            ok = line.quantity == Decimal(exp_qty)
            failures += 0 if ok else 1
            check(f"{pv_sku:14s} <- {mat_sku:48s} qty={exp_qty}",
                  ok, "" if ok else f"actual qty {line.quantity}")

    section("Spot check: BOM lines v6 REMOVED (should be gone IF --prune used)")
    pruned = True
    for pv_sku, mat_sku in REMOVED_BOM:
        exists = BomLine.objects.filter(
            product_variant__sku=pv_sku, raw_material__sku=mat_sku
        ).exists()
        if exists:
            pruned = False
        check(f"{pv_sku:14s} <- {mat_sku:48s} absent",
              not exists,
              "still present (prune did NOT run)" if exists else "")
    if not pruned:
        print("\n  NOTE: stale lines remain — re-run import with --prune to clean.")

    # Special-case: GG630368 stainless steel was phased out of EVERY PV
    section("Spot check: GG630368_6x3mm_Stainless_Steel phased-out everywhere")
    gg_lines = BomLine.objects.filter(
        raw_material__sku="GG630368_6_x_3mm_Stainless_Steel"
    ).count()
    if gg_lines == 0:
        check("GG630368 absent from all BOMs (47 PVs)", True)
    else:
        check("GG630368 absent from all BOMs", False,
              f"still in {gg_lines} BOM lines — needs --prune")
        failures += 1

    section("Spot check: quantity changes")
    for pv_sku, mat_sku, exp_qty in QTY_CHANGED:
        line = BomLine.objects.filter(
            product_variant__sku=pv_sku, raw_material__sku=mat_sku
        ).first()
        if not line:
            failures += 1
            check(f"{pv_sku:14s} <- {mat_sku}", False, "MISSING")
        else:
            ok = line.quantity == Decimal(exp_qty)
            failures += 0 if ok else 1
            check(f"{pv_sku:14s} <- {mat_sku:42s} qty={exp_qty}",
                  ok, "" if ok else f"actual qty {line.quantity}")

    section("Stock invariant (material changes were zero — totals should match v5)")
    total_units = sum(m.current_stock for m in RawMaterial.objects.all())
    total_value = sum(m.current_stock * m.last_paid_unit_cost
                      for m in RawMaterial.objects.all())
    print(f"  Total stock units:  {total_units}")
    print(f"  Total stock value:  R {total_value:,.2f}")
    print(f"  (v5 baseline was 26,581 units / R 10,310.03 — should match if "
          f"no movements happened)")

    section("DataChangeLog audit")
    recent = DataChangeLog.objects.order_by("-timestamp").values_list(
        "model_name", "action", "sku"
    )[:5]
    print(f"  Total entries: {log}")
    if recent:
        print(f"  5 most recent:")
        for m, a, s in recent:
            print(f"    {a:8s} {m:14s} {s}")

    print()
    print("=" * 64)
    if failures == 0:
        print("ALL CHECKS PASSED")
    else:
        print(f"{failures} CHECK(S) FAILED — review above")
    print("=" * 64)
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
