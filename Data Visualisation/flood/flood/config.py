# config.py

# Visual settings for the 3D map blocks (Adapted for Flood UI)
TERRAIN_PROFILES = {
    'Mountain': {'top_color': '#228B22', 'sub_color': '#4B4B4B', 'label': 'Granite / Rock'},
    'Urban': {'top_color': '#808080', 'sub_color': '#404040', 'label': 'Concrete / Asphalt'},
    'River_Valley': {'top_color': '#D2B48C', 'sub_color': '#8B4513', 'label': 'Saturated Silt'},
    'Coastal_Plain': {'top_color': '#F4A460', 'sub_color': '#4682B4', 'label': 'Sandy Loam'}
}

# Master settings for each disaster type
DISASTER_SETTINGS = {
    'flood': {
        'title': 'FLOOD INTELLIGENCE TERMINAL',
        'color_scale': 'Blues',      # Blue color scale for Plotly maps
        'metric_name': 'Rainfall_mm',
        'metric_label': 'Rainfall (mm)'
    }
}