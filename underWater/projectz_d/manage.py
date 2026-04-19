#!/usr/bin/env python
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "projectz.settings")
    if "runserver" in sys.argv:
        try:
            from projectz.autostart import start_internal_api_if_needed

            start_internal_api_if_needed()
        except Exception:
            pass
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django is not installed. Install it with: pip install -r requirements.txt"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
