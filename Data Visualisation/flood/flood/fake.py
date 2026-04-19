# fake.py
import os
import pandas as pd
import numpy as np

def create_mock_live_data(disaster_type='flood', num_records=15):
    """Generates a standalone CSV file to mimic a downloaded dataset (Strictly 2007-2017)."""
    print(f"🛠️ Generating clean mock 'real' data for {disaster_type}...")
    np.random.seed(99)
    
    base_zones = [
        {'City': 'Brahmaputra Basin', 'Lat': 26.1, 'Lon': 91.7, 'Terrain': 'River_Valley', 'State': 'Assam', 'Soil': 'Saturated Silt'},
        {'City': 'Mumbai Coast', 'Lat': 19.0, 'Lon': 72.8, 'Terrain': 'Urban', 'State': 'Maharashtra', 'Soil': 'Concrete/Urban'},
        {'City': 'Chennai Shores', 'Lat': 13.0, 'Lon': 80.2, 'Terrain': 'Coastal_Plain', 'State': 'Tamil Nadu', 'Soil': 'Porous Sand'}
    ]

    data = []
    for i in range(num_records):
        zone = base_zones[np.random.randint(0, len(base_zones))]
        lat = np.clip(zone['Lat'] + np.random.normal(0, 1.0), 8.0, 35.0)
        lon = np.clip(zone['Lon'] + np.random.normal(0, 1.0), 68.0, 97.0)
        
        rainfall = round(np.random.uniform(100.0, 450.0), 1)
        random_year = np.random.randint(2007, 2018) 
        
        # 55km Coordinate-based naming logic
        city_base = zone['City']
        safe_city = city_base.lower().replace(' ', '_')
        lat_str = str(round(lat, 1)).replace('.', '_')
        lon_str = str(round(lon, 1)).replace('.', '_')
        geo_id = f"loc_{lat_str}_{lon_str}_{safe_city}"
        
        depth = round(np.random.uniform(1.5, 12.0), 1)
        velocity = round((rainfall * 0.01) + np.random.uniform(0.5, 3.0), 2)
        pop = int(np.random.uniform(10000, 2500000))
        loss = round(np.random.uniform(10.0, 850.5), 1)
            
        record = {
            'City': f"{city_base} [LIVE-MOCK {i+1}]",
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
            'Year': random_year,
            'Block_ID': geo_id 
        }
        data.append(record)
        
    df = pd.DataFrame(data)
    
    # --- DATA CLEANING PIPELINE ---
    df['Flood_Depth_Meters'] = df['Flood_Depth_Meters'].fillna(2.0)
    df['Economic_Loss_Millions'] = df['Economic_Loss_Millions'].fillna(0.0)
    df['Flow_Velocity_mps'] = df['Flow_Velocity_mps'].fillna(0.1)
    df['Affected_Population'] = df['Affected_Population'].fillna(0)
    df['Soil_Permeability'] = df['Soil_Permeability'].fillna('Unknown Base')
    
    os.makedirs('data/real', exist_ok=True)
    filepath = f"data/real/{disaster_type}_live_feed.csv"
    df.to_csv(filepath, index=False)
    
    print(f"✅ Clean mock live data saved to: {filepath}")

if __name__ == "__main__":
    create_mock_live_data('flood')