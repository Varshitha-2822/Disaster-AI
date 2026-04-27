# GIS Processing Module

This module implements GIS tools for flood hazard modeling according to the project objectives.

## Objectives Implementation

### Objective 1: Flood Hazard Model & Static Map
- **File:** `dem_processor.py` - Processes DEM and extracts topographic features
- **File:** `hazard_map_generator.py` - Generates hazard maps with High/Medium/Low zones
- **Output:** Static flood hazard map (PNG), GeoTIFF, GeoJSON

### Objective 2: Vulnerability Assessment
- **File:** `vulnerability_analyzer.py` - Performs spatial overlay analysis
- **Output:** JSON summary of infrastructure counts per risk zone

### Complete Pipeline
- **File:** `pipeline.py` - Runs complete GIS processing workflow

## Installation

```bash
# Install GIS libraries
pip install -r requirements_gis.txt

# Or install individually
pip install rasterio geopandas shapely fiona pyproj
```

## Usage

### Run Complete Pipeline

```python
from gis_processing.pipeline import FloodHazardPipeline

# Initialize pipeline
pipeline = FloodHazardPipeline()

# Run all objectives
results = pipeline.run_complete_pipeline()
```

### Individual Components

```python
# 1. Process DEM
from gis_processing.dem_processor import DEMProcessor

processor = DEMProcessor()
processor.create_sample_dem(bounds=[68.0, 6.0, 97.0, 37.0])
features = processor.extract_all_features()
processor.save_features("data/processed")

# 2. Generate Hazard Map
from gis_processing.hazard_map_generator import HazardMapGenerator

generator = HazardMapGenerator()
generator.create_sample_probability(bounds=[68.0, 6.0, 97.0, 37.0])
generator.classify_hazard_zones(high_threshold=0.7, medium_threshold=0.4)
generator.export_geojson("data/processed/hazard_zones.geojson")
generator.generate_static_map_image("data/processed/static_map.png")

# 3. Vulnerability Analysis
from gis_processing.vulnerability_analyzer import VulnerabilityAnalyzer

analyzer = VulnerabilityAnalyzer()
analyzer.load_hazard_zones("data/processed/hazard_zones.geojson")
analyzer.create_sample_infrastructure(bounds=[68.0, 6.0, 97.0, 37.0])
vulnerability = analyzer.perform_spatial_overlay()
analyzer.export_summary("data/processed/vulnerability_summary.json")
```

## Output Files

After running the pipeline, you'll get:

1. **data/processed/hazard_map.tif** - GeoTIFF hazard classification
2. **data/processed/hazard_zones.geojson** - Vector polygons of risk zones
3. **data/processed/static_hazard_map.png** - Static map image for dashboard
4. **data/processed/vulnerability_summary.json** - Infrastructure counts per zone
5. **data/processed/*.tif** - Topographic feature rasters (slope, HAND, TWI, etc.)

## Integration with Dashboard

The generated files are automatically used by the Flask dashboard:

- `hazard_zones.geojson` → Loaded into map visualization
- `static_hazard_map.png` → Displayed as background map
- `vulnerability_summary.json` → Shown in vulnerability panel

## Notes

- If `geopandas` is not installed, the module will use simplified fallback methods
- For production use, replace sample data generation with real DEM and infrastructure data
- QGIS can be used for advanced visualization and manual editing of outputs




