# tranform_seismic_hazards.py
# ---------------------------------------------------------------------
# CGS Liquefaction Zones → Leaflet-ready GeoJSON
# Converts from EPSG:3310 → EPSG:4326, adds seismic_hazard_score,
# simplifies geometry, and exports to /data/seismic_hazards.json
# ---------------------------------------------------------------------

import os
import json
import geopandas as gpd
import glob

# ---------------------------------------------------------------------
# 1️⃣ Load dataset (CGS Liquefaction Zones)
# ---------------------------------------------------------------------
# Try to find the downloaded file
geojson_files = glob.glob("data/CGS_Liquefaction_Zones*.geojson") + \
                glob.glob("data/seismic_liquefaction.geojson")

if not geojson_files:
    raise FileNotFoundError(
        f"File not found!\n"
        "Download CGS Liquefaction Zones GeoJSON from:\n"
        "https://www.conservation.ca.gov/cgs/topo-and-geologic-maps/maps/liquefaction-zones\n"
        "and place it in the data/ folder"
    )

input_path = geojson_files[0]
print(f"[FILE] Using file: {input_path}")

print("[LOAD] Loading GeoJSON...")
gdf = gpd.read_file(input_path)
print(f"[OK] Loaded {len(gdf)} features. CRS = {gdf.crs}")

# ---------------------------------------------------------------------
# 2️⃣ Reproject EPSG:3310 → EPSG:4326
# ---------------------------------------------------------------------
try:
    gdf = gdf.to_crs(epsg=4326)
    print("[REPROJECT] Reprojected to EPSG:4326 (lat/lng).")
except Exception as e:
    raise RuntimeError(f"Error reprojecting CRS: {e}")

# ---------------------------------------------------------------------
# 3️⃣ Identify key columns & create seismic hazard score
# ---------------------------------------------------------------------
print("\n" + "="*60)
print("Available columns:")
for i, col in enumerate(gdf.columns, 1):
    print(f"  {i}. {col}")
print("="*60)

# For liquefaction zones, all areas are potential seismic hazards
# We'll assign a uniform high score since these are all areas
# of known or potential liquefaction during seismic events
print("\n[INFO] All liquefaction zones represent potential seismic hazards")
print("       Assigning uniform high hazard score (1.0) to all zones")

# Create seismic hazard classification
gdf["seismic_hazard_class"] = "Liquefaction Zone"
gdf["seismic_hazard_score"] = 1.0  # High score for all liquefaction zones

# Keep relevant metadata
if "QUAD_NAME" in gdf.columns:
    gdf["location_name"] = gdf["QUAD_NAME"]
if "RELEASED" in gdf.columns:
    gdf["data_date"] = gdf["RELEASED"].astype(str)

# Show summary
print("\n[SUMMARY] Seismic hazard classification summary:")
zone_count = len(gdf)
print(f"  Liquefaction Zones: {zone_count} features (score: 1.0)")
print()

# ---------------------------------------------------------------------
# 4️⃣ Simplify geometries to reduce file size
# ---------------------------------------------------------------------
print("[SIMPLIFY] Simplifying and dissolving geometries for web use...")

# Keep only needed columns
cols_to_keep = ["seismic_hazard_class", "seismic_hazard_score", "geometry"]
if "location_name" in gdf.columns:
    cols_to_keep.append("location_name")
if "data_date" in gdf.columns:
    cols_to_keep.append("data_date")

gdf = gdf[cols_to_keep]

# Merge polygons by hazard level (all same class in this case)
if "seismic_hazard_class" in gdf.columns:
    gdf = gdf.dissolve(by="seismic_hazard_class", as_index=False)

# Add area column before simplification for filtering small areas
gdf["area"] = gdf.geometry.area

print(f"[COUNT] Features before simplification: {len(gdf)}")

# Remove very small polygons (< 0.1% of total area) to reduce noise
total_area = gdf["area"].sum()
area_threshold = total_area * 0.001
gdf = gdf[gdf["area"] > area_threshold].copy()
print(f"[FILTER] Removed small polygons, {len(gdf)} features remaining")

# Simplify shapes aggressively to reduce file size for GitHub
# Tolerance values guide:
#   0.0001 → Very detailed (~50-100MB file) 
#   0.001  → Detailed (~10-20MB file)
#   0.002  → Balanced for GitHub (~5-10MB file) ← Recommended
#   0.005  → Smaller (~2-5MB file) - may lose some detail
#   0.01   → Very small (~1-2MB file) - may look blocky
# Lower value = more detail but larger file size
SIMPLIFICATION_TOLERANCE = 0.002  # Adjust this to balance size vs quality

gdf["geometry"] = gdf["geometry"].simplify(
    tolerance=SIMPLIFICATION_TOLERANCE, 
    preserve_topology=True
)

# Remove the temporary area column
gdf = gdf.drop(columns=["area"])

print(f"[OK] Final feature count: {len(gdf)}")


# ---------------------------------------------------------------------
# 5️⃣ Keep only relevant columns
# ---------------------------------------------------------------------
keep_cols = ["seismic_hazard_class", "seismic_hazard_score", "geometry"]
if "location_name" in gdf.columns:
    keep_cols.append("location_name")
if "data_date" in gdf.columns:
    keep_cols.append("data_date")

gdf = gdf[keep_cols]



# ---------------------------------------------------------------------
# 6️⃣ Export to clean GeoJSON with reduced precision
# ---------------------------------------------------------------------
output_dir = "data"
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, "seismic_hazards.json")

print("[SAVE] Saving to GeoJSON for Leaflet...")
try:
    # Round coordinates to 4 decimal places (~11 meters precision) to reduce file size
    # Lower precision (e.g., 3 decimals for ~111 meters) can be used if file still too large
    COORD_PRECISION = 4
    
    gdf.to_file(output_path, driver="GeoJSON")
    
    # Post-process to round coordinates (simplify GeoJSON)
    with open(output_path, 'r', encoding='utf-8') as f:
        geojson = json.load(f)
    
    def round_coords(coords):
        if isinstance(coords[0], list):
            return [round_coords(c) for c in coords]
        else:
            return [round(coord, COORD_PRECISION) for coord in coords]
    
    if geojson.get('type') == 'FeatureCollection':
        for feature in geojson['features']:
            if feature.get('geometry') and 'coordinates' in feature['geometry']:
                feature['geometry']['coordinates'] = round_coords(feature['geometry']['coordinates'])
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(geojson, f)
    
    file_size = os.path.getsize(output_path) / (1024 * 1024)  # Size in MB
    print(f"[OK] Saved {len(gdf)} features to {output_path}")
    print(f"[SIZE] File size: {file_size:.2f} MB")
    
    # GitHub file size guidelines
    if file_size > 50:
        print("\n[WARNING] File exceeds GitHub's recommended 50MB limit!")
        print("          Consider increasing SIMPLIFICATION_TOLERANCE to 0.005 or higher")
    elif file_size > 10:
        print("\n[NOTE] File is over 10MB - may take longer to load")
        print("       For faster loading, consider SIMPLIFICATION_TOLERANCE = 0.005")
    else:
        print("[OK] File size is good for GitHub!")
except Exception as e:
    raise RuntimeError(f"Error saving GeoJSON: {e}")

print("\n[DONE] Done! You can now use this file directly in Leaflet or Postman.")
print("Example Leaflet usage:")
print("""
fetch('https://raw.githubusercontent.com/<username>/<repo>/main/data/seismic_hazards.json')
  .then(res => res.json())
  .then(data => {
    L.geoJSON(data, {
      style: f => ({
        fillColor: f.properties.seismic_hazard_score > 0.9 ? '#ff0000' :
                   f.properties.seismic_hazard_score > 0.7 ? '#ff8000' :
                   f.properties.seismic_hazard_score > 0.5 ? '#ffff00' :
                                                             '#00ff00',
        fillOpacity: 0.4,
        color: '#333',
        weight: 0.5
      }),
      onEachFeature: (f, layer) => {
        const props = f.properties;
        layer.bindPopup(
          `Hazard: ${props.seismic_hazard_class} (score ${props.seismic_hazard_score})
          ${props.location_name ? '<br/>Location: ' + props.location_name : ''}
          ${props.data_date ? '<br/>Data Date: ' + props.data_date : ''}`
        );
      }
    }).addTo(map);
  });
""")

