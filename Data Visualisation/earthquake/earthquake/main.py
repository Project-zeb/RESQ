# main.py
# Master script to load data and export dashboard

from data_engine import load_disaster_data
from exporter import export_dashboard_html
from config import DISASTER_SETTINGS

def main():
    """Main execution function - Load data and export dashboard"""
    
    print("\n🚀 SEISMIC DASHBOARD - COMPLETE EXECUTION")
    print("="*75)
    
    # Load earthquake data
    print("\n📊 LOADING EARTHQUAKE DATA...")
    df_100 = load_disaster_data('earthquake')
    
    # Grab the visual configuration for earthquakes
    earthquake_config = DISASTER_SETTINGS.get('earthquake', {})
    
    # Export HTML dashboard
    print("\n📁 EXPORTING HTML DASHBOARD...")
    # Updated function name and added the config parameter
    export_dashboard_html(df_100, earthquake_config, 'earthquake_dashboard.html')
    
    print("\n✅ COMPLETE SEISMIC DASHBOARD READY")
    print("="*75)

if __name__ == '__main__':
    main()