"""
Data Quality & Integrity Checks - Latest Files Only
"""
import pandas as pd
import logging
from pathlib import Path
from typing import Dict, List
from src.core.storage import read_parquet
from datetime import datetime

logger = logging.getLogger(__name__)

def get_latest_file_per_type(bronze_path: Path = Path("data/bronze")) -> Dict[str, Path]:
    """Get the most recent file for each disaster type"""
    latest_files = {}
    
    # Group files by disaster type (cyclone_events_*, earthquake_events_*)
    files_by_type = {}
    for parquet_file in bronze_path.glob("*_events_*.parquet"):
        # Extract disaster type: cyclone_events_20260327_021017.parquet → "cyclone"
        disaster_type = parquet_file.stem.split("_events_")[0]
        files_by_type.setdefault(disaster_type, []).append(parquet_file)
    
    # Get latest file per type
    for disaster_type, files in files_by_type.items():
        if files:
            latest_files[disaster_type] = max(files, key=lambda f: f.stat().st_mtime)
            logger.debug(f"Latest {disaster_type}: {latest_files[disaster_type].name}")
    
    return latest_files

def analyze_bronze_quality(bronze_path: Path = Path("data/bronze")) -> Dict:
    """Analyze bronze layer - LATEST files only"""
    latest_files = get_latest_file_per_type(bronze_path)
    results = {}
    
    for disaster_type, latest_file in latest_files.items():
        df = read_parquet(latest_file)
        
        results[disaster_type] = {
            "rows": len(df),
            "cols": len(df.columns),
            "file": latest_file.name,
            "missing_rate": df.isnull().mean().mean(),
            "lat_null": df["lat"].isnull().sum(),
            "lon_null": df["lon"].isnull().sum(),
            "time_null": df["event_time"].isnull().sum(),
            "time_range": f"{df['event_time'].min()} to {df['event_time'].max()}",
            "duplicates": df.duplicated().sum(),
            "lat_range": f"{df['lat'].min():.2f} to {df['lat'].max():.2f}",
            "lon_range": f"{df['lon'].min():.2f} to {df['lon'].max():.2f}",
        }
        
        logger.info(f"✅ {disaster_type}: {len(df)} rows from {latest_file.name}")
    
    return results

def run_quality_checks() -> None:
    """Main quality runner - analyzes LATEST files only"""
    bronze_results = analyze_bronze_quality()
    
    print("\n" + "="*70)
    print("BRONZE LAYER QUALITY REPORT (LATEST FILES)")
    print("="*70)
    
    total_rows = sum(r["rows"] for r in bronze_results.values())
    print(f" TOTAL EVENTS: {total_rows:,}")
    
    for disaster, metrics in bronze_results.items():
        print(f"\n {disaster.upper()}:")
        print(f"    File: {metrics['file']}")
        print(f"   Rows: {metrics['rows']:,}")
        print(f"    Null lat/lon: {metrics['lat_null']:,}")
        print(f"    Time range: {metrics['time_range']}")
        print(f"    Duplicates: {metrics['duplicates']}")
    
    # Alerts
    zero_rows = [k for k,v in bronze_results.items() if v["rows"] == 0]
    if zero_rows:
        print(f"\n  ZERO ROWS: {', '.join(zero_rows)}")
    
    high_nulls = [k for k,v in bronze_results.items() 
                  if v["lat_null"] / max(1, v["rows"]) > 0.1]
    if high_nulls:
        print(f"\nHIGH NULLS (>10%): {', '.join(high_nulls)}")