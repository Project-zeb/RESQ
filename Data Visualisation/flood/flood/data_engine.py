# data_engine.py
import os
import pandas as pd
import numpy as np

def clean_disaster_data(df):
    """
    MASTER SANITIZATION PIPELINE 🚨
    Ensures the 3D JavaScript engine never receives a missing value that would break rendering.
    """
    # Critical 3D Rendering Data (FLOOD METRICS)
    df['Flood_Depth_Meters'] = df['Flood_Depth_Meters'].fillna(2.0)  
    df['Flow_Velocity_mps'] = df['Flow_Velocity_mps'].fillna(0.5)
    df['Rainfall_mm'] = df['Rainfall_mm'].fillna(50.0)
    
    # UI Display Data
    if 'Soil_Permeability' not in df.columns: df['Soil_Permeability'] = 'Unknown Base'
    df['Soil_Permeability'] = df['Soil_Permeability'].fillna('Unknown Base')
    df['Economic_Loss_Millions'] = df['Economic_Loss_Millions'].fillna(0.0)
    df['Affected_Population'] = df['Affected_Population'].fillna(0)
    df['Terrain'] = df['Terrain'].fillna('River_Valley')
    
    return df

def aggregate_regional_data(df):
    """Groups multiple floods in the same 55km Block_ID into a single analytical profile."""
    agg_logic = {
        'City': 'first',           
        'Lat': 'first',            
        'Lon': 'first',
        'Terrain': 'first',
        'Soil_Permeability': 'first',
        'Rainfall_mm': 'max', 
        'Flow_Velocity_mps': 'max',
        'Economic_Loss_Millions': 'sum', 
        'Affected_Population': 'max',    
        'Flood_Depth_Meters': 'mean',        
        'Year': 'count'            
    }
    
    df_smart = df.groupby('Block_ID').agg(agg_logic).reset_index()
    df_smart = df_smart.rename(columns={'Year': 'Total_Historical_Events'})
    return df_smart

def generate_synthetic_data(disaster_type='flood'):
    """Internal fallback generator with HIGH-FIDELITY mock data."""
    np.random.seed(42) 
    
    base_zones = [
        {'City': 'Brahmaputra Basin', 'Lat': 26.1, 'Lon': 91.7, 'Terrain': 'River_Valley', 'State': 'Assam', 'Soil': 'Saturated Silt'},
        {'City': 'Mumbai Coast', 'Lat': 19.0, 'Lon': 72.8, 'Terrain': 'Urban', 'State': 'Maharashtra', 'Soil': 'Concrete/Urban'},
        {'City': 'Chennai Shores', 'Lat': 13.0, 'Lon': 80.2, 'Terrain': 'Coastal_Plain', 'State': 'Tamil Nadu', 'Soil': 'Porous Sand'},
        {'City': 'Himalayan Foothills', 'Lat': 31.0, 'Lon': 77.0, 'Terrain': 'Mountain', 'State': 'HP', 'Soil': 'Rocky/Granite'},
        {'City': 'Ganges Plains', 'Lat': 25.6, 'Lon': 85.1, 'Terrain': 'River_Valley', 'State': 'Bihar', 'Soil': 'Saturated Silt'}
    ]

    data = []
    # STRICT TIMEFRAME: 2007 to 2017
    for year in range(2007, 2018):
        for evt in range(2):
            zone = base_zones[np.random.randint(0, len(base_zones))]
            lat = np.clip(zone['Lat'] + np.random.normal(0, 1.0), 8.0, 35.0)
            lon = np.clip(zone['Lon'] + np.random.normal(0, 1.0), 68.0, 97.0)
            
            # 55km Block Snapping
            lat_55 = round(lat * 2) / 2
            lon_55 = round(lon * 2) / 2
            city_base = zone['City']
            safe_city = city_base.lower().replace(' ', '_')
            geo_id = f"loc_{str(lat_55).replace('.', '_')}_{str(lon_55).replace('.', '_')}_{safe_city}"
            
            # Flood Telemetry
            rainfall = round(np.random.uniform(50.0, 450.0), 1)
            depth = round(np.random.uniform(0.5, 12.0), 1)
            velocity = round((rainfall * 0.01) + np.random.uniform(0.1, 2.0), 2) 
            pop = int(np.random.uniform(10000, 2500000))
            loss = round(np.random.uniform(10.0, 850.5), 1)

            record = {
                'City': f"{city_base} {year}-{evt+1}",
                'State': zone['State'],
                'Lat': round(lat, 4),
                'Lon': round(lon, 4),
                'Rainfall_mm': rainfall, 
                'Flood_Depth_Meters': depth,
                'Soil_Permeability': zone['Soil'],
                'Flow_Velocity_mps': velocity,
                'Affected_Population': pop,
                'Economic_Loss_Millions': loss,
                'Terrain': zone['Terrain'],
                'Year': year,
                'Block_ID': geo_id 
            }
            data.append(record)
            
    return pd.DataFrame(data)

def load_disaster_data(disaster_type='flood', use_real_data=False):
    """Master router: Safely attempts to load files, falls back if missing."""
    df = None
    if not use_real_data:
        print(f"[DATA] Generating internal SYNTHETIC data for {disaster_type}...")
        df = generate_synthetic_data(disaster_type)
    else:
        print(f"[DATA] Searching for REAL dataset for {disaster_type}...")
        csv_path = f"data/real/{disaster_type}_live_feed.csv"
        parquet_path = f"data/real/{disaster_type}_live_feed.parquet"
        
        if os.path.exists(csv_path):
            print(f"📥 SUCCESS: Loaded CSV from {csv_path}")
            df = pd.read_csv(csv_path)
        elif os.path.exists(parquet_path):
            print(f"📥 SUCCESS: Loaded Parquet from {parquet_path}")
            df = pd.read_parquet(parquet_path)
        else:
            print(f"\n❌ ERROR: Could not find real data files. Reverting to synthetic data...\n")
            df = generate_synthetic_data(disaster_type)
            
    # 🚨 ALWAYS SANITIZE BEFORE SENDING TO FRONTEND
    return clean_disaster_data(df)