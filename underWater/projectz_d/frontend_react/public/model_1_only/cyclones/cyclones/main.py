# main.py
# Master script to load data and export dashboard

from data_engine import load_disaster_data
from exporter import export_seismic_dashboard_html


def main():
    """Main execution function - Load data and export dashboard"""
    
    print("\n🚀 SEISMIC DASHBOARD - COMPLETE EXECUTION")
    print("="*75)
    
    # Load earthquake data
    print("\n📊 LOADING EARTHQUAKE DATA...")
    df_100 = load_disaster_data()
    
    # Export HTML dashboard
    print("\n📁 EXPORTING HTML DASHBOARD...")
    export_seismic_dashboard_html(df_100, 'seismic_dashboard_interactive.html')
    
    print("\n✅ COMPLETE SEISMIC DASHBOARD READY")
    print("="*75)


if __name__ == '__main__':
    main()
