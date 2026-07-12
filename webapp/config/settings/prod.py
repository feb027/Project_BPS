"""Setelan produksi (laptop host di LAN)."""
from .base import *  # noqa: F401,F403

DEBUG = False

# Keamanan dasar (django-expert: security checklist)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

# Public deployment is served through HTTPS by Caddy.
# Do not force SECURE_SSL_REDIRECT here; Caddy owns HTTP -> HTTPS redirects.
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Shared cache across gunicorn workers (LocMemCache is per-process, so the
# @cache_page on the catalog/time-series endpoints misses on every worker
# rotation -> 30s first-hit every request). DatabaseCache is shared by all
# workers through PostgreSQL. Requires `manage.py createcachetable`.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}
