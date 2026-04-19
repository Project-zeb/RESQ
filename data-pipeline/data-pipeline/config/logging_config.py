# config/logging_config.py
import logging
from pathlib import Path

from config.settings import LOG_DIR

def setup_logging():
    """Set up logging with file + console handlers and consistent format."""
    LOG_DIR.mkdir(exist_ok=True)

    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(lineno)4s | %(message)s"
    formatter = logging.Formatter(fmt)

    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Remove any existing handlers (e.g., from previous calls)
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler
    file_handler = logging.FileHandler(LOG_DIR / "pipeline.log")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)