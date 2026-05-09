from django.apps import AppConfig


class InventoryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "inventory"
    verbose_name = "Inventory & Operations"

    def ready(self):
        # Register audit signal handlers
        from . import signals  # noqa: F401
