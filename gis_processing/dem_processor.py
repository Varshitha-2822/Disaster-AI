"""
DEM Processing Module
Objective 1: Process Digital Elevation Model and extract topographic features
Based on final objectives.pdf and Project Overview.pdf
"""

import rasterio
import numpy as np
from rasterio.transform import from_bounds
from rasterio.crs import CRS
import os

try:
    import geopandas as gpd
    from shapely.geometry import shape, Polygon
    GIS_AVAILABLE = True
except ImportError:
    GIS_AVAILABLE = False
    print("Warning: geopandas not available. Install with: pip install geopandas")

class DEMProcessor:
    """
    Process DEM to extract topographic features:
    - HAND (Height Above Nearest Drainage)
    - TWI (Topographic Wetness Index)
    - Slope
    - Flow Accumulation
    - Distance to River
    """
    
    def __init__(self, dem_path=None):
        self.dem_path = dem_path
        self.dem_data = None
        self.transform = None
        self.crs = None
        self.features = {}
        
    def load_dem(self, dem_path):
        """Load DEM from file"""
        if not os.path.exists(dem_path):
            raise FileNotFoundError(f"DEM file not found: {dem_path}")
        
        with rasterio.open(dem_path) as src:
            self.dem_data = src.read(1)
            self.transform = src.transform
            self.crs = src.crs
            self.dem_path = dem_path
        
        print(f"Loaded DEM: {self.dem_data.shape} pixels")
        return self.dem_data
    
    def create_sample_dem(self, bounds, resolution=0.01, size=(100, 100)):
        """
        Create a sample DEM for demonstration
        bounds: [min_lon, min_lat, max_lon, max_lat]
        """
        # Create synthetic DEM with elevation gradient
        lons = np.linspace(bounds[0], bounds[2], size[1])
        lats = np.linspace(bounds[1], bounds[3], size[0])
        lon_grid, lat_grid = np.meshgrid(lons, lats)
        
        # Simulate elevation (higher in north, lower near rivers)
        elevation = 100 + (lat_grid - bounds[1]) * 50
        # Add river valleys (lower elevation)
        river_valley = 20 * np.exp(-((lon_grid - (bounds[0] + bounds[2])/2)**2 + 
                                     (lat_grid - (bounds[1] + bounds[3])/2)**2) / 0.1)
        self.dem_data = elevation - river_valley
        
        # Create transform
        self.transform = from_bounds(bounds[0], bounds[1], bounds[2], bounds[3], 
                                   size[1], size[0])
        self.crs = CRS.from_epsg(4326)
        
        print(f"Created sample DEM: {self.dem_data.shape} pixels")
        return self.dem_data
    
    def calculate_slope(self):
        """Calculate slope from DEM"""
        if self.dem_data is None:
            raise ValueError("DEM data not loaded")
        
        # Calculate gradient
        dy, dx = np.gradient(self.dem_data)
        
        # Calculate slope in degrees
        slope_rad = np.arctan(np.sqrt(dx**2 + dy**2))
        slope_deg = np.degrees(slope_rad)
        
        self.features['slope'] = slope_deg
        print("Calculated slope")
        return slope_deg
    
    def calculate_flow_accumulation(self):
        """Calculate flow accumulation (simplified)"""
        if self.dem_data is None:
            raise ValueError("DEM data not loaded")
        
        # Simplified flow accumulation
        # In production, use proper D8 flow direction algorithm
        flow_acc = np.zeros_like(self.dem_data)
        
        # Simple approximation: accumulate based on elevation gradient
        for i in range(1, self.dem_data.shape[0]-1):
            for j in range(1, self.dem_data.shape[1]-1):
                # Count cells that flow into this cell
                neighbors = self.dem_data[i-1:i+2, j-1:j+2]
                center = self.dem_data[i, j]
                # Cells higher than center contribute to flow
                flow_acc[i, j] = np.sum(neighbors > center)
        
        self.features['flow_accumulation'] = flow_acc
        print("Calculated flow accumulation")
        return flow_acc
    
    def calculate_hand(self, river_threshold=50):
        """
        Calculate HAND (Height Above Nearest Drainage)
        Simplified version - in production use proper drainage network extraction
        """
        if self.dem_data is None:
            raise ValueError("DEM data not loaded")
        
        # Identify drainage network (low elevation areas)
        drainage = self.dem_data < np.percentile(self.dem_data, river_threshold)
        
        # Calculate distance to nearest drainage
        from scipy.ndimage import distance_transform_edt
        hand = distance_transform_edt(~drainage)
        
        # Convert to height above drainage
        hand_elevation = self.dem_data - np.min(self.dem_data[drainage]) if np.any(drainage) else self.dem_data
        
        self.features['hand'] = hand_elevation
        print("Calculated HAND")
        return hand_elevation
    
    def calculate_twi(self):
        """
        Calculate TWI (Topographic Wetness Index)
        TWI = ln(Flow_Accumulation / tan(Slope))
        """
        if 'flow_accumulation' not in self.features:
            self.calculate_flow_accumulation()
        if 'slope' not in self.features:
            self.calculate_slope()
        
        flow_acc = self.features['flow_accumulation']
        slope = self.features['slope']
        
        # Avoid division by zero
        slope_rad = np.radians(np.maximum(slope, 0.1))
        tan_slope = np.tan(slope_rad)
        
        # Calculate TWI
        twi = np.log((flow_acc + 1) / (tan_slope + 0.001))
        
        self.features['twi'] = twi
        print("Calculated TWI")
        return twi
    
    def calculate_distance_to_river(self):
        """Calculate distance to nearest river"""
        if self.dem_data is None:
            raise ValueError("DEM data not loaded")
        
        # Identify rivers (low elevation areas)
        river_threshold = np.percentile(self.dem_data, 30)
        rivers = self.dem_data < river_threshold
        
        # Calculate distance to nearest river
        from scipy.ndimage import distance_transform_edt
        dist_to_river = distance_transform_edt(~rivers)
        
        self.features['distance_to_river'] = dist_to_river
        print("Calculated distance to river")
        return dist_to_river
    
    def extract_all_features(self):
        """Extract all topographic features"""
        print("🔄 Extracting topographic features...")
        self.calculate_slope()
        self.calculate_flow_accumulation()
        self.calculate_hand()
        self.calculate_twi()
        self.calculate_distance_to_river()
        print("All features extracted")
        return self.features
    
    def save_features(self, output_dir="data/processed"):
        """Save extracted features as GeoTIFF files"""
        os.makedirs(output_dir, exist_ok=True)
        
        for feature_name, feature_data in self.features.items():
            output_path = os.path.join(output_dir, f"{feature_name}.tif")
            
            with rasterio.open(
                output_path,
                'w',
                driver='GTiff',
                height=feature_data.shape[0],
                width=feature_data.shape[1],
                count=1,
                dtype=feature_data.dtype,
                crs=self.crs,
                transform=self.transform
            ) as dst:
                dst.write(feature_data, 1)
            
            print(f"Saved {feature_name} to {output_path}")
        
        return output_dir



