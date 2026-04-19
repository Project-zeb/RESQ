# data_engine.py
import os
import pandas as pd
import numpy as np

def clean_disaster_data(df):
    """
    MASTER SANITIZATION PIPELINE 🚨
    Ensures the 3D JavaScript engine never receives a missing value that would break rendering.
    """
    # Critical 3D Rendering Data
    df['Depth_km'] = df['Depth_km'].fillna(35.0)  
    df['Max_Vibration_PGA'] = df['Max_Vibration_PGA'].fillna(0.15)
    df['Intensity_Metric'] = df['Intensity_Metric'].fillna(5.0)
    
    # UI Display Data
    if 'Soil_Type' not in df.columns: df['Soil_Type'] = 'Unknown Base'
    df['Soil_Type'] = df['Soil_Type'].fillna('Unknown Base')
    df['Economic_Loss_Millions'] = df['Economic_Loss_Millions'].fillna(0.0)
    df['Affected_Population'] = df['Affected_Population'].fillna(0)
    df['Terrain'] = df['Terrain'].fillna('Plain')
    
    return df

def aggregate_regional_data(df):
    """Groups multiple earthquakes in the same 55km Block_ID into a single analytical profile."""
    agg_logic = {
        'City': 'first',           
        'Lat': 'first',            
        'Lon': 'first',
        'Terrain': 'first',
        'Soil_Type': 'first',      # FIX: Ensure Soil_Type is not dropped
        'Intensity_Metric': 'max', 
        'Max_Vibration_PGA': 'max',
        'Economic_Loss_Millions': 'sum', 
        'Affected_Population': 'max',    
        'Depth_km': 'mean',        
        'Year': 'count'            
    }
    
    df_smart = df.groupby('Block_ID').agg(agg_logic).reset_index()
    df_smart = df_smart.rename(columns={'Year': 'Total_Historical_Events'})
    return df_smart

def generate_synthetic_data(disaster_type='earthquake'):
    """Internal fallback generator with HIGH-FIDELITY mock data."""
    np.random.seed(42) 
    
    base_zones = [
        {'City': 'Delhi NCR', 'Lat': 28.6, 'Lon': 77.2, 'Terrain': 'Plain', 'State': 'Delhi', 'Soil': 'Alluvium'},
        {'City': 'Guwahati', 'Lat': 26.1, 'Lon': 91.7, 'Terrain': 'Forest', 'State': 'Assam', 'Soil': 'Silt / Clay'},
        {'City': 'Kutch', 'Lat': 23.3, 'Lon': 69.7, 'Terrain': 'Desert', 'State': 'Gujarat', 'Soil': 'Sandy / Arid'},
        {'City': 'Himalayan', 'Lat': 31.0, 'Lon': 77.0, 'Terrain': 'Mountain', 'State': 'HP', 'Soil': 'Granite Bedrock'},
        {'City': 'Andaman', 'Lat': 11.6, 'Lon': 92.7, 'Terrain': 'Coastal', 'State': 'Andaman', 'Soil': 'Marine Silt'},
        {'City': 'Deccan', 'Lat': 18.5, 'Lon': 73.8, 'Terrain': 'Plateau', 'State': 'Maharashtra', 'Soil': 'Basalt Rock'}
    ]

    data = []
    for year in range(2007, 2018):
        for evt in range(2):
            zone = base_zones[np.random.randint(0, len(base_zones))]
            lat = np.clip(zone['Lat'] + np.random.normal(0, 1.0), 8.0, 35.0)
            lon = np.clip(zone['Lon'] + np.random.normal(0, 1.0), 68.0, 97.0)
            
            lat_55 = round(lat * 2) / 2
            lon_55 = round(lon * 2) / 2
            city_base = zone['City']
            safe_city = city_base.lower().replace(' ', '_')
            geo_id = f"loc_{str(lat_55).replace('.', '_')}_{str(lon_55).replace('.', '_')}_{safe_city}"
            
            intensity = round(np.random.uniform(3.5, 9.2), 1)
            depth = round(np.random.uniform(5.0, 80.0), 1)
            pga = round((intensity * 0.15) + np.random.uniform(0.01, 0.1), 3) 
            pop = int(np.random.uniform(10000, 2500000))
            loss = round(np.random.uniform(10.0, 850.5), 1)

            # (The code that intentionally injected None values has been permanently removed)

            record = {
                'City': f"{city_base} {year}-{evt+1}",
                'State': zone['State'],
                'Lat': round(lat, 4),
                'Lon': round(lon, 4),
                'Intensity_Metric': intensity, 
                'Depth_km': depth,
                'Soil_Type': zone['Soil'],
                'Max_Vibration_PGA': pga,
                'Affected_Population': pop,
                'Economic_Loss_Millions': loss,
                'Terrain': zone['Terrain'],
                'Year': year,
                'Block_ID': geo_id 
            }
            data.append(record)
            
    return pd.DataFrame(data)

def load_disaster_data(disaster_type='earthquake', use_real_data=False):
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