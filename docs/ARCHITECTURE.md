# Architecture

> Engineering reference for the African Goddess Operations app. The authoritative version lives in the consultant's knowledge repo at `Inventory & Sales Management/07_Custom_Build/architecture.md` — this is a copy kept alongside the code so any future maintainer can read it without that repo.

For full content please see the source document. Highlights:

## Stack

- Python 3.11+, Django 5.1.x, SQLite (file-based)
- Pico.css + HTMX 2, Waitress WSGI, pytest
- Zero third-party licence costs. Loopback-only on Tersia's desktop.

## Data model — 8 tables

`Supplier`, `RawMaterial`, `Product`, `BomLine`, `PurchaseOrder`, `PurchaseOrderLine`, `StockMovement` (append-only audit log), `ProductionRun`.

Decimal precision = 4 places everywhere. ZAR-only. No multi-tenancy. No multi-currency.

## Side-effect points

Two only:
1. `PurchaseOrder.save()` — when status transitions into `RECEIVED`, increments stock and writes a `StockMovement(reason=PO_RECEIVED)` per line.
2. `ProductionRun.save()` — atomically deducts BOM × run-quantity for each ingredient and writes `StockMovement(reason=PRODUCTION_CONSUMED)` per line. Refuses if any material would go negative.

Production runs are immutable post-save. Audit corrections happen via manual `StockMovement(reason=ADJUSTMENT)` rows.

## URL surface

- `/` — dashboard (login required)
- `/admin/` — Django admin (Tersia's primary CRUD UI)
- `/healthz/` — JSON liveness (no auth)
- `/inventory/...` — drill-down dashboard sub-views (Day-2-and-beyond)

## Capability gaps explicitly absorbed by this build

- Decimal precision & unit conversions ✓ (Decimal(4) + `unit` field)
- Cost-flow method ✓ (last-paid unit cost)
- Audit trail ✓ (`StockMovement` is the source of truth)
- Reconciliation tool ✓ (`manage.py reconcile_stock`)

## Capability gaps consciously deferred

- WooCommerce sync — out of scope per client direction
- Customer-facing components — out of scope per client direction
- Variant explosion — variants modelled as distinct Products for now
- Multi-user collaboration — single-user only
- Email/WhatsApp notifications — surfaced in dashboard only

See the consultant's knowledge-repo `build_vs_buy_analysis.md` and `architecture.md` for the full reasoning behind these scope choices.
