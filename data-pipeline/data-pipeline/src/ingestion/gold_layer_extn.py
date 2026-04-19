import pandas as pd 
import numpy as np 
from pathlib import Path 
from config.settings import SILVER_DIR, GOLD_DIR

def merge_events_weather(events_df, weather_df):
    events_df = events_df.copy()
    weather_df = weather_df.copy()

    
    events_df = events_df.sort_values(['event_time', 'grid_id']).reset_index(drop=True)
    weather_df = weather_df.sort_values(['date', 'grid_id']).reset_index(drop=True)

    merged_df = pd.merge_asof(
        events_df,
        weather_df,
        left_on='event_time',
        right_on='date',
        by='grid_id',
        direction='backward'
    )

    merged_df = merged_df.drop(columns=['date'])

    return merged_df

def add_missing_flags(df):
    df = df.copy()

    weather_cols = ['temperature', 'precipitation', 'wind_speed']

    for col in weather_cols:
        df[f'{col}_missing'] = df[col].isna().astype(int)

    return df

def validate_merged_data(df):
    print("\n--- Validation Report ---")

    print("\nMissingness:")
    print(df.isna().mean())

    print("\nTarget Distribution:")
    print(df['target'].value_counts(normalize=True))

    weather_cols = ['temperature', 'precipitation', 'wind_speed']
    coverage = df[weather_cols].notna().any(axis=1).mean()

    print(f"\nRows with ANY weather info: {coverage:.2%}")

    if 'event_time' in df.columns:
        print("\nTime Range:")
        print(df['event_time'].min(), "→", df['event_time'].max())

    print("\nValidation Complete\n")

def build_final_training_dataset(events_path, weather_path):
    print("\n--- Loading Data ---")

    events_df = pd.read_parquet(events_path)
    weather_df = pd.read_parquet(weather_path)

    print(f"Events: {len(events_df):,} rows")
    print(f"Weather: {len(weather_df):,} rows")

    print("\n--- Merging Datasets ---")
    merged_df = merge_events_weather(events_df, weather_df)

    print("\n--- Adding Missing Flags ---")
    merged_df = add_missing_flags(merged_df)

    print("\n--- Running Validation ---")
    validate_merged_data(merged_df)

    return merged_df

def save_final_dataset(df, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)
    print(f"\nSaved Final Dataset: {output_path}")

def run_merge_pipeline():
    events_path = GOLD_DIR / "events_dataset.parquet"
    weather_path = GOLD_DIR / "weather_dataset.parquet"
    output_path = GOLD_DIR / "training_dataset.parquet"

    final_df = build_final_training_dataset(events_path, weather_path)

    save_final_dataset(final_df, output_path)

    print("\nMerge Pipeline Complete")

    return final_df

if __name__ == "__main__" :
    run_merge_pipeline()