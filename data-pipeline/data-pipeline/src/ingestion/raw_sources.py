# src/ingestion/raw_sources.py
import logging
import pandas as pd
from typing import Optional, Literal

from config.settings import RAW_FILES, MIN_DATE, MAX_DATE, EVENT_TIME_GRANULARITY, DISASTER_TYPES


logger = logging.getLogger(__name__)


def load_cyclones(min_date: str = MIN_DATE, max_date: str = MAX_DATE) -> pd.DataFrame:
    path = RAW_FILES["cyclones"]
    logger.info(f"Loading cyclones from {path}")

    df = pd.read_csv(path, low_memory=False)

    # Clean column names
    df.columns = df.columns.str.strip()
    df.columns = df.columns.str.replace(" ", "_", regex=False)
    df.columns = df.columns.str.replace("\t", "_", regex=False)
    df.columns = df.columns.str.replace("\n", "", regex=False)
    df.columns = df.columns.str.replace(".*ISO_TIME.*", "ISO_TIME", regex=True)

    # Build event_time early
    df["event_time"] = pd.to_datetime(df["ISO_TIME"], errors="coerce")

    # Keep cols including event_time
    keep_cols = [
        "SID", "SEASON", "NUMBER", "BASIN", "SUBBASIN", "NAME", "NATURE",
        "LAT", "LON", "WMO_WIND", "WMO_PRES",
        "USA_LAT", "USA_LON", "USA_WIND", "USA_PRES",
        "NEWDELHI_LAT", "NEWDELHI_LON", "NEWDELHI_WIND", "NEWDELHI_PRES",
        "event_time",          # ← add this line
    ]
    df = df[keep_cols].copy()

    # Unify lat/lon
    df["lat"] = pd.to_numeric(df["LAT"], errors="coerce")
    df["lon"] = pd.to_numeric(df["LON"], errors="coerce")

    # Filter 2007–2017
    df = df.loc[
        (df["event_time"] >= min_date)
        & (df["event_time"] <= max_date)
    ].copy()

    # Hourly grid + disaster type
    df["event_hour"] = df["event_time"].dt.floor(EVENT_TIME_GRANULARITY)
    df["disaster_type"] = "cyclone"

    # Final schema
    df_out = df[[
        "SID",
        "NAME", "NATURE",
        "lat", "lon",
        "WMO_WIND", "WMO_PRES",
        "event_time", "event_hour",
        "disaster_type",
    ]].copy()

    logger.info(f"Cyclones loaded: {df_out.shape} after filtering {min_date}–{max_date}")
    return df_out


def load_earthquakes(min_date: str = MIN_DATE, max_date: str = MAX_DATE) -> pd.DataFrame:
    path = RAW_FILES["earthquakes"]
    logger.info(f"Loading earthquakes from {path}")

    df = pd.read_csv(path)

    # 1. Keep important cols
    keep_cols = [
        "time", "latitude", "longitude", "depth", "mag", "magType",
        "rms", "net", "id", "place", "type",
    ]
    df = df[keep_cols].copy()

    # 2. Unify lat/lon/mag
    df["lat"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["lon"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["magnitude"] = pd.to_numeric(df["mag"], errors="coerce")

    # 3. Build event_time from 'time'
    df["event_time"] = pd.to_datetime(df["time"], errors="coerce")

    # 4. Filter window
    df = df.loc[
        (df["event_time"] >= min_date)
        & (df["event_time"] <= max_date)
    ].copy()

    # 5. Hourly grid + type
    df["event_hour"] = df["event_time"].dt.floor(EVENT_TIME_GRANULARITY)
    df["disaster_type"] = "earthquake"

    df_out = df[[
        "id",
        "place", "type",
        "lat", "lon", "depth", "magnitude",
        "magType", "rms", "event_time", "event_hour", "disaster_type",
    ]].copy()

    logger.info(f"Earthquakes loaded: {df_out.shape} after filtering {min_date}–{max_date}")
    return df_out


def load_landslides(min_date: str = MIN_DATE, max_date: str = MAX_DATE) -> pd.DataFrame:
    path = RAW_FILES["landslides"]
    logger.info(f"Loading landslides from {path}")

    df = pd.read_csv(path)

    keep_cols = [
        "event_id", "event_date", "event_time", "event_title",
        "landslide_category", "landslide_trigger", "landslide_size",
        "landslide_setting",
        "fatality_count", "injury_count",
        "latitude", "longitude",
    ]
    df = df[keep_cols].copy()

    # Convert event_date to datetime
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")

    # If event_time exists as string, combine with event_date
    if "event_time" in df.columns and df["event_time"].notna().any():
        # 1. Ensure event_time is string
        df["event_time"] = df["event_time"].astype(str)

        # 2. Replace colon pattern to make it parseable
        df["event_time"] = df["event_time"].str.replace(":", ":", regex=False)
        # Simple: just parse as HH:MM or HH:MM:SS
        df["event_time"] = pd.to_datetime(
            df["event_date"].dt.strftime("%Y-%m-%d") + " " + df["event_time"],
            errors="coerce",
        )
    else:
        # If no event_time, use only event_date as event_time
        df["event_time"] = df["event_date"]

    # 2. Ensure numeric lat/lon
    df["lat"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["lon"] = pd.to_numeric(df["longitude"], errors="coerce")

    # 3. Filter to 2007–2017
    df = df.loc[
        (df["event_time"] >= min_date)
        & (df["event_time"] <= max_date)
    ].copy()

    # 4. Hourly grid + type
    df["event_hour"] = df["event_time"].dt.floor(EVENT_TIME_GRANULARITY)
    df["disaster_type"] = "landslide"

    df_out = df[[
        "event_id", "event_title", "landslide_category", "landslide_trigger",
        "fatality_count", "injury_count",
        "lat", "lon",
        "event_time", "event_hour", "disaster_type",
    ]].copy()

    logger.info(f"Landslides loaded: {df_out.shape} after filtering {min_date}–{max_date}")
    return df_out


def load_fire(min_date: str = MIN_DATE, max_date: str = MAX_DATE) -> pd.DataFrame:
    path = RAW_FILES["fires"]
    logger.info(f"Loading MODIS fire from {path}")

    df = pd.read_csv(path)

    keep_cols = [
        "latitude", "longitude",
        "brightness", "scan", "track", "satellite", "instrument",
        "confidence", "bright_t31", "frp", "daynight", "type",
        "acq_date", "acq_time",
    ]
    df = df[keep_cols].copy()

    # 1. Ensure acq_date is datetime
    df["acq_date"] = pd.to_datetime(df["acq_date"], errors="coerce")

    # 2. Parse HHMM acq_time safely
    if "acq_time" in df.columns:
        df["acq_time"] = df["acq_time"].astype(str).str.zfill(4).replace("nan", "")
        df["hh"] = df["acq_time"].str[:2]
        df["mm"] = df["acq_time"].str[2:4]
        df["hh"] = pd.to_numeric(df["hh"], errors="coerce").astype("Int64")
        df["mm"] = pd.to_numeric(df["mm"], errors="coerce").astype("Int64")

        # Build HHMMSS as timedelta and add to acq_date
        df["event_time"] = df["acq_date"] + pd.to_timedelta(
            df["hh"].astype(str) + "H" + df["mm"].astype(str) + "M",
            errors="coerce",
        )
    else:
        df["event_time"] = df["acq_date"]

    # 3. Lat/lon/FRP
    df["lat"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["lon"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["frp"] = pd.to_numeric(df["frp"], errors="coerce")

    # 4. Filter 2007–2017
    df = df.loc[
        (df["event_time"] >= min_date)
        & (df["event_time"] <= max_date)
    ].copy()

    # 5. Hourly grid + type
    df["event_hour"] = df["event_time"].dt.floor(EVENT_TIME_GRANULARITY)
    df["disaster_type"] = "fire"

    df_out = df[[
        "brightness", "scan", "track", "satellite", "instrument",
        "confidence", "bright_t31", "frp", "daynight", "type",
        "lat", "lon",
        "event_time", "event_hour", "disaster_type",
    ]].copy()

    logger.info(f"Fire loaded: {df_out.shape} after filtering {min_date}–{max_date}")
    return df_out


def load_all_disasters(
    min_date: str = MIN_DATE,
    max_date: str = MAX_DATE,
    disaster_types: Optional[list[Literal["cyclone", "earthquake", "landslide", "fire"]]] = None,
) -> dict[str, pd.DataFrame]:
    if disaster_types is None:
        disaster_types = ["cyclone", "earthquake", "landslide", "fire"]

    loaders = {
        "cyclone": load_cyclones,
        "earthquake": load_earthquakes,
        "landslide": load_landslides,
        "fire": load_fire,
    }
    dfs = {}
    for d in disaster_types:
        if d not in loaders:
            raise ValueError(f"Unknown disaster type: {d}")
        dfs[d] = loaders[d](min_date=min_date, max_date=max_date)
    return dfs