# exporter.py
import json
import base64
import os
import pandas as pd

def get_base64_models():
    """Converts .glb files into Base64 strings for total embedding."""
    models_dict = {}
    # Use the same names your JS switch statement expects
    required = ['mountain.glb', 'city.glb', 'desert.glb', 'river.glb']
    models_dir = os.path.join('assets', 'models')
    
    if not os.path.exists(models_dir):
        print(f"⚠️ Warning: {models_dir} folder not found.")
        return json.dumps({})

    for model_name in required:
        path = os.path.join(models_dir, model_name)
        if os.path.exists(path):
            with open(path, "rb") as f:
                # Binary to base64 conversion
                encoded = base64.b64encode(f.read()).decode('utf-8')
                models_dict[model_name] = f"data:application/octet-stream;base64,{encoded}"
            print(f"📦 Embedded: {model_name}")
        else:
            print(f"❌ Missing: {model_name}")
            
    return json.dumps(models_dict)

def export_dashboard_html(df, config, filename):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Prepare Data, Config, and Baked-in Models
    data_json = df.to_json(orient='records')
    config_json = json.dumps(config)
    embedded_models = get_base64_models()

    # Read Source Templates
    with open(os.path.join(base_dir, 'templates', 'dashboard.html'), 'r') as f:
        html = f.read()
    with open(os.path.join(base_dir, 'static', 'css', 'style.css'), 'r') as f:
        css = f.read()
    with open(os.path.join(base_dir, 'static', 'js', 'dashboard.js'), 'r') as f:
        js = f.read()

    # Inject everything into one file
    final_html = html.replace('/* INJECT_CSS */', css)
    final_html = final_html.replace('/* INJECT_DATA_JSON */', data_json)
    final_html = final_html.replace('/* INJECT_CONFIG_JSON */', config_json)
    final_html = final_html.replace('/* INJECT_MODELS_JSON */', embedded_models)
    final_html = final_html.replace('/* INJECT_JS */', js)
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(final_html)
    print(f"✅ STANDALONE READY: {filename}")
    # exporter.py - Updated Part of export_dashboard_html

def export_dashboard_html(df, config, filename):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 1. Prepare Data & Models
    data_json = df.to_json(orient='records')
    config_json = json.dumps(config)
    embedded_models = get_base64_models()

    # 2. Read Templates WITH UTF-8 ENCODING 🚨
    # Update these three blocks specifically:
    with open(os.path.join(base_dir, 'templates', 'dashboard.html'), 'r', encoding='utf-8') as f:
        html = f.read()
    with open(os.path.join(base_dir, 'static', 'css', 'style.css'), 'r', encoding='utf-8') as f:
        css = f.read()
    with open(os.path.join(base_dir, 'static', 'js', 'dashboard.js'), 'r', encoding='utf-8') as f:
        js = f.read()

    # 3. Inject everything into the HTML
    final_html = html.replace('/* INJECT_CSS */', css)
    final_html = final_html.replace('/* INJECT_DATA_JSON */', data_json)
    final_html = final_html.replace('/* INJECT_CONFIG_JSON */', config_json)
    final_html = final_html.replace('/* INJECT_MODELS_JSON */', embedded_models)
    final_html = final_html.replace('/* INJECT_JS */', js)
    
    # Ensure the output file is also written in UTF-8
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(final_html)
    
    print(f"✅ STANDALONE READY: {filename}")