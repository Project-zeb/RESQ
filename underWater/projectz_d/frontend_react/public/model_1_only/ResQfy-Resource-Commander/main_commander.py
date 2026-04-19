# main_commander.py
import json
import shutil
import os
from data_engine import get_ngo_capacity_matrix

def build_command_center():
    print("\n🚀 ResQfy: Initializing Strategic Command Center Build...")
    
    # 1. Get the cleaned data
    ngo_data = get_ngo_capacity_matrix()
    
    # 2. Create the JS Data File
    os.makedirs('static/js', exist_ok=True)
    with open('static/js/resources.js', 'w', encoding='utf-8') as f:
        f.write(f"const ngoPool = {json.dumps(ngo_data)};\n")

    print("✅ Created static/js/resources.js (Data Link Established)")

    # 3. Copy the template to the main folder for easy opening
    if os.path.exists('templates/commander_base.html'):
        shutil.copy('templates/commander_base.html', 'index.html')
        print("✅ Exported HTML -> index.html")
    else:
        print("⚠️ WARNING: templates/commander_base.html not found yet. Skipping HTML export.")

    print("="*60)
    print("👉 Next: Run 'python -m http.server'")
    print("👉 Then open: http://127.0.0.1:8000/index.html\n")

if __name__ == "__main__":
    build_command_center()