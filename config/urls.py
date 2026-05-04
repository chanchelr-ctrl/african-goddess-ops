from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import include, path

from inventory import views as inventory_views

# Tersia-friendly admin branding
admin.site.site_header = "African Goddess — Operations"
admin.site.site_title = "African Goddess Ops"
admin.site.index_title = "Operations Dashboard"

urlpatterns = [
    path("", login_required(inventory_views.dashboard), name="dashboard"),
    path("admin/", admin.site.urls),
    path("", include("inventory.urls")),
    path("healthz/", inventory_views.healthz, name="healthz"),
]
