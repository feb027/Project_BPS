#!/usr/bin/env python
"""Utilitas command-line Django untuk tugas administratif."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Tidak bisa mengimpor Django. Pastikan sudah terpasang dan "
            "virtualenv aktif."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
