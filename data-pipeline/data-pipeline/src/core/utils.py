# src/core/utils.py
import logging
from typing import Iterable, Iterator, Dict, Any
from pathlib import Path

from config.settings import ROOT_DIR, BRONZE_DIR, SILVER_DIR, GOLD_DIR, TEMP_DIR


logger = logging.getLogger(__name__)


def chunker(iterable: Iterable, chunk_size: int) -> Iterator[list]:
    """Split an iterable into chunks of size `chunk_size`."""
    iterator = iter(iterable)
    while True:
        chunk = []
        try:
            for _ in range(chunk_size):
                chunk.append(next(iterator))
        except StopIteration:
            if chunk:
                yield chunk
            break
        yield chunk


def resolve_path(path: str | Path) -> Path:
    """Resolve a string path relative to ROOT_DIR."""
    if isinstance(path, str):
        path = Path(path)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def get_disaster_dir(stage: str) -> Path:
    """Return the base directory for a given stage (bronze, silver, gold)."""
    if stage == "bronze":
        return BRONZE_DIR
    elif stage == "silver":
        return SILVER_DIR
    elif stage == "gold":
        return GOLD_DIR
    elif stage == "temp":
        return TEMP_DIR
    else:
        raise ValueError(f"Unknown stage: {stage}")


def make_disaster_path(
    stage: str,
    disaster_type: str,
    name: str,
    suffix: str = "",
    ext: str = ".parquet",
) -> Path:
    """Make a standardized path for a stage/disaster table."""
    base_dir = get_disaster_dir(stage)
    base_dir.mkdir(exist_ok=True)
    if suffix:
        suffix = "_" + suffix
    return base_dir / f"{disaster_type}_{name}{suffix}{ext}"