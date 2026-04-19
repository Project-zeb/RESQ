# fake.py
import os
import pandas as pd
import numpy as np

def create_mock_live_data(disaster_type='earthquake', num_records=15):
    """Generates a standalone CSV file to mimic a downloaded dataset (Strictly 2007-2017)."""
    print(f"🛠️ Generating clean mock 'real' data for {disaster_type}...")
    np.random.seed(99) # Using a different seed so the data looks distinct
    
    # Added Soil Type to match the 3D UI requirements
    base_zones = [
        {'City': 'Delhi NCR', 'Lat': 28.6, 'Lon': 77.2, 'Terrain': 'Plain', 'State': 'Delhi', 'Soil': 'Alluvium'},
        {'City': 'Guwahati', 'Lat': 26.1, 'Lon': 91.7, 'Terrain': 'Forest', 'State': 'Assam', 'Soil': 'Silt / Clay'},
        {'City': 'Kutch', 'Lat': 23.3, 'Lon': 69.7, 'Terrain': 'Desert', 'State': 'Gujarat', 'Soil': 'Sandy / Arid'}
    ]

    data = []
    for i in range(num_records):
        zone = base_zones[np.random.randint(0, len(base_zones))]
        lat = np.clip(zone['Lat'] + np.random.normal(0, 1.0), 8.0, 35.0)
        lon = np.clip(zone['Lon'] + np.random.normal(0, 1.0), 68.0, 97.0)
        
        # Slightly higher intensities to simulate major events
        intensity = round(np.random.uniform(5.5, 9.0), 1)
        
        # STRICTLY ENFORCE 2007 TO 2017
        random_year = np.random.randint(2007, 2018) 
        
        # Coordinate-based naming logic
        city_base = zone['City']
        safe_city = city_base.lower().replace(' ', '_')
        lat_str = str(round(lat, 1)).replace('.', '_')
        lon_str = str(round(lon, 1)).replace('.', '_')
        geo_id = f"loc_{lat_str}_{lon_str}_{safe_city}"
        
        # --- NEW: Generate the missing analytical fields required by the 3D Engine ---
        depth = round(np.random.uniform(5.0, 80.0), 1)
        pga = round((intensity * 0.15) + np.random.uniform(0.01, 0.1), 3)
        pop = int(np.random.uniform(10000, 2500000))
        loss = round(np.random.uniform(10.0, 850.5), 1)
            
        record = {
            'City': f"{city_base} [LIVE-MOCK {i+1}]",
            'State': zone['State'],
            'Lat': round(lat, 4),
            'Lon': round(lon, 4),
            'Intensity_Metric': intensity,
            'Depth_km': depth,                  # Critical for 3D Core
            'Soil_Type': zone['Soil'],          # Critical for UI Card
            'Max_Vibration_PGA': pga,           # Critical for UI Card
            'Affected_Population': pop,
            'Economic_Loss_Millions': loss,
            'Terrain': zone['Terrain'],
            'Year': random_year,
            'Block_ID': geo_id 
        }
        data.append(record)
        
    df = pd.DataFrame(data)
    
    # --- DATA CLEANING PIPELINE ---
    # In a real scenario, CSVs might have empty cells. We force-fill NaNs here
    # to guarantee the 3D JavaScript engine never receives 'null' or breaks.
    df['Depth_km'] = df['Depth_km'].fillna(35.0)  # Default depth if missing
    df['Economic_Loss_Millions'] = df['Economic_Loss_Millions'].fillna(0.0)
    df['Max_Vibration_PGA'] = df['Max_Vibration_PGA'].fillna(0.1)
    df['Affected_Population'] = df['Affected_Population'].fillna(0)
    df['Soil_Type'] = df['Soil_Type'].fillna('Unknown Base')
    
    # Create the data folder if it doesn't exist
    os.makedirs('data/real', exist_ok=True)
    
    # Save as CSV
    filepath = f"data/real/{disaster_type}_live_feed.csv"
    df.to_csv(filepath, index=False)
    
    print(f"✅ Clean mock live data saved to: {filepath}")
    print(f"📊 Total records generated: {len(df)} (Zero NaN values in core columns)")
    print("⏳ Timeframe: 2007 - 2017\n")

if __name__ == "__main__":
    create_mock_live_data('earthquake')