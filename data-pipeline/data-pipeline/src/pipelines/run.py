# src/pipelines/run.py
from config.logging_config import setup_logging
from src.ingestion.raw_sources import load_all_disasters
from src.core.storage import save_parquet
from src.quality.data_quality_check import run_quality_checks
setup_logging()


def run_bronze():
    disaster_dfs = load_all_disasters()

    for disaster_type, df in disaster_dfs.items():
        save_parquet(
            df=df,
            stage="bronze",
            disaster_type=disaster_type,
            name="events",
        )
    
    # NEW: Run quality checks
    print("\n Running data quality checks...")
    run_quality_checks()


if __name__ == "__main__":
    run_bronze()

    