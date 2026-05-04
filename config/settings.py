"""
Django settings for African Goddess inventory & operations app.

Single-tenant. Self-hosted on Tersia's Windows desktop. SQLite.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Security ---------------------------------------------------------------

# Generated on first install by setup.ps1 and persisted to .env. Do NOT commit.
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-only-secret-do-not-use-in-production-replace-during-setup",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() == "true"

# Loopback only — the app is not exposed to the network. Override via env if
# Tersia ever wants LAN access from a phone.
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")

# CSRF: explicit trusted origins for the local dev server
CSRF_TRUSTED_ORIGINS = [f"http://{h}:8000" for h in ALLOWED_HOSTS]

# --- Apps -------------------------------------------------------------------

INSTALLED_APPS = [
    # Unfold admin theme — must come BEFORE django.contrib.admin
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_htmx",
    "inventory",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves static files efficiently in production. Must come
    # right after SecurityMiddleware.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Database ---------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            # Decent defaults for a single-user desktop app
            "timeout": 20,
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;",
        },
    }
}

# --- Auth -------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LOGIN_REDIRECT_URL = "/"
LOGIN_URL = "/admin/login/"

# --- I18n / Tz --------------------------------------------------------------

LANGUAGE_CODE = "en-za"
TIME_ZONE = "Africa/Johannesburg"
USE_I18N = True
USE_TZ = True

# --- Static -----------------------------------------------------------------

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# WhiteNoise: compressed + cache-busted static files in production
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# --- Defaults ---------------------------------------------------------------

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Silenced checks --------------------------------------------------------
# This app runs on 127.0.0.1 only (loopback). HTTPS-related warnings from
# `manage.py check --deploy` are not applicable. Silence them so the deploy
# check stays clean and meaningful for actually-relevant warnings.
SILENCED_SYSTEM_CHECKS = [
    "security.W004",  # SECURE_HSTS_SECONDS — not relevant on loopback HTTP
    "security.W008",  # SECURE_SSL_REDIRECT — not relevant on loopback HTTP
    "security.W012",  # SESSION_COOKIE_SECURE — not relevant on loopback HTTP
    "security.W016",  # CSRF_COOKIE_SECURE — not relevant on loopback HTTP
]

# --- Logging ----------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
        "file": {
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "app.log",
            "formatter": "verbose",
        },
    },
    "formatters": {
        "verbose": {"format": "{asctime} {levelname} {name} {message}", "style": "{"},
    },
    "root": {"handlers": ["console", "file"], "level": "INFO"},
}

# --- Money/decimal display --------------------------------------------------

# Currency symbol used by templates. Single-currency app.
CURRENCY_SYMBOL = "R"

# --- Unfold admin theme -----------------------------------------------------
# Brand palette: warm terracotta primary, muted gold accent, cream background.
# Inspired by African Goddess's "Sacred Tools For Sacred Times" positioning.

UNFOLD = {
    "SITE_TITLE": "African Goddess — Operations",
    "SITE_HEADER": "African Goddess",
    "SITE_SUBHEADER": "Operations",
    "SITE_SYMBOL": "auto_awesome",  # Material icon name
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "THEME": "light",
    "LOGIN": {
        "image": lambda r: "/static/branding/login_panel.svg",
    },
    "STYLES": [
        lambda r: "/static/branding/unfold-overrides.css",
    ],
    "COLORS": {
        "base": {
            "50": "250 246 241",   # warm cream
            "100": "245 238 230",
            "200": "232 221 211",
            "300": "199 184 170",
            "400": "144 127 113",
            "500": "107 93 82",
            "600": "78 65 55",
            "700": "63 50 41",
            "800": "45 24 16",
            "900": "30 16 11",
            "950": "20 11 7",
        },
        "primary": {
            "50": "253 246 235",   # cream-tinged amber
            "100": "250 234 211",
            "200": "243 213 169",
            "300": "232 187 121",
            "400": "210 149 76",
            "500": "160 82 45",    # terracotta — brand primary
            "600": "139 68 35",
            "700": "110 53 26",
            "800": "79 38 19",
            "900": "61 28 14",
            "950": "45 20 10",
        },
        "font": {
            "subtle-light": "107 93 82",
            "subtle-dark": "199 184 170",
            "default-light": "63 50 41",
            "default-dark": "245 238 230",
            "important-light": "45 24 16",
            "important-dark": "250 246 241",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Workflows",
                "separator": False,
                "items": [
                    {"title": "Dashboard", "icon": "dashboard", "link": "/"},
                    {"title": "Build", "icon": "construction", "link": "/build/"},
                    {"title": "Track", "icon": "track_changes", "link": "/track/"},
                    {"title": "Purchase", "icon": "local_shipping", "link": "/purchase/"},
                    {"title": "Sales", "icon": "point_of_sale", "link": "/sales/"},
                ],
            },
            {
                "title": "Catalogue",
                "separator": True,
                "items": [
                    {"title": "Brands", "icon": "label", "link": "/admin/inventory/brand/"},
                    {"title": "Products", "icon": "auto_awesome", "link": "/admin/inventory/product/"},
                    {"title": "Variants (palettes)", "icon": "palette", "link": "/admin/inventory/variant/"},
                    {"title": "Sellable SKUs", "icon": "qr_code_2", "link": "/admin/inventory/productvariant/"},
                    {"title": "Raw materials", "icon": "scatter_plot", "link": "/admin/inventory/rawmaterial/"},
                    {"title": "Suppliers", "icon": "store", "link": "/admin/inventory/supplier/"},
                ],
            },
            {
                "title": "Records",
                "separator": True,
                "items": [
                    {"title": "Projects", "icon": "folder_open", "link": "/admin/inventory/project/"},
                    {"title": "Production runs", "icon": "build", "link": "/admin/inventory/productionrun/"},
                    {"title": "Purchase orders", "icon": "shopping_cart", "link": "/admin/inventory/purchaseorder/"},
                    {"title": "Sales", "icon": "receipt_long", "link": "/admin/inventory/sale/"},
                    {"title": "Stock movements", "icon": "history", "link": "/admin/inventory/stockmovement/"},
                ],
            },
        ],
    },
}
