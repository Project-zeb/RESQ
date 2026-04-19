# main.py
# Master script to load data and export dashboard

from exporter import export_dashboard_html

def main():
    """Main execution function - Load data and export dashboard"""
    
    print("\n🌊 FLOOD DASHBOARD - COMPLETE EXECUTION")
    print("="*75)
    
    print("\n📁 EXPORTING HTML DASHBOARD...")
    # Call the exporter without arguments (it loads its own data now)
    export_dashboard_html()
    
    print("\n✅ COMPLETE FLOOD DASHBOARD READY")
    print("="*75)

if __name__ == '__main__':
    main()