"""URL surface for the operations app — process-flow nav verbs at the top level."""

from django.urls import path

from . import views

urlpatterns = [
    # Build flow
    path("build/", views.build_index, name="build"),
    path("build/check/", views.build_check, name="build_check"),
    path("build/start/", views.build_start_project, name="build_start_project"),

    # Track flow
    path("track/", views.track_index, name="track"),
    path("track/project/<int:pk>/", views.project_detail, name="project_detail"),
    path("track/project/<int:pk>/run/", views.project_record_run, name="project_record_run"),
    path("track/project/<int:pk>/complete/", views.project_complete, name="project_complete"),
    path("track/project/<int:pk>/cancel/", views.project_cancel, name="project_cancel"),

    # Purchase flow
    path("purchase/", views.purchase_index, name="purchase"),
    path("purchase/draft/", views.purchase_draft_po, name="purchase_draft_po"),
    path("purchase/po/<int:pk>/", views.po_detail, name="po_detail"),
    path("purchase/po/<int:pk>/sent/", views.po_mark_sent, name="po_mark_sent"),
    path("purchase/po/<int:pk>/received/", views.po_mark_received, name="po_mark_received"),
    path("purchase/po/<int:pk>/cancel/", views.po_cancel, name="po_cancel"),
    path("purchase/po/<int:pk>/temu/", views.po_open_in_temu, name="po_open_in_temu"),
    path("purchase/po/<int:pk>/parse-receipt/", views.po_parse_receipt, name="po_parse_receipt"),

    # Sales flow
    path("sales/", views.sales_index, name="sales"),
    path("sales/record/", views.sales_record, name="sales_record"),

    # Data — export / import the canonical master workbook
    path("data/", views.data_index, name="data"),
    path("data/export/", views.data_export, name="data_export"),
    path("data/import/", views.data_import, name="data_import"),
]
