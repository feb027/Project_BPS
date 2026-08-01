"""Setelan pengembangan (lokal)."""
from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]  # bebas saat dev di LAN

# Email ke konsol saat dev
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Dummy cache: dev + pytest share this settings module, and LocMemCache
# persists across TestCase classes in one process — a cached response from an
# earlier test (e.g. CatalogAPIView's @cache_page(60)) makes later tests read
# stale data (order-dependent flakes). DummyCache keeps every test fresh.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}
