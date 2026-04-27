#!/usr/bin/env python3
"""
Run GIS Processing Pipeline
Executes complete flood hazard modeling workflow
Based on final objectives.pdf and Project Overview.pdf
"""

import sys
from pathlib import Path

# Add gis_processing to path
sys.path.insert(0, str(Path(__file__).parent))

from gis_processing.pipeline import FloodHazardPipeline

def main():
    print("="*70)
    print("FLOOD HAZARD MODELING - GIS PROCESSING PIPELINE")
    print("Based on: final objectives.pdf & Project Overview.pdf")
    print("="*70)
    
    # Initialize pipeline with India bounds
    # You can customize bounds for specific study area
    study_area_bounds = [68.0, 6.0, 97.0, 37.0]  # India bounds
    
    pipeline = FloodHazardPipeline(study_area_bounds=study_area_bounds)
    
    # Run complete pipeline
    try:
        results = pipeline.run_complete_pipeline()
        
        print("\n" + "="*70)
        print("GIS PROCESSING COMPLETED SUCCESSFULLY!")
        print("="*70)
        print("\nGenerated Files:")
        print(f"   • Static Hazard Map: {results['objective1']['static_map_png']}")
        print(f"   • Hazard Zones (GeoJSON): {results['objective1']['hazard_zones_geojson']}")
        print(f"   • Vulnerability Summary: {results['objective2']['vulnerability_summary']}")
        print("\nNext Steps:")
        print("   1. Review generated files in data/processed/")
        print("   2. The Flask dashboard will automatically use these files")
        print("   3. For production, replace sample data with real DEM and infrastructure")
        
    except Exception as e:
        print(f"\nERROR: Error during processing: {e}")
        print("\nTroubleshooting:")
        print("   • Install GIS libraries: pip install -r requirements_gis.txt")
        print("   • If geopandas fails, the pipeline will use simplified fallback methods")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())



