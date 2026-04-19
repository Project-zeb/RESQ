# data_engine.py
import pandas as pd
import re
import os

def clean_num(val):
    """Precision extraction for complex data strings (e.g., '12 lakh meals')"""
    if pd.isna(val) or str(val).lower().strip() in ['partner', 'n/a', 'unknown', '']:
        return 0
    val_str = str(val).lower()
    multiplier = 100000 if 'lakh' in val_str else 1
    clean_str = re.sub(r'[^\d.]', '', val_str)
    try:
        return float(clean_str) * multiplier if clean_str else 0
    except:
        return 0

def get_ngo_capacity_matrix():
    print("🧠 NDMA Data Core: Initializing Multi-Dimensional Resource Matrix...")
    files = ['data/3.csv', 'data/8.csv', 'data/10.csv']
    ngo_pool = []

    for f in files:
        if not os.path.exists(f):
            print(f"⚠️ WARNING: Could not find {f}")
            continue
            
        try:
            # Bypass messy commas in the CSVs safely
            df = pd.read_csv(f, on_bad_lines='skip', engine='python')
            for _, row in df.iterrows():
                name = str(row.get('Organisation Name') or row.get('Organization Name') or "Unknown NGO").strip()
                
                # We now extract and keep the EXACT granular data
                vols = clean_num(row.get('Volunteers', 0))
                shelter = clean_num(row.get('Shelter Capacity') or row.get('Beneficiaries', 0))
                meals = clean_num(row.get('Food Capacity/Day') or row.get('Meals Served', 0))
                kits = clean_num(row.get('Medical Kits') or row.get('Relief Kits', 0))
                focus = str(row.get('Focus Area') or row.get('Specialty/Focus') or "General Relief").strip()
                
                # Calculate a purely sorting-based power score so biggest NGOs show up first
                sort_power = vols + (shelter * 2) + (meals / 100) + (kits * 5)
                
                if sort_power > 0:
                    ngo_pool.append({
                        "name": name,
                        "state": str(row.get('State') or row.get('State/UT') or "National").strip(),
                        "focus": focus,
                        "sort_power": sort_power,
                        "resources": {
                            "vols": int(vols),
                            "shelter": int(shelter),
                            "meals": int(meals),
                            "kits": int(kits)
                        }
                    })
        except Exception as e:
            print(f"❌ Error processing {f}: {e}")
    
    # Sort largest NGOs to the top for the allocator's convenience
    ngo_pool = sorted(ngo_pool, key=lambda x: x['sort_power'], reverse=True)
    print(f"✅ Matrix Complete: Processed {len(ngo_pool)} NGO profiles with 4-dimensional data.")
    return ngo_pool