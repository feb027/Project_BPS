"""Setelan produksi (laptop host di LAN)."""
from .base import *  # noqa: F401,F403

DEBUG = False

# Keamanan dasar (django-expert: security checklist)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

# Karena di LAN (http, bukan https), biarkan cookie non-secure.
# Aktifkan ini bila nanti pakai HTTPS:
# SECURE_SSL_REDIRECT = True
# SESSION_COOKIE_SECURE = True
# CSRF_COOKIE_SECURE = True
