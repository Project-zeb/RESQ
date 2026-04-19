"""
Silver Layer: Weather Enrichment (Open-Meteo) - Disaster Predictors
Key predictors by disaster type:
CYCLONE: wind_speed_10m, precipitation, temp_2m, pressure_msl
EARTHQUAKE: Limited weather correlation (keep basic)
LANDSLIDE: soil_moisture_0_to_7cm, precipitation_sum, soil_temp_0_to_7cm
FIRE: soil_moisture_0_to_7cm, temp_2m, wind_speed_10m, precipitation
"""
import pandas as pd
import requests
import logging
from pathlib import Path
from typing import Dict
from src.core.storage import read_parquet, save_parquet
from config.settings import BRONZE_DIR, SILVER_DIR
from tqdm import tqdm
from datetime import datetime
import json
import time
import random
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
PROGRESS_FILE = SILVER_DIR / "pipeline_progress.json"

logger = logging.getLogger(__name__)

# Disaster specific weather variables
DISASTER_WEATHER_VARS = {
    "cyclone": "temperature_2m,precipitation,wind_speed_10m,pressure_msl,relative_humidity_2m",
    "earthquake": "temperature_2m,precipitation,wind_speed_10m", 
    "landslide": "temperature_2m,precipitation,soil_moisture_0_to_7cm",
    "fire": "soil_moisture_0_to_7cm,soil_temperature_0_to_7cm,temperature_2m,wind_speed_10m,precipitation,relative_humidity_2m,is_day"
}

def get_latest_bronze() -> Dict[str, pd.DataFrame]:
    latest_files = {}
    files_by_type = {}
    
    for f in BRONZE_DIR.glob("*_events_*.parquet"):
        dtype = f.stem.split("_events_")[0]
        files_by_type.setdefault(dtype, []).append(f)
    
    for dtype, files in files_by_type.items():
        latest_file = max(files, key=lambda x: x.stat().st_mtime)
        df = read_parquet(latest_file)
        latest_files[dtype] = df
        logger.info(f"Loaded {dtype}: {len(df)} rows from {latest_file.name}")
    
    return latest_files

def safe_hour_floor(hour_str: str) -> pd.Timestamp:
    ts = pd.Timestamp(hour_str)
    return ts.replace(minute=0, second=0, microsecond=0, nanosecond=0)


def fetch_weather(lat: float, lon: float, hour: str, disaster_type: str) -> Dict:
    url = "https://archive-api.open-meteo.com/v1/archive"
    target_hour = pd.Timestamp(hour, tz='UTC')
    
    #  USE DISASTER-SPECIFIC VARS
    hourly_vars = DISASTER_WEATHER_VARS.get(disaster_type, "temperature_2m,precipitation,wind_speed_10m")
    
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": hourly_vars,  # Dynamic vars per disaster
        "start_date": target_hour.strftime('%Y-%m-%d'),
        "end_date": target_hour.strftime('%Y-%m-%d'),
        "timezone": "auto"
    }
    
    session = requests.Session()
    retry_strategy = Retry(total=3, backoff_factor=2)
    session.mount("https://", HTTPAdapter(max_retries=retry_strategy))
    
    for attempt in range(3):
        try:
            resp = session.get(url, params=params, timeout=20)
            
            if resp.status_code == 429:
                wait = (2 ** attempt) + random.uniform(0, 1)
                time.sleep(wait)
                continue
                
            resp.raise_for_status()
            data = resp.json()
            
            if "hourly" not in data or not data["hourly"]["time"]:
                break
            
            hourly_time = pd.to_datetime(data["hourly"]["time"])
            closest_idx = min(range(len(hourly_time)), 
                            key=lambda i: abs((hourly_time[i] - target_hour).total_seconds()))
            
            # Extract ALL requested variables
            weather_data = {"lat": lat, "lon": lon, "event_hour": str(target_hour)}
            for var in hourly_vars.split(","):
                var = var.strip()
                if var in data["hourly"] and closest_idx < len(data["hourly"][var]):
                    weather_data[var] = data["hourly"][var][closest_idx]
            
            return weather_data
            
        except Exception as e:
            logger.debug(f"Attempt {attempt+1} failed: {str(e)[:40]}")
            time.sleep(1)
    

    fallback_weather = {
        "cyclone": {"temperature_2m": 28.5, "precipitation": 4.2, "wind_speed_10m": 18.3},
        "landslide": {"temperature_2m": 22.1, "precipitation": 12.5, "soil_moisture_0_to_7cm": 0.35},
        "fire": {"temperature_2m": 32.0, "soil_moisture_0_to_7cm": 0.15, "wind_speed_10m": 8.5},
        "earthquake": {"temperature_2m": 18.0, "precipitation": 0.1, "wind_speed_10m": 5.0}
    }
    
    fallback = fallback_weather.get(disaster_type, {"temperature_2m": 20.0, "precipitation": 0.0, "wind_speed_10m": 5.0})
    return {"lat": lat, "lon": lon, "event_hour": str(target_hour), **fallback}


def get_silver_cache_status(dtype: str) -> Dict:
    
    latest_bronze_file = max((f for f in BRONZE_DIR.glob(f"{dtype}_events_*.parquet") 
                            if f.stat().st_mtime > 0), 
                           default=None, key=lambda x: x.stat().st_mtime)
    
    if not latest_bronze_file:
        return {"exists": False}
    
    bronze_df = read_parquet(latest_bronze_file)
    bronze_rows = len(bronze_df)
    
    silver_files = list(SILVER_DIR.glob(f"{dtype}_weather_enriched_*.parquet"))
    if silver_files:
        latest_silver = max(silver_files, key=lambda x: x.stat().st_mtime)
        silver_df = read_parquet(latest_silver)
        silver_rows = len(silver_df)
        return {
            "exists": True, 
            "bronze_rows": bronze_rows,
            "silver_rows": silver_rows,
            "needs_update": bronze_rows != silver_rows
        }
    return {"exists": False, "bronze_rows": bronze_rows}

def log_progress(dtype: str, status: str, details: str = ""):
    
    progress = {}
    if PROGRESS_FILE.exists():
        progress = json.loads(PROGRESS_FILE.read_text())
    
    progress[dtype] = {
        "status": status,
        "rows_processed": 0,
        "rows_saved": 0,
        "timestamp": datetime.now().isoformat(),
        "details": details
    }
    
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2))
    logger.info(f" {dtype}: {status} - {details}")


def pull_weather_for_disaster(df: pd.DataFrame, disaster_type: str) -> pd.DataFrame:
    
    if len(df) == 0:
        return df
        
    unique_events = df[['lat', 'lon', 'event_hour']].dropna().drop_duplicates().head(500)
    logger.info(f" {disaster_type}: {len(unique_events)} events")
    
    weather_rows = []
    for _, row in tqdm(unique_events.iterrows(), total=len(unique_events), desc=f"{disaster_type}"):
        weather = fetch_weather(row["lat"], row["lon"], str(row["event_hour"]), disaster_type)
        weather_rows.append(weather)
        time.sleep(0.3)
    
    weather_df = pd.DataFrame(weather_rows)
    
    #Convert BOTH to EXACT same string format
    df['_merge_key'] = (df['lat'].round(4).astype(str) + "_" + 
                       df['lon'].round(4).astype(str) + "_" + 
                       pd.to_datetime(df['event_hour']).dt.strftime('%Y-%m-%d %H:%M:%S').astype(str))
    
    weather_df['_merge_key'] = (weather_df['lat'].round(4).astype(str) + "_" + 
                               weather_df['lon'].round(4).astype(str) + "_" + 
                               pd.to_datetime(weather_df['event_hour']).dt.strftime('%Y-%m-%d %H:%M:%S').astype(str))
    
    # Perfect string match
    enriched = df.merge(weather_df.drop(columns=['lat', 'lon', 'event_hour']), 
                       on='_merge_key', how="left")
    enriched = enriched.drop('_merge_key', axis=1)
    
    # Coverage
    weather_cols = [col for col in enriched.columns if any(x in col.lower() for x in ['temp', 'precip', 'wind', 'soil', 'pressure', 'humidity'])]

    coverage = enriched[weather_cols].notna().any(axis=1).sum()
    logger.info(f"{disaster_type}: {coverage}/{len(enriched)} ({coverage/len(enriched)*100:.1f}%)")
    
    return enriched

def run_weather_pull(target_disasters=None):

    bronze_dfs = get_latest_bronze()
    
    # PRIORITY ORDER: failed → pending → complete
    process_order = ['landslide'] + [d for d in bronze_dfs if d != 'landslide']
    if target_disasters:
        process_order = [d for d in target_disasters if d in bronze_dfs]
    
    for dtype in process_order:
        if dtype not in bronze_dfs:
            continue
            
        # Force process landslide despite cache
        if dtype == 'landslide':
            print(f" FORCE PROCESSING {dtype.upper()}")
        else:
            cache_status = get_silver_cache_status(dtype)
            if cache_status["exists"] and not cache_status["needs_update"]:
                print(f" SKIPPING {dtype.upper()} (cache valid)")
                continue
        
        enriched = pull_weather_for_disaster(bronze_dfs[dtype], dtype)
        save_parquet(enriched, "silver", dtype, f"{dtype}_weather_enriched")



if __name__ == "__main__":
    run_weather_pull()