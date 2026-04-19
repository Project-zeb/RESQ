from pathlib import Path

# Paths
ROOT_DIR = Path(__file__).parent.parent  # config/ data-pipeline/
DATA_DIR = ROOT_DIR / "data"
LOG_DIR = ROOT_DIR / "logs"
RAW_DIR  = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR   = DATA_DIR / "gold"
TEMP_DIR   = DATA_DIR / "temp"

RAW_DIR = DATA_DIR / "raw"

RAW_FILES = {
    "cyclones": RAW_DIR / "cyclones.csv",
    "earthquakes": RAW_DIR / "earthquakes.csv",
    "landslides": RAW_DIR / "landslides.csv",
    "fires": RAW_DIR / "fires.csv",   # or whatever your file is named
    "weather_dir": RAW_DIR / "weather_2007_2017",  # folder with 11 parquet files
}


# APIs
OPEN_METEO_BASE_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_PARAMS = {
    "models": "auto",
    "cell_selection": "land",
    "elevation": "auto",  # use land cells + auto elevation
}

# Batching
API_BATCH_SIZE = 1000          # max rows per request to avoid hitting 10k/day
API_DAILY_LIMIT = 9000         # leave headroom
MAX_RETRIES = 3
BACKOFF_BASE = 2               # seconds for exponential backoff

# Date windows (for backfill + streaming window)
MIN_DATE = "2007-01-01"
MAX_DATE = "2017-12-31"
EVENT_TIME_GRANULARITY = "h"      
# Disaster types
DISASTER_TYPES = ["cyclone", "earthquake", "landslide", "fire"]

# Features (for gold)
LAGS_HOURS = [1, 3, 6, 12, 24]
LUMS_COLS = ["temperature", "precipitation"]