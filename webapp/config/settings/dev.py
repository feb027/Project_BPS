"""Setelan pengembangan (lokal)."""
from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]  # bebas saat dev di LAN

# Email ke konsol saat dev
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
