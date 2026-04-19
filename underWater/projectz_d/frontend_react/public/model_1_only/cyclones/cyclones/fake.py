# fake.py
import pandas as pd
import numpy as np

def generate_synthetic_data(disaster_type='cyclone'):
    """Generates hyper-realistic synthetic dataset for Indian Cyclone Analysis."""
    np.random.seed(42) 
    
    # 4 Core Vulnerable Coastal Profiles
    base_zones = [
        {'City': 'Odisha Coast', 'Lat': 19.8, 'Lon': 86.1, 'Terrain': 'Coastal Delta', 'base_wind': 110, 'base_pres': 980, 'pop': 4500000},
        {'City': 'Sundarbans Basin', 'Lat': 21.9, 'Lon': 89.0, 'Terrain': 'Floodplain', 'base_wind': 130, 'base_pres': 965, 'pop': 2100000},
        {'City': 'Mumbai Urban Coast', 'Lat': 19.0, 'Lon': 72.8, 'Terrain': 'Coastal Urban', 'base_wind': 95, 'base_pres': 990, 'pop': 12500000},
        {'City': 'Chennai Delta', 'Lat': 13.0, 'Lon': 80.2, 'Terrain': 'Coastal Delta', 'base_wind': 105, 'base_pres': 985, 'pop': 7200000}
    ]

    data = []
    for year in range(2007, 2018):
        for evt in range(2):
            zone = base_zones[np.random.randint(0, len(base_zones))]
            
            lat = np.clip(zone['Lat'] + np.random.normal(0, 0.5), 8.0, 35.0)
            lon = np.clip(zone['Lon'] + np.random.normal(0, 0.5), 68.0, 97.0)
            
            lat_55 = round(lat * 2) / 2
            lon_55 = round(lon * 2) / 2
            city_base = zone['City']
            safe_city = city_base.lower().replace(' ', '_')
            geo_id = f"CYC_{str(lat_55).replace('.', '_')}_{str(lon_55).replace('.', '_')}_{safe_city}"
            
            severity_multiplier = np.random.uniform(0.7, 1.8) 
            wind_speed = int(zone["base_wind"] * severity_multiplier)
            pressure = int(zone["base_pres"] - ((wind_speed - 100) * 0.4)) 
            
            # Saffir-Simpson Hurricane Wind Scale
            if wind_speed >= 137: category = 5
            elif wind_speed >= 113: category = 4
            elif wind_speed >= 96: category = 3
            elif wind_speed >= 83: category = 2
            elif wind_speed >= 64: category = 1
            else: category = 0 
            
            # Cyclone-Specific Impact
            pop = int(zone["pop"] * np.random.uniform(0.1, 0.6))
            loss = int((wind_speed * pop) / 85000) 
            storm_surge = round(category * 1.8 + np.random.uniform(0.5, 2.0), 1) # Up to 11m surge for Cat 5
            
            record = {
                'City': f"{city_base} {year}-{evt+1}",
                'Lat': round(lat, 4),
                'Lon': round(lon, 4),
                'Wind_Speed_Knots': wind_speed,
                'Pressure_hPa': pressure,
                'Storm_Category': category,
                'Storm_Surge_Meters': storm_surge,
                'Affected_Population': pop,
                'Economic_Loss_Millions': loss,
                'Terrain': zone['Terrain'],
                'Year': year,
                'Block_ID': geo_id 
            }
            data.append(record)
            
    df = pd.DataFrame(data)
    df = df.sort_values(by="Year").reset_index(drop=True)
    return df

if __name__ == "__main__":
    df = generate_synthetic_data()
    df.to_csv("synthetic_cyclones.csv", index=False)
    print("✅ Synthetic Cyclone Data Generated!")