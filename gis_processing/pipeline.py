"""
Complete GIS Processing Pipeline
Integrates all GIS processing steps according to objectives
Based on final objectives.pdf and Project Overview.pdf
"""

import os
import sys
import numpy as np
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

try:
    import geopandas as gpd
    from shapely.geometry import box
    GIS_AVAILABLE = True
except ImportError:
    GIS_AVAILABLE = False

from gis_processing.dem_processor import DEMProcessor
from gis_processing.hazard_map_generator import HazardMapGenerator
from gis_processing.vulnerability_analyzer import VulnerabilityAnalyzer
from gis_processing.enhanced_map_generator import EnhancedMapGenerator

class FloodHazardPipeline:
    """
    Complete pipeline for flood hazard modeling and vulnerability assessment
    Implements all three objectives from final objectives.pdf
    """
    
    def __init__(self, study_area_bounds=None):
        """
        study_area_bounds: [min_lon, min_lat, max_lon, max_lat]
        Default: India bounds
        """
        if study_area_bounds is None:
            # Default: India bounds
            self.bounds = [68.0, 6.0, 97.0, 37.0]
        else:
            self.bounds = study_area_bounds
        
        self.output_dir = "data/processed"
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.dem_processor = DEMProcessor()
        self.hazard_generator = HazardMapGenerator()
        self.vulnerability_analyzer = VulnerabilityAnalyzer()
        self.enhanced_map_gen = EnhancedMapGenerator()
    
    def run_objective1(self, dem_path=None):
        """
        Objective 1: Develop flood susceptibility model and generate static hazard map
        """
        print("\n" + "="*60)
        print("OBJECTIVE 1: Flood Hazard Model & Static Map Generation")
        print("="*60)
        
        # Step 1: Process DEM
        print("\nStep 1: Processing DEM and extracting features...")
        if dem_path and os.path.exists(dem_path):
            self.dem_processor.load_dem(dem_path)
        else:
            print("   Creating sample DEM for demonstration...")
            self.dem_processor.create_sample_dem(self.bounds, size=(200, 200))
        
        # Extract topographic features
        features = self.dem_processor.extract_all_features()
        
        # Save features
        self.dem_processor.save_features(self.output_dir)
        
        # Step 2: Generate probability map (simulated from features)
        print("\nStep 2: Generating flood probability map...")
        # In production, this would use ML model predictions
        # For now, create sample probability based on HAND and TWI
        if 'hand' in features and 'twi' in features:
            # Higher probability where HAND is low and TWI is high
            hand_norm = (features['hand'] - features['hand'].min()) / (features['hand'].max() - features['hand'].min() + 1e-10)
            twi_norm = (features['twi'] - features['twi'].min()) / (features['twi'].max() - features['twi'].min() + 1e-10)
            probability = 1 - hand_norm * 0.6 + twi_norm * 0.4
            probability = np.clip(probability, 0, 1)
        else:
            # Fallback: create sample probability
            self.hazard_generator.create_sample_probability(self.bounds, size=(200, 200))
            probability = self.hazard_generator.probability_raster
        
        # Step 3: Classify into hazard zones
        print("\nStep 3: Classifying hazard zones...")
        self.hazard_generator.probability_raster = probability
        self.hazard_generator.transform = self.dem_processor.transform
        self.hazard_generator.crs = self.dem_processor.crs
        
        hazard_classes = self.hazard_generator.classify_hazard_zones(
            high_threshold=0.7,
            medium_threshold=0.4
        )
        
        # Step 4: Export outputs
        print("\nStep 4: Exporting outputs...")
        
        # Export GeoTIFF
        hazard_tif = os.path.join(self.output_dir, "hazard_map.tif")
        self.hazard_generator.export_geotiff(hazard_tif, 'hazard_classes')
        
        # Export GeoJSON
        hazard_geojson = os.path.join(self.output_dir, "hazard_zones.geojson")
        self.hazard_generator.export_geojson(hazard_geojson)
        
        # Export basic static PNG map
        static_map = os.path.join(self.output_dir, "static_hazard_map.png")
        self.hazard_generator.generate_static_map_image(static_map)
        
        # Export colored raster PNG for Leaflet (direct area coloring, no overlay boxes)
        colored_raster = os.path.join(self.output_dir, "hazard_raster.png")
        try:
            self.hazard_generator.generate_colored_raster_png(colored_raster, bounds=self.bounds)
            print(f"Generated colored raster for map overlay: {colored_raster}")
        except Exception as e:
            print(f"WARNING: Could not generate colored raster: {e}")
            print(f"WARNING: Could not generate colored raster: {e}")
            colored_raster = static_map  # Fallback
        
        # Generate enhanced professional map with all components
        print("\nGenerating enhanced professional map...")
        try:
            # Load hazard zones GeoDataFrame
            if GIS_AVAILABLE:
                hazard_zones_gdf = gpd.read_file(hazard_geojson)
                
                # Create sample river network and sub-districts if not provided
                river_network = self.enhanced_map_gen.create_sample_river_network(self.bounds)
                sub_districts = self.enhanced_map_gen.create_sample_sub_districts(self.bounds, n_districts=8)
                
                # Create basin boundary from bounds
                from shapely.geometry import box
                basin_boundary = gpd.GeoDataFrame(
                    [{'geometry': box(self.bounds[0], self.bounds[1], self.bounds[2], self.bounds[3])}],
                    crs='EPSG:4326'
                )
                
                # Generate enhanced map
                enhanced_map = os.path.join(self.output_dir, "enhanced_hazard_map.png")
                self.enhanced_map_gen.generate_professional_map(
                    hazard_zones_gdf=hazard_zones_gdf,
                    output_path=enhanced_map,
                    study_area_name="Lower Narmada Basin",
                    river_network_gdf=river_network,
                    basin_boundary_gdf=basin_boundary,
                    sub_districts_gdf=sub_districts,
                    bounds=self.bounds
                )
                static_map = enhanced_map  # Use enhanced map as primary
        except Exception as e:
            print(f"WARNING: Could not generate enhanced map: {e}")
            print("   Using basic static map instead")
        
        print("\nObjective 1 completed!")
        print(f"   Outputs saved to: {self.output_dir}")
        
        return {
            'hazard_map_tif': hazard_tif,
            'hazard_zones_geojson': hazard_geojson,
            'static_map_png': static_map
        }
    
    def run_objective2(self, hazard_zones_path=None):
        """
        Objective 2: Vulnerability assessment via spatial overlay
        """
        print("\n" + "="*60)
        print("OBJECTIVE 2: Vulnerability Assessment")
        print("="*60)
        
        # Step 1: Load hazard zones
        print("\n📂 Step 1: Loading hazard zones...")
        if hazard_zones_path and os.path.exists(hazard_zones_path):
            self.vulnerability_analyzer.load_hazard_zones(hazard_zones_path)
        else:
            # Use generated zones from Objective 1
            zones_path = os.path.join(self.output_dir, "hazard_zones.geojson")
            if os.path.exists(zones_path):
                self.vulnerability_analyzer.load_hazard_zones(zones_path)
            else:
                print("WARNING: No hazard zones found. Run Objective 1 first.")
                return None
        
        # Step 2: Load infrastructure
        print("\nStep 2: Loading infrastructure data...")
        infrastructure_path = "data/infrastructure.json"
        if os.path.exists(infrastructure_path):
            self.vulnerability_analyzer.load_infrastructure(infrastructure_path)
        else:
            print("   Creating sample infrastructure data...")
            self.vulnerability_analyzer.create_sample_infrastructure(self.bounds)
        
        # Step 3: Perform spatial overlay
        print("\nStep 3: Performing spatial overlay analysis...")
        vulnerability = self.vulnerability_analyzer.perform_spatial_overlay()
        
        # Step 4: Export summary
        print("\nStep 4: Exporting vulnerability summary...")
        summary_path = os.path.join(self.output_dir, "vulnerability_summary.json")
        self.vulnerability_analyzer.export_summary(summary_path)
        
        print("\nObjective 2 completed!")
        print(f"   Vulnerability summary: {summary_path}")
        
        return {
            'vulnerability_summary': summary_path,
            'summary_data': vulnerability
        }
    
    def run_complete_pipeline(self):
        """Run complete pipeline for all objectives"""
        print("\n" + "="*60)
        print("FLOOD HAZARD MODELING PIPELINE")
        print("Based on final objectives.pdf")
        print("="*60)
        
        # Objective 1: Hazard Map
        obj1_outputs = self.run_objective1()
        
        # Objective 2: Vulnerability Assessment
        obj2_outputs = self.run_objective2()
        
        print("\n" + "="*60)
        print("PIPELINE COMPLETED SUCCESSFULLY!")
        print("="*60)
        print("\nGenerated files:")
        print(f"  - Hazard Map: {obj1_outputs['static_map_png']}")
        print(f"  - Hazard Zones: {obj1_outputs['hazard_zones_geojson']}")
        print(f"  - Vulnerability Summary: {obj2_outputs['vulnerability_summary']}")
        print("\nThese files can now be used in the Flask dashboard!")
        
        return {
            'objective1': obj1_outputs,
            'objective2': obj2_outputs
        }

if __name__ == "__main__":
    # Initialize pipeline
    pipeline = FloodHazardPipeline()
    
    # Run complete pipeline
    results = pipeline.run_complete_pipeline()

