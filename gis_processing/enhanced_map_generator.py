"""
Enhanced Static Map Generator
Creates professional flood hazard maps with river networks, boundaries, and proper styling
Based on the example static map format
"""

import numpy as np
import os
import json
from pathlib import Path

try:
    import geopandas as gpd
    from shapely.geometry import Point, LineString, Polygon, shape
    from shapely.ops import unary_union
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.colors import ListedColormap, BoundaryNorm
    from matplotlib import font_manager
    import contextlib
    GIS_AVAILABLE = True
except ImportError:
    GIS_AVAILABLE = False
    print("Warning: Required libraries not available. Install: pip install geopandas matplotlib")

class EnhancedMapGenerator:
    """
    Generate professional static flood hazard maps
    Similar to the example: Lower Narmada Basin map
    """
    
    def __init__(self):
        self.hazard_zones = None
        self.river_network = None
        self.basin_boundary = None
        self.sub_districts = None
        self.bounds = None
        self.crs = None
    
    def generate_professional_map(self, hazard_zones_gdf, output_path, 
                                   study_area_name="Study Area",
                                   river_network_gdf=None,
                                   basin_boundary_gdf=None,
                                   sub_districts_gdf=None,
                                   bounds=None):
        """
        Generate professional static map with all components
        
        Args:
            hazard_zones_gdf: GeoDataFrame with risk_level column (High/Medium/Low)
            output_path: Path to save PNG
            study_area_name: Name of study area
            river_network_gdf: Optional river network GeoDataFrame
            basin_boundary_gdf: Optional basin boundary GeoDataFrame
            sub_districts_gdf: Optional sub-district boundaries GeoDataFrame
            bounds: [min_lon, min_lat, max_lon, max_lat] for extent
        """
        if not GIS_AVAILABLE:
            print("WARNING: GIS libraries not available. Using simplified map generation.")
            return self._generate_simplified_map(hazard_zones_gdf, output_path)
        
        self.hazard_zones = hazard_zones_gdf
        self.river_network = river_network_gdf
        self.basin_boundary = basin_boundary_gdf
        self.sub_districts = sub_districts_gdf
        
        # Get bounds from hazard zones if not provided
        if bounds is None:
            bounds = list(hazard_zones_gdf.total_bounds)  # [minx, miny, maxx, maxy]
            bounds = [bounds[0], bounds[1], bounds[2], bounds[3]]  # [min_lon, min_lat, max_lon, max_lat]
        
        self.bounds = bounds
        self.crs = hazard_zones_gdf.crs
        
        # Create figure with proper styling
        fig, ax = plt.subplots(figsize=(14, 12))
        ax.set_facecolor('#f5f5f5')
        
        # Plot hazard zones with proper colors
        self._plot_hazard_zones(ax)
        
        # Plot river network
        if river_network_gdf is not None:
            self._plot_river_network(ax)
        
        # Plot sub-district boundaries
        if sub_districts_gdf is not None:
            self._plot_sub_districts(ax)
        
        # Plot basin boundary
        if basin_boundary_gdf is not None:
            self._plot_basin_boundary(ax)
        
        # Add map elements
        self._add_map_elements(ax, study_area_name, bounds)
        
        # Add legend
        self._add_legend(ax)
        
        # Set extent and labels
        ax.set_xlim(bounds[0], bounds[2])
        ax.set_ylim(bounds[1], bounds[3])
        ax.set_xlabel('Longitude (°E)', fontsize=11, fontweight='bold')
        ax.set_ylim(bounds[1], bounds[3])
        ax.set_ylabel('Latitude (°N)', fontsize=11, fontweight='bold')
        
        # Add graticule (grid lines)
        self._add_graticule(ax, bounds)
        
        # Add scale bar
        self._add_scale_bar(ax, bounds)
        
        # Add north arrow
        self._add_north_arrow(ax)
        
        # Title
        title = f"Flood Risk - {study_area_name}"
        ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
        
        # Save
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close()
        
        print(f"Generated professional static map: {output_path}")
        return output_path
    
    def _plot_hazard_zones(self, ax):
        """Plot hazard zones with proper colors"""
        # Color scheme matching example
        colors = {
            'High': '#d73027',      # Red
            'Medium': '#fee08b',    # Yellow/Orange
            'Low': '#a6d96a',       # Light Green
            'No Risk': '#ffffcc'    # Cream
        }
        
        for risk_level in ['High', 'Medium', 'Low', 'No Risk']:
            zones = self.hazard_zones[self.hazard_zones['risk_level'] == risk_level]
            if len(zones) > 0:
                zones.plot(ax=ax, color=colors.get(risk_level, '#cccccc'), 
                          edgecolor='black', linewidth=0.5, alpha=0.7,
                          label=f'{risk_level} Risk')
    
    def _plot_river_network(self, ax):
        """Plot river network in blue"""
        if self.river_network is not None:
            self.river_network.plot(ax=ax, color='#2166ac', linewidth=1.5, 
                                   alpha=0.8, zorder=5)
    
    def _plot_sub_districts(self, ax):
        """Plot sub-district boundaries"""
        if self.sub_districts is not None:
            self.sub_districts.plot(ax=ax, facecolor='none', 
                                   edgecolor='black', linewidth=0.8,
                                   linestyle='--', alpha=0.6)
            
            # Add labels if name column exists
            if 'name' in self.sub_districts.columns:
                for idx, row in self.sub_districts.iterrows():
                    centroid = row.geometry.centroid
                    ax.text(centroid.x, centroid.y, row['name'],
                           fontsize=8, ha='center', va='center',
                           bbox=dict(boxstyle='round,pad=0.3', facecolor='white', 
                                    alpha=0.7, edgecolor='none'))
    
    def _plot_basin_boundary(self, ax):
        """Plot basin boundary as thick black line"""
        if self.basin_boundary is not None:
            self.basin_boundary.plot(ax=ax, facecolor='none',
                                    edgecolor='black', linewidth=2.5,
                                    linestyle='-', zorder=10)
    
    def _add_map_elements(self, ax, study_area_name, bounds):
        """Add map elements like title, labels"""
        # Add subtitle
        subtitle = f"{study_area_name} - Flood Risk Assessment"
        ax.text(0.5, 0.98, subtitle, transform=ax.transAxes,
               fontsize=12, ha='center', va='top',
               bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    
    def _add_legend(self, ax):
        """Add comprehensive legend"""
        legend_elements = []
        
        # Hazard zones
        legend_elements.append(mpatches.Patch(facecolor='#d73027', 
                                             edgecolor='black', 
                                             label='High Risk'))
        legend_elements.append(mpatches.Patch(facecolor='#fee08b', 
                                             edgecolor='black', 
                                             label='Moderate Risk'))
        legend_elements.append(mpatches.Patch(facecolor='#a6d96a', 
                                             edgecolor='black', 
                                             label='Low Risk'))
        legend_elements.append(mpatches.Patch(facecolor='#ffffcc', 
                                             edgecolor='black', 
                                             label='No Risk'))
        
        # River network
        if self.river_network is not None:
            from matplotlib.lines import Line2D
            legend_elements.append(Line2D([0], [0], color='#2166ac', 
                                         linewidth=1.5, label='River Network'))
        
        # Basin boundary
        if self.basin_boundary is not None:
            from matplotlib.lines import Line2D
            legend_elements.append(Line2D([0], [0], color='black', 
                                         linewidth=2.5, label='Basin Boundary'))
        
        # Sub-districts
        if self.sub_districts is not None:
            from matplotlib.lines import Line2D
            legend_elements.append(Line2D([0], [0], color='black', 
                                         linewidth=0.8, linestyle='--',
                                         label='Sub-district Map'))
        
        ax.legend(handles=legend_elements, loc='upper left', 
                 frameon=True, fancybox=True, shadow=True,
                 fontsize=10, title='Legend', title_fontsize=11)
    
    def _add_graticule(self, ax, bounds):
        """Add latitude/longitude grid lines"""
        # Calculate step size
        lon_range = bounds[2] - bounds[0]
        lat_range = bounds[3] - bounds[1]
        
        lon_step = max(0.25, round(lon_range / 5, 2))
        lat_step = max(0.25, round(lat_range / 5, 2))
        
        # Longitude lines
        lon_lines = np.arange(np.floor(bounds[0]), np.ceil(bounds[2]) + lon_step, lon_step)
        for lon in lon_lines:
            if bounds[0] <= lon <= bounds[2]:
                ax.axvline(lon, color='gray', linewidth=0.5, alpha=0.5, linestyle=':')
                # Add label
                ax.text(lon, bounds[1] - (bounds[3] - bounds[1]) * 0.02,
                       f"{lon:.2f}°E", fontsize=8, ha='center')
        
        # Latitude lines
        lat_lines = np.arange(np.floor(bounds[1]), np.ceil(bounds[3]) + lat_step, lat_step)
        for lat in lat_lines:
            if bounds[1] <= lat <= bounds[3]:
                ax.axhline(lat, color='gray', linewidth=0.5, alpha=0.5, linestyle=':')
                # Add label
                ax.text(bounds[0] - (bounds[2] - bounds[0]) * 0.02, lat,
                       f"{lat:.2f}°N", fontsize=8, va='center')
    
    def _add_scale_bar(self, ax, bounds):
        """Add scale bar"""
        # Calculate approximate distance for scale bar
        # Use 1 degree ≈ 111 km at equator
        lon_range = bounds[2] - bounds[0]
        center_lat = (bounds[1] + bounds[3]) / 2
        km_per_degree = 111 * np.cos(np.radians(center_lat))
        
        # Create 50 km scale bar
        scale_km = 50
        scale_degrees = scale_km / km_per_degree
        
        # Position at bottom right
        bar_x = bounds[2] - (bounds[2] - bounds[0]) * 0.15
        bar_y = bounds[1] + (bounds[3] - bounds[1]) * 0.05
        
        # Draw scale bar
        ax.plot([bar_x, bar_x + scale_degrees], [bar_y, bar_y], 
               'k-', linewidth=3, transform=ax.transData)
        ax.plot([bar_x, bar_x], [bar_y - scale_degrees*0.02, bar_y + scale_degrees*0.02],
               'k-', linewidth=3, transform=ax.transData)
        ax.plot([bar_x + scale_degrees, bar_x + scale_degrees],
               [bar_y - scale_degrees*0.02, bar_y + scale_degrees*0.02],
               'k-', linewidth=3, transform=ax.transData)
        
        # Add label
        ax.text(bar_x + scale_degrees/2, bar_y - scale_degrees*0.05,
               f'{scale_km} Kilometers', fontsize=9, ha='center',
               bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
    
    def _add_north_arrow(self, ax):
        """Add north arrow"""
        bounds = self.bounds
        # Position at top right
        arrow_x = bounds[2] - (bounds[2] - bounds[0]) * 0.1
        arrow_y = bounds[3] - (bounds[3] - bounds[1]) * 0.1
        
        # Draw arrow
        arrow_length = (bounds[2] - bounds[0]) * 0.03
        ax.annotate('', xy=(arrow_x, arrow_y + arrow_length),
                   xytext=(arrow_x, arrow_y),
                   arrowprops=dict(arrowstyle='->', lw=2, color='black'))
        ax.text(arrow_x, arrow_y + arrow_length * 1.2, 'N',
               fontsize=12, fontweight='bold', ha='center',
               bbox=dict(boxstyle='circle', facecolor='white', edgecolor='black'))
    
    def _generate_simplified_map(self, hazard_zones_gdf, output_path):
        """Fallback simplified map generation"""
        import matplotlib.pyplot as plt
        
        fig, ax = plt.subplots(figsize=(12, 10))
        
        if GIS_AVAILABLE and hazard_zones_gdf is not None:
            hazard_zones_gdf.plot(ax=ax, column='risk_level', 
                                legend=True, cmap='RdYlGn_r')
        
        ax.set_title('Flood Hazard Map', fontsize=16, fontweight='bold')
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        return output_path
    
    def create_sample_river_network(self, bounds):
        """Create sample river network for demonstration"""
        if not GIS_AVAILABLE:
            return None
        
        # Create a simple river network (main river + tributaries)
        rivers = []
        
        # Main river (flows through center)
        center_lon = (bounds[0] + bounds[2]) / 2
        center_lat = (bounds[1] + bounds[3]) / 2
        
        # Main river
        main_river = LineString([
            (bounds[0] + (bounds[2] - bounds[0]) * 0.2, bounds[1] + (bounds[3] - bounds[1]) * 0.8),
            (center_lon, center_lat),
            (bounds[0] + (bounds[2] - bounds[0]) * 0.8, bounds[1] + (bounds[3] - bounds[1]) * 0.2)
        ])
        rivers.append({'geometry': main_river, 'name': 'Main River'})
        
        # Tributaries
        for i in range(3):
            start_lon = bounds[0] + (bounds[2] - bounds[0]) * (0.3 + i * 0.15)
            start_lat = bounds[1] + (bounds[3] - bounds[1]) * (0.7 - i * 0.1)
            end_lon = center_lon + (bounds[2] - bounds[0]) * 0.1 * (-1 if i % 2 == 0 else 1)
            end_lat = center_lat
            
            tributary = LineString([(start_lon, start_lat), (end_lon, end_lat)])
            rivers.append({'geometry': tributary, 'name': f'Tributary {i+1}'})
        
        gdf = gpd.GeoDataFrame(rivers, crs='EPSG:4326')
        return gdf
    
    def create_sample_sub_districts(self, bounds, n_districts=8):
        """Create sample sub-district boundaries"""
        if not GIS_AVAILABLE:
            return None
        
        districts = []
        lon_step = (bounds[2] - bounds[0]) / 3
        lat_step = (bounds[3] - bounds[1]) / 3
        
        district_names = ['Bharuch', 'Sinor', 'Jhagadia', 'Rajpipla', 
                          'Dediapada', 'Mangrol', 'Sankheda', 'Naswadi']
        
        idx = 0
        for i in range(3):
            for j in range(3):
                if idx >= n_districts:
                    break
                
                min_lon = bounds[0] + i * lon_step
                max_lon = bounds[0] + (i + 1) * lon_step
                min_lat = bounds[1] + j * lat_step
                max_lat = bounds[1] + (j + 1) * lat_step
                
                district = Polygon([
                    (min_lon, min_lat),
                    (max_lon, min_lat),
                    (max_lon, max_lat),
                    (min_lon, max_lat)
                ])
                
                districts.append({
                    'geometry': district,
                    'name': district_names[idx] if idx < len(district_names) else f'District {idx+1}'
                })
                idx += 1
        
        gdf = gpd.GeoDataFrame(districts, crs='EPSG:4326')
        return gdf



