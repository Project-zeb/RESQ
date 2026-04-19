import pandas as pd 
import numpy as np 
from pathlib import Path 
from config.settings import SILVER_DIR, GOLD_DIR
def save_parquet(df, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    print(f"Saved: {path}")

def load_and_standardize_events():
    all_dfs = []

    for f in SILVER_DIR.glob("*_events_*.parquet"):
        df = pd.read_parquet(f)
        print(f"Loaded {f.name}: {len(df):,} rows")

        disaster_type = f.stem.split("_")[0]
        df = standardize_events(df, disaster_type)
        all_dfs.append(df)

    events_df = pd.concat(all_dfs, ignore_index=True)

    events_df = (
        events_df
        .groupby(['grid_id', 'event_time'])
        .agg({
            'lat': 'mean',
            'lon': 'mean',
            'target': 'max',
            'disaster_type': 'first'
        })
        .reset_index()
    )

    return events_df


def standardize_events(df, disaster_type):
    df = df.rename(columns={"latitude": "lat", "longitude": "lon"})

    df = df[
        (df['lat'] >= 6) & (df['lat'] <= 37) &
        (df['lon'] >= 68) & (df['lon'] <= 97)
    ]

    df['event_time'] = pd.to_datetime(df['event_time'], errors='coerce', utc=True)

    df = df[['lat', 'lon', 'event_time']].copy()
    df['disaster_type'] = disaster_type
    df['target'] = 1

    k = 5
    df['grid_lat'] = np.floor(df['lat'] * k) / k
    df['grid_lon'] = np.floor(df['lon'] * k) / k
    df['grid_id'] = (
        df['grid_lat'].round(3).astype(str) + '_' +
        df['grid_lon'].round(3).astype(str)
    )

    return df

def generate_negative_samples(events_df):
    neg_samples = []

    all_times = events_df['event_time'].drop_duplicates()

    for grid, group in events_df.groupby('grid_id'):
        event_times = group['event_time']

        n_neg = 5
        candidates = all_times.sample(n=n_neg * 2, replace=True)
        candidates = candidates[~candidates.isin(event_times)]

        if len(candidates) < n_neg:
            sampled_times = candidates.sample(n=n_neg, replace=True)
        else:
            sampled_times = candidates.head(n_neg)

        lat = group['lat'].iloc[0]
        lon = group['lon'].iloc[0]

        temp = pd.DataFrame({
            'grid_id': grid,
            'event_time': sampled_times,
            'lat': lat,
            'lon': lon,
            'target': 0,
            'disaster_type': 'none'
        })

        neg_samples.append(temp)

    neg_df = pd.concat(neg_samples, ignore_index=True)

    return neg_df

def build_event_dataset():
    events_df = load_and_standardize_events()
    neg_df = generate_negative_samples(events_df)

    final_events = pd.concat([events_df, neg_df], ignore_index=True)

    final_events = final_events.sort_values(['grid_id', 'event_time'])

    return final_events

def standardize_weather(df):
    df = df.copy()

    df = df.rename(columns={
        "latitude": "lat",
        "longitude": "lon",
        "temperature_2m": "temperature",
        "wind_speed_10m": "wind_speed"
    })

    df = df[
        (df['lat'] >= 6) & (df['lat'] <= 37) &
        (df['lon'] >= 68) & (df['lon'] <= 97)
    ]

    df['event_time'] = pd.to_datetime(df['event_time'], utc=True)
    df['date'] = df['event_time'].dt.floor('D')

    
    k = 5
    df['grid_lat'] = np.floor(df['lat'] * k) / k
    df['grid_lon'] = np.floor(df['lon'] * k) / k
    df['grid_id'] = (
        df['grid_lat'].round(3).astype(str) + '_' +
        df['grid_lon'].round(3).astype(str)
    )

    
    for col in ['temperature', 'precipitation', 'wind_speed']:
        if col not in df.columns:
            df[col] = np.nan

    return df[['grid_id', 'date',
               'temperature',
               'precipitation',
               'wind_speed']]

def build_weather_dataset():
    all_dfs = []

    for f in SILVER_DIR.glob("*_events_*.parquet"):
        df = pd.read_parquet(f)
        print(f"Loaded {f.name}: {len(df):,} rows")

        weather_df = standardize_weather(df)
        all_dfs.append(weather_df)

    weather_df = pd.concat(all_dfs, ignore_index=True)

    weather_df = (
        weather_df
        .groupby(['grid_id', 'date'])
        .agg({
            'temperature': 'mean',
            'precipitation': 'sum',
            'wind_speed': 'max'
        })
        .reset_index()
    )
    print("\nWeather Missingness:")
    print(weather_df.isna().mean())
    weather_df = weather_df.sort_values(['grid_id', 'date'])

    return weather_df

def run_pipeline():
    print("\n--- Building Event Dataset ---")
    events_df = build_event_dataset()

    print("\n--- Building Weather Dataset ---")
    weather_df = build_weather_dataset()

    print("\n--- Saving Outputs ---")
    save_parquet(events_df, GOLD_DIR / "events_dataset.parquet")
    save_parquet(weather_df, GOLD_DIR / "weather_dataset.parquet")

    print("\nPipeline Complete")

    return events_df, weather_df

if __name__ == "__main__" :
    run_pipeline()