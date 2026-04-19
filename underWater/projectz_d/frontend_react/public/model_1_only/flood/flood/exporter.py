import json
import base64
import os
from data_engine import load_disaster_data
from config import DISASTER_SETTINGS

def export_dashboard_html():
    print("\n🌊 BUILDING TRUE STANDALONE DASHBOARD...")
    
    # 1. Load the Data
    df = load_disaster_data('flood')
    data_dict = df.to_dict(orient='records')
    flood_config = DISASTER_SETTINGS.get('flood', {})
    
    # 2. Dynamically encode GLB files to Base64 so they bypass CORS
    print("📦 Packing 3D Models into memory...")
    embedded_models = {}
    model_names = ['mountain.glb', 'city.glb', 'river.glb', 'desert.glb']
    
    for model in model_names:
        # Check both the static/models/ folder AND the root directory
        path_in_static = os.path.join('static', 'models', model)
        path_in_root = model
        
        target_path = None
        if os.path.exists(path_in_static):
            target_path = path_in_static
        elif os.path.exists(path_in_root):
            target_path = path_in_root
            
        if target_path:
            with open(target_path, 'rb') as f:
                encoded = base64.b64encode(f.read()).decode('utf-8')
                embedded_models[model] = f"data:model/gltf-binary;base64,{encoded}"
                print(f"  -> ✅ Encoded {model} successfully from {target_path}")
        else:
            print(f"  -> ⚠️ WARNING: Could not find {model} anywhere!")

    # 3. Read the HTML, JS, and CSS files
    print("📄 Reading HTML, JS, and CSS templates...")
    with open('templates/dashboard.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
        
    with open('static/js/dashboard.js', 'r', encoding='utf-8') as f:
        js_content = f.read()
        
    with open('static/css/style.css', 'r', encoding='utf-8') as f:
        css_content = f.read()

    # 4. Inject EVERYTHING (CSS, JS, Data, Models) into the placeholders
    print("💉 Injecting assets directly into HTML...")
    html_content = html_content.replace('/* INJECT_CSS */', css_content)
    html_content = html_content.replace('/* INJECT_DATA_JSON */', json.dumps(data_dict))
    html_content = html_content.replace('/* INJECT_CONFIG_JSON */', json.dumps(flood_config))
    html_content = html_content.replace('/* INJECT_MODELS_JSON */', json.dumps(embedded_models))
    html_content = html_content.replace('/* INJECT_JS */', js_content)
    
    # 5. Save the standalone file
    with open('standalone_flood_dashboard.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
        
    print("\n✅ SUCCESS: Created standalone_flood_dashboard.html")
    print("👉 You can now double-click this file directly. No server needed!\n")

if __name__ == '__main__':
    export_dashboard_html()