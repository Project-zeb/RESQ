# src/core/storage.py
import logging
import pandas as pd
from pathlib import Path
from config.settings import BRONZE_DIR, SILVER_DIR, GOLD_DIR
from src.core.utils import make_disaster_path


logger = logging.getLogger(__name__)


def read_csv(path: str | Path, **kwargs) -> pd.DataFrame:
    """Read CSV into a DataFrame."""
    logger.info(f"Reading CSV: {path}")
    return pd.read_csv(path, **kwargs)


def read_parquet(path: str | Path, **kwargs) -> pd.DataFrame:
    """Read Parquet into a DataFrame."""
    logger.info(f"Reading Parquet: {path}")
    return pd.read_parquet(path, **kwargs)


def save_parquet(
    df: pd.DataFrame,
    stage: str,
    disaster_type: str,
    name: str,
    ts_suffix: bool = True,
) -> Path:
    """
    Save a DataFrame to a stage‑specific Parquet file with timestamped suffix.

    Args:
        stage: "bronze", "silver", "gold"
        disaster_type: "cyclone", "earthquake", etc.
        name: table name (e.g., "events", "enriched")
        ts_suffix: if True, append current timestamp
    """
    timestamp = None
    if ts_suffix:
        timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")

    path = make_disaster_path(
        stage=stage,
        disaster_type=disaster_type,
        name=name,
        suffix=timestamp,
        ext=".parquet",
    )

    logger.info(f"Saving Parquet: {path} | shape={df.shape}")
    df.to_parquet(path, index=False)
    return path


def save_csv(
    df: pd.DataFrame,
    stage: str,
    disaster_type: str,
    name: str,
    ts_suffix: bool = True,
) -> Path:
    """Same as save_parquet but for CSV."""
    timestamp = None
    if ts_suffix:
        timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")

    path = make_disaster_path(
        stage=stage,
        disaster_type=disaster_type,
        name=name,
        suffix=timestamp,
        ext=".csv",
    )

    logger.info(f"Saving CSV: {path} | shape={df.shape}")
    df.to_csv(path, index=False)
    return path


def list_files(dir_path: str | Path, pattern: str = "*") -> list[Path]:
    """List files in a directory matching a glob pattern."""
    dir_path = Path(dir_path)
    files = sorted(dir_path.glob(pattern))
    logger.info(f"Found {len(files)} files matching {pattern} in {dir_path}")
    return files