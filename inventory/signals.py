"""Audit signal handlers — write a DataChangeLog entry for every CREATE,
UPDATE, or DELETE on the tracked master/spec models.

Tracked: RawMaterial, Product, ProductVariant, Variant, Brand, BomLine, Supplier
Not tracked: StockMovement (already an audit log), PurchaseOrder/Sale/
ProductionRun/Project (operational, not master data), and DataChangeLog
itself (don't audit the auditor).
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .audit import get_current_user
from .models import (
    BomLine,
    Brand,
    DataChangeLog,
    Product,
    ProductVariant,
    RawMaterial,
    Supplier,
    Variant,
)

TRACKED_MODELS = (
    RawMaterial,
    Product,
    ProductVariant,
    Variant,
    Brand,
    BomLine,
    Supplier,
)

# Fields we explicitly do NOT log per-field changes for — they're noisy or
# auto-managed.
SKIP_FIELDS = {"updated_at", "created_at"}


def _stringify(v) -> str:
    if v is None:
        return ""
    if isinstance(v, Decimal):
        return f"{v:f}".rstrip("0").rstrip(".") or "0"
    return str(v)


def _sku_of(instance) -> str:
    """Best-effort identifier on the instance. Different models have different
    keys: RawMaterial.sku, Product.code, Variant.code, ProductVariant.sku,
    BomLine has no key (we use product_variant.sku + raw_material.sku),
    Supplier.name, Brand.code."""
    for attr in ("sku", "code", "name"):
        v = getattr(instance, attr, None)
        if v:
            return str(v)
    if isinstance(instance, BomLine):
        try:
            return f"{instance.product_variant.sku} <- {instance.raw_material.sku}"
        except Exception:
            return ""
    return ""


@receiver(pre_save)
def _capture_pre_save_state(sender, instance, **kwargs):
    if sender not in TRACKED_MODELS:
        return
    if not instance.pk:
        return
    try:
        instance._audit_pre = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        instance._audit_pre = None


@receiver(post_save)
def _log_post_save(sender, instance, created, **kwargs):
    if sender not in TRACKED_MODELS:
        return
    user = get_current_user()
    sku = _sku_of(instance)
    model_name = sender.__name__

    if created:
        DataChangeLog.objects.create(
            user=user, action="CREATE",
            model_name=model_name, object_pk=instance.pk, sku=sku,
            field="", old_value="", new_value=_stringify(instance),
        )
        return

    pre = getattr(instance, "_audit_pre", None)
    if pre is None:
        # No snapshot available — still record an UPDATE, but without diff
        DataChangeLog.objects.create(
            user=user, action="UPDATE",
            model_name=model_name, object_pk=instance.pk, sku=sku,
            field="", old_value="", new_value="",
            note="no pre-save snapshot",
        )
        return

    for f in instance._meta.concrete_fields:
        if f.name in SKIP_FIELDS:
            continue
        old = getattr(pre, f.name, None)
        new = getattr(instance, f.name, None)
        if old == new:
            continue
        DataChangeLog.objects.create(
            user=user, action="UPDATE",
            model_name=model_name, object_pk=instance.pk, sku=sku,
            field=f.name,
            old_value=_stringify(old),
            new_value=_stringify(new),
        )


@receiver(post_delete)
def _log_post_delete(sender, instance, **kwargs):
    if sender not in TRACKED_MODELS:
        return
    DataChangeLog.objects.create(
        user=get_current_user(), action="DELETE",
        model_name=sender.__name__, object_pk=instance.pk,
        sku=_sku_of(instance),
        field="", old_value=_stringify(instance), new_value="",
    )
