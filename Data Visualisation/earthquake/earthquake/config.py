# config.py

# Visual settings for the 3D map blocks
TERRAIN_PROFILES = {
    'Mountain': {'top_color': '#8B4513', 'sub_color': '#4B4B4B', 'label': 'Granite'},
    'Desert': {'top_color': '#EDC9AF', 'sub_color': '#A0522D', 'label': 'Sand'},
    'Forest': {'top_color': '#228B22', 'sub_color': '#556B2F', 'label': 'Silt'},
    'Coastal': {'top_color': '#F4A460', 'sub_color': '#4682B4', 'label': 'Basalt'},
    'Plain': {'top_color': '#D2B48C', 'sub_color': '#8B4513', 'label': 'Alluvium'},
    'Plateau': {'top_color': '#A52A2A', 'sub_color': '#2F4F4F', 'label': 'Basalt'}
}

# Master settings for each disaster type
DISASTER_SETTINGS = {
    'earthquake': {
        'title': 'STRATEGIC SEISMIC TERMINAL',
        'color_scale': 'Turbo',
        'metric_name': 'Magnitude',
        'metric_label': 'Magnitude'
    },
    'cyclone': {
        'title': 'CYCLONE TRACKING TERMINAL',
        'color_scale': 'Blues',
        'metric_name': 'Intensity_Metric', 
        'metric_label': 'Wind Speed (knots)'
    },
    'storm': {
        'title': 'SEVERE STORM MONITOR',
        'color_scale': 'dense',
        'metric_name': 'Intensity_Metric',
        'metric_label': 'Precipitation (mm)'
    }
}