import os

from dotenv import load_dotenv

load_dotenv()


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "internal_api.settings")
    host = os.getenv("INTERNAL_API_HOST", "0.0.0.0")
    port = os.getenv("INTERNAL_API_PORT", "5100")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django is not installed. Install it with: pip install -r requirements.txt"
        ) from exc
    execute_from_command_line(["manage.py", "runserver", f"{host}:{port}"])


if __name__ == "__main__":
    main()
