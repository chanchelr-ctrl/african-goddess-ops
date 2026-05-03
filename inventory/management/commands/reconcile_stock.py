"""
Verify the invariant: for every RawMaterial,
    current_stock == sum(StockMovement.delta for that material)

If discrepancies are found, prints them. With --fix, recomputes
current_stock from the movement log (truth = the audit trail).

Usage:
    python manage.py reconcile_stock           # report only
    python manage.py reconcile_stock --fix     # recompute current_stock from movements
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum

from inventory.models import RawMaterial


class Command(BaseCommand):
    help = "Reconcile RawMaterial.current_stock against the StockMovement audit log."

    def add_arguments(self, parser):
        parser.add_argument("--fix", action="store_true",
                            help="Recompute current_stock from the movement log.")

    def handle(self, *args, **options):
        fix = options["fix"]
        problems = []
        for m in RawMaterial.objects.all():
            total = m.movements.aggregate(s=Sum("delta"))["s"] or Decimal("0")
            if m.current_stock != total:
                problems.append((m, total))

        if not problems:
            self.stdout.write(self.style.SUCCESS("All raw materials reconcile cleanly."))
            return

        self.stdout.write(self.style.WARNING(
            f"\nFound {len(problems)} material(s) with current_stock != sum(movements):\n"
        ))
        for m, total in problems:
            self.stdout.write(
                f"  {m.sku} ({m.name}): current_stock={m.current_stock}, movements_sum={total}, diff={m.current_stock - total}"
            )

        if fix:
            for m, total in problems:
                m.current_stock = total
                m.save(update_fields=["current_stock", "updated_at"])
            self.stdout.write(self.style.SUCCESS(
                f"\nFixed: {len(problems)} material(s) recomputed from the audit log."
            ))
        else:
            self.stdout.write("\nRe-run with --fix to recompute current_stock from the audit log.")
