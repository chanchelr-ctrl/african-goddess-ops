r"""
Open Temu in a managed Chromium browser, pre-loaded with a search for the
given material SKU(s) or PO. Tersia logs in once (Playwright keeps her
session in `.playwright_temu_state.json`) and then can review results +
add to cart. The window stays open until she closes it.

Usage:
    python manage.py temu_search --sku DB4914290
    python manage.py temu_search --po PO-20260504-001
    python manage.py temu_search --sku DB4914290 --headless

Notes:
- Requires Playwright + Chromium. setup.ps1 installs both.
- This is a *helper*, not full automation. We pre-load the search; Tersia
  drives the cart and checkout. After ordering, she records the Temu order
  ID + tracking number back in the app via the PO's "Mark as sent" form
  (or the paste-and-parse receipt feature).
- Saved login state means she only logs in once. State file is gitignored.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote_plus

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from inventory.models import PurchaseOrder, RawMaterial
from inventory.views import temu_search_key


STATE_FILE = Path(settings.BASE_DIR) / ".playwright_temu_state.json"
TEMU_SEARCH = "https://www.temu.com/search_result.html?search_key={q}"


class Command(BaseCommand):
    help = "Open Temu in a managed browser pre-loaded with a search."

    def add_arguments(self, parser):
        g = parser.add_mutually_exclusive_group(required=True)
        g.add_argument("--sku", help="Search Temu for this raw-material SKU.")
        g.add_argument("--po", help="Open one tab per line on this PO reference.")
        parser.add_argument("--headless", action="store_true",
                            help="Run without showing the window. (For automated tests.)")
        parser.add_argument("--clear-state", action="store_true",
                            help="Delete saved login state before launching.")

    def handle(self, *args, **options):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise CommandError(
                "Playwright not installed. Run: "
                ".venv\\Scripts\\python.exe -m pip install playwright && "
                ".venv\\Scripts\\python.exe -m playwright install chromium"
            )

        if options["clear_state"] and STATE_FILE.exists():
            STATE_FILE.unlink()
            self.stdout.write("Cleared saved Temu login state.")

        # Build list of search queries
        queries: list[tuple[str, str]] = []  # (label, search_key)
        if options["sku"]:
            sku = options["sku"]
            try:
                m = RawMaterial.objects.get(sku=sku)
            except RawMaterial.DoesNotExist:
                queries = [(sku, sku)]
            else:
                queries = [(f"{m.sku} — {m.name[:40]}", temu_search_key(m))]
        else:
            ref = options["po"]
            try:
                po = PurchaseOrder.objects.get(reference=ref)
            except PurchaseOrder.DoesNotExist:
                raise CommandError(f"PO not found: {ref}")
            for line in po.lines.select_related("raw_material").all():
                rm = line.raw_material
                queries.append((f"{rm.sku} — {rm.name[:40]}", temu_search_key(rm)))

        if not queries:
            raise CommandError("Nothing to search.")

        self.stdout.write(self.style.NOTICE(
            f"\nLaunching Chromium with {len(queries)} Temu tab(s)...\n"
        ))

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=options["headless"])
            context_kwargs = {}
            if STATE_FILE.exists():
                context_kwargs["storage_state"] = str(STATE_FILE)
            context = browser.new_context(**context_kwargs)

            for label, query in queries:
                self.stdout.write(f"  → {label}")
                page = context.new_page()
                page.goto(TEMU_SEARCH.format(q=quote_plus(query)), wait_until="domcontentloaded")

            if not options["headless"]:
                self.stdout.write(self.style.SUCCESS(
                    "\nBrowser is open. Drive checkout in the window. "
                    "When you're done, close the browser to save your login state.\n"
                ))
                # Wait for the user to close the browser
                try:
                    page.wait_for_event("close", timeout=0)
                except Exception:
                    pass

            # Save login state so next launch is logged in
            try:
                context.storage_state(path=str(STATE_FILE))
                self.stdout.write(f"Saved Temu session state to {STATE_FILE.name}")
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Could not save state: {e}"))

            browser.close()
