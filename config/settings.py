"""
Django settings for the e-commerce project (Phase 1 MVP).
"""
import os
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

def env(key, default=None):
    return os.environ.get(key, default)

SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-secret-key-change-me")
DEBUG = env("DJANGO_DEBUG", "True") == "True"
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "jazzmin",  # must come before django.contrib.admin to override its templates
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "django_filters",
    "corsheaders",

    # local apps
    "apps.accounts",
    "apps.catalog",
    "apps.cart",
    "apps.orders",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "ecommerce"),
        "USER": env("POSTGRES_USER", "ecommerce"),
        "PASSWORD": env("POSTGRES_PASSWORD", "ecommerce"),
        "HOST": env("POSTGRES_HOST", "db"),
        "PORT": env("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTH_USER_MODEL = "accounts.User"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    # Without this, nothing stops a script from hammering /register/ or
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "180/min",
        # tighter limits on the specific actions spam would target
        "register": "5/hour",
        "product_write": "30/hour",
        "image_upload": "20/hour",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

# Render terminates HTTPS at its proxy and forwards plain HTTP to Django, so
# without this Django builds http:// URLs and browsers block them as mixed
# content on the https:// site.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Product images. Render's free disk is wiped on every redeploy/sleep, so
# uploaded files vanish. When CLOUDINARY_URL is set (production), uploads go
# to Cloudinary instead and come back as permanent https:// URLs. Locally
# (no CLOUDINARY_URL) images keep using the plain ./media folder.
if env("CLOUDINARY_URL"):
    INSTALLED_APPS += ["cloudinary_storage", "cloudinary"]
    STORAGES = {
        "default": {"BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }

# CORS: wide open in local dev (DEBUG=True); in production only allow
# *.onrender.com subdomains (your frontend static site + backend itself),
# since CORS_ALLOW_ALL_ORIGINS = DEBUG alone would silently block every
# frontend request once DEBUG=False in production.
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://.*\.onrender\.com$",
]
CORS_ALLOW_ALL_ORIGINS = DEBUG

# Admin theme (Jazzmin) — the admin itself still has no custom CSS of its
# own; this is a drop-in package that reskins the built-in Django admin
# templates, colors loosely matched to the storefront's teal/saffron look.
JAZZMIN_SETTINGS = {
    "site_title": "Souk Admin",
    "site_header": "Souk",
    "site_brand": "Souk Admin",
    "welcome_sign": "Welcome to the Souk back office",
    "copyright": "Souk",
    "show_sidebar": True,
    "navigation_expanded": True,
    "icons": {
        "catalog.Product": "fas fa-box",
        "catalog.Category": "fas fa-tags",
        "catalog.Review": "fas fa-star",
        "orders.Order": "fas fa-receipt",
        "cart.Cart": "fas fa-shopping-cart",
        "accounts.User": "fas fa-user",
        "accounts.Address": "fas fa-map-marker-alt",
    },
}
JAZZMIN_UI_TWEAKS = {
    "navbar": "navbar-dark",
    "accent": "accent-teal",
    "theme": "flatly",
}

# By default Django only prints crash tracebacks to the console when
# DEBUG=True — in production (DEBUG=False) it silently swallows them unless
# explicitly configured like this, which made the image-upload 500 error
# invisible in Render's logs. This makes every unhandled error visible.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}

# Redis / Celery (used from Phase 2 onward, wired now so Docker stack is ready)
REDIS_URL = env("REDIS_URL", "redis://redis:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
