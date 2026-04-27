"""
Hazard Map Generator
Objective 1: Generate static flood hazard map with High/Medium/Low risk zones
Based on final objectives.pdf
"""

import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS
import os
import json

try:
    import geopandas as gpd
    from shapely.geometry import shape, Polygon, mapping
    from rasterio.features import shapes
    GIS_AVAILABLE = True
except ImportError:
    GIS_AVAILABLE = False
    print("Warning: geopandas not available. Install with: pip install geopandas shapely")

class HazardMapGenerator:
    """
    Generate flood hazard map from probability predictions
    Classifies into High, Medium, Low risk zones
    """
    
    def __init__(self, probability_raster=None):
        self.probability_raster = probability_raster
        self.hazard_classes = None
        self.transform = None
        self.crs = None
        self.thresholds = {'high': 0.7, 'medium': 0.4}  # Default thresholds
    
    def load_probability_raster(self, raster_path):
        """Load probability raster from file"""
        with rasterio.open(raster_path) as src:
            self.probability_raster = src.read(1)
            self.transform = src.transform
            self.crs = src.crs
        
        print(f"Loaded probability raster: {self.probability_raster.shape}")
        return self.probability_raster
    
    def create_sample_probability(self, bounds, size=(100, 100)):
        """Create sample probability raster for demonstration"""
        # Simulate flood probability (higher near rivers, lower on hills)
        lons = np.linspace(bounds[0], bounds[2], size[1])
        lats = np.linspace(bounds[1], bounds[3], size[0])
        lon_grid, lat_grid = np.meshgrid(lons, lats)
        
        # Higher probability near center (simulated river)
        center_lon = (bounds[0] + bounds[2]) / 2
        center_lat = (bounds[1] + bounds[3]) / 2
        
        dist_from_center = np.sqrt((lon_grid - center_lon)**2 + (lat_grid - center_lat)**2)
        max_dist = np.sqrt((bounds[2] - bounds[0])**2 + (bounds[3] - bounds[1])**2)
        
        # Probability decreases with distance from river
        probability = 0.9 * np.exp(-dist_from_center / (max_dist * 0.3))
        probability = np.clip(probability + np.random.normal(0, 0.1, size), 0, 1)
        
        self.probability_raster = probability
        self.transform = from_bounds(bounds[0], bounds[1], bounds[2], bounds[3], 
                                     size[1], size[0])
        self.crs = CRS.from_epsg(4326)
        
        print(f"Created sample probability raster: {self.probability_raster.shape}")
        return self.probability_raster
    
    def classify_hazard_zones(self, high_threshold=None, medium_threshold=None):
        """
        Classify probability into hazard zones
        High: p >= high_threshold
        Medium: medium_threshold <= p < high_threshold
        Low: p < medium_threshold
        """
        if self.probability_raster is None:
            raise ValueError("Probability raster not loaded")
        
        if high_threshold:
            self.thresholds['high'] = high_threshold
        if medium_threshold:
            self.thresholds['medium'] = medium_threshold
        
        # Classify: 0=Low, 1=Medium, 2=High
        hazard_classes = np.zeros_like(self.probability_raster, dtype=np.uint8)
        hazard_classes[self.probability_raster >= self.thresholds['medium']] = 1  # Medium
        hazard_classes[self.probability_raster >= self.thresholds['high']] = 2    # High
        
        self.hazard_classes = hazard_classes
        
        # Count pixels per class
        low_count = np.sum(hazard_classes == 0)
        medium_count = np.sum(hazard_classes == 1)
        high_count = np.sum(hazard_classes == 2)
        
        total = hazard_classes.size
        print(f"Classified hazard zones:")
        print(f"   Low Risk: {low_count} pixels ({100*low_count/total:.1f}%)")
        print(f"   Medium Risk: {medium_count} pixels ({100*medium_count/total:.1f}%)")
        print(f"   High Risk: {high_count} pixels ({100*high_count/total:.1f}%)")
        
        return hazard_classes
    
    def raster_to_polygons(self):
        """Convert hazard class raster to vector polygons"""
        if self.hazard_classes is None:
            raise ValueError("Hazard classes not generated")
        
        if not GIS_AVAILABLE:
            print("WARNING: geopandas not available. Returning simplified polygons")
            return self._create_simplified_polygons()
        
        # Convert raster to polygons
        polygons = []
        for (geom, value) in shapes(self.hazard_classes, transform=self.transform):
            if value > 0:  # Skip background (Low risk)
                zone_type = ['Medium', 'High'][int(value) - 1]
                polygons.append({
                    'geometry': shape(geom),
                    'risk_level': zone_type,
                    'risk_class': int(value)
                })
        
        # Create GeoDataFrame
        gdf = gpd.GeoDataFrame(polygons, crs=self.crs)
        
        # Dissolve by risk level
        gdf_dissolved = gdf.dissolve(by='risk_level')
        
        print(f"Created {len(gdf_dissolved)} hazard zone polygons")
        return gdf_dissolved
    
    def _create_simplified_polygons(self):
        """Create simplified polygons when geopandas is not available"""
        # Return basic polygon structure
        return {
            'high_risk': [],
            'medium_risk': [],
            'low_risk': []
        }
    
    def export_geotiff(self, output_path, data_type='hazard_classes'):
        """Export hazard map as GeoTIFF"""
        if data_type == 'hazard_classes':
            data = self.hazard_classes
        elif data_type == 'probability':
            data = self.probability_raster
        else:
            raise ValueError(f"Unknown data type: {data_type}")
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with rasterio.open(
            output_path,
            'w',
            driver='GTiff',
            height=data.shape[0],
            width=data.shape[1],
            count=1,
            dtype=data.dtype,
            crs=self.crs,
            transform=self.transform,
            compress='lzw'
        ) as dst:
            dst.write(data, 1)
        
        print(f"Exported {data_type} to {output_path}")
        return output_path
    
    def export_geojson(self, output_path):
        """Export hazard zones as GeoJSON"""
        if not GIS_AVAILABLE:
            print("WARNING: geopandas not available. Creating simplified GeoJSON")
            return self._export_simplified_geojson(output_path)
        
        gdf = self.raster_to_polygons()
        
        # Convert to GeoJSON
        gdf.to_file(output_path, driver='GeoJSON')
        
        print(f"Exported hazard zones to {output_path}")
        return output_path
    
    def _export_simplified_geojson(self, output_path):
        """Export simplified GeoJSON when geopandas is not available"""
        # Create basic GeoJSON structure
        geojson = {
            "type": "FeatureCollection",
            "features": []
        }
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(geojson, f)
        
        print(f"Created simplified GeoJSON at {output_path}")
        return output_path
    
    def generate_static_map_image(self, output_path, style_config=None):
        """
        Generate static PNG map image for dashboard
        Red = High Risk, Yellow = Medium Risk, Green = Low Risk
        """
        if self.hazard_classes is None:
            raise ValueError("Hazard classes not generated")
        
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors
        
        # Create color map
        colors = ['green', 'yellow', 'red']  # Low, Medium, High
        cmap = mcolors.ListedColormap(colors)
        bounds = [0, 1, 2, 3]
        norm = mcolors.BoundaryNorm(bounds, cmap.N)
        
        # Create figure
        fig, ax = plt.subplots(figsize=(12, 10))
        
        # Plot hazard map
        im = ax.imshow(self.hazard_classes, cmap=cmap, norm=norm, 
                      extent=[self.transform[2], 
                             self.transform[2] + self.transform[0] * self.hazard_classes.shape[1],
                             self.transform[5] + self.transform[4] * self.hazard_classes.shape[0],
                             self.transform[5]])
        
        # Add legend
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor='green', label='Low Risk'),
            Patch(facecolor='yellow', label='Medium Risk'),
            Patch(facecolor='red', label='High Risk')
        ]
        ax.legend(handles=legend_elements, loc='upper right')
        ax.set_title('Flood Hazard Map', fontsize=16, fontweight='bold')
        ax.set_xlabel('Longitude')
        ax.set_ylabel('Latitude')
        
        # Save
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"Generated static map image: {output_path}")
        return output_path
    
    def generate_colored_raster_png(self, output_path, bounds=None):
        """
        Generate colored PNG raster map for Leaflet display
        Colors are applied directly to geographic areas (not polygons)
        Returns PNG with transparent background for Low risk areas
        """
        if self.hazard_classes is None:
            raise ValueError("Hazard classes not generated")
        
        try:
            from PIL import Image
            import numpy as np
        except ImportError:
            print("WARNING: PIL not available. Install with: pip install Pillow")
            return self.generate_static_map_image(output_path)
        
        # Color mapping: 0=Low (Green), 1=Medium (Yellow), 2=High (Red)
        # Using RGBA with transparency
        color_map = {
            0: (0, 255, 136, 0),      # Green - Low risk (fully transparent)
            1: (255, 215, 0, 200),    # Yellow - Medium risk (semi-transparent)
            2: (255, 23, 68, 200)     # Red - High risk (semi-transparent)
        }
        
        # Create RGBA image
        height, width = self.hazard_classes.shape
        img = np.zeros((height, width, 4), dtype=np.uint8)
        
        for class_val, color in color_map.items():
            mask = self.hazard_classes == class_val
            img[mask] = color
        
        # Convert to PIL Image and save
        pil_img = Image.fromarray(img, 'RGBA')
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        pil_img.save(output_path, 'PNG')
        
        print(f"Generated colored raster PNG: {output_path}")
        return output_path

