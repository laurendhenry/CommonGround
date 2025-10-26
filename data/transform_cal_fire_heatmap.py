# transform_cal_fire_heatmap.py
# ---------------------------------------------------------------------
# CAL FIRE Fire Hazard Severity Zones → Leaflet-ready GeoJSON
# Converts from EPSG:3310 → EPSG:4326, adds fire_hazard_score,
# simplifies geometry, and exports to /data/cal_fire_heatmap.json
# ---------------------------------------------------------------------

import os
import json
import geopandas as gpd

# ---------------------------------------------------------------------
# 1️⃣ Load dataset (download manually first from CA Open Data)
# ---------------------------------------------------------------------
# Try to find the downloaded file (may have downloaded with ArcGIS suffix)
import glob
geojson_files = glob.glob("data/FHSZ_SRA_LRA_Combined*.geojson") + \
                glob.glob("data/cal_fire_fhsz.geojson")

if not geojson_files:
    raise FileNotFoundError(
        f"File not found!\n"
        "Download GeoJSON from:\n"
        "https://www.lab.data.ca.gov/dataset/"
        "fire-hazard-severity-zones-in-sra-effective-april-1-2024-with-lra-recommended-2007-2011\n"
        "and place it in the data/ folder"
    )

input_path = geojson_files[0]
print(f"📂 Using file: {input_path}")

print("📥 Loading GeoJSON...")
gdf = gpd.read_file(input_path)
print(f"✅ Loaded {len(gdf)} features. CRS = {gdf.crs}")

# ---------------------------------------------------------------------
# 2️⃣ Reproject EPSG:3310 → EPSG:4326
# ---------------------------------------------------------------------
try:
    gdf = gdf.to_crs(epsg=4326)
    print("🌎 Reprojected to EPSG:4326 (lat/lng).")
except Exception as e:
    raise RuntimeError(f"Error reprojecting CRS: {e}")

# ---------------------------------------------------------------------
# 3️⃣ Identify hazard column & compute score
# ---------------------------------------------------------------------
print("\n" + "="*60)
print("Available columns:")
for i, col in enumerate(gdf.columns, 1):
    print(f"  {i}. {col}")
print("="*60)

# Prefer descriptive column names in order
possible_cols = ["FHSZ_Description", "FHSZ", "FHSZ_7Class", "Hazard"]
hazard_col = None
for c in possible_cols:
    if c in gdf.columns:
        hazard_col = c
        break

# If not found, try fuzzy matching on column names
if not hazard_col:
    for c in gdf.columns:
        c_lower = c.lower()
        if any(keyword in c_lower for keyword in ['hazard', 'fhs', 'moderate', 'high']):
            if 'geometry' not in c_lower:
                hazard_col = c
                print(f"⚠️  Matched by keyword: {hazard_col}")
                break

if not hazard_col:
    print("\n❌ ERROR: No hazard column found!")
    print("\nPossible solutions:")
    print("1. Check if the column name matches: FHSZ_Description, FHSZ, FHSZ_7Class, or Hazard")
    print("2. Edit the 'possible_cols' list in the script (around line 44)")
    print("3. Manually specify the column by adding it to possible_cols")
    raise ValueError("No hazard column found in dataset. See columns printed above.")
else:
    print(f"\n✅ Using hazard column: '{hazard_col}'")
    
    # Show sample values to verify the column is correct
    print("\nSample values from hazard column:")
    unique_vals = gdf[hazard_col].value_counts().head(10)
    for val, count in unique_vals.items():
        print(f"  '{val}': {count} features")
    print(f"  ... ({len(gdf[hazard_col].unique())} unique values total)\n")

# Map hazard categories to numeric scores
# Expanded mapping to handle various data formats
hazard_map = {
    "Moderate": 0.5,
    "High": 0.75,
    "Very High": 1.0,
    "Very High Fire Hazard Severity Zone": 1.0,
    "High Fire Hazard Severity Zone": 0.75,
    "Moderate Fire Hazard Severity Zone": 0.5,
    "Mh": 0.6,
    "M": 0.5,
    "H": 0.75,
    "Vh": 1.0,
    "Vhfv": 1.0,
    "Moderate/High": 0.6,
}

def map_hazard_value(val):
    if val is None:
        return 0
    val_str = str(val).strip()
    
    # Try exact match first
    if val_str in hazard_map:
        return hazard_map[val_str]
    
    # Try case-insensitive title case
    val_title = val_str.title()
    if val_title in hazard_map:
        return hazard_map[val_title]
    
    # Check for keywords
    val_lower = val_str.lower()
    if 'very' in val_lower and 'high' in val_lower:
        return 1.0
    elif 'high' in val_lower and 'moderate' not in val_lower:
        return 0.75
    elif 'moderate' in val_lower:
        return 0.5
    else:
        # If no match, return 0 (safe default)
        print(f"⚠️  Warning: Unknown hazard value '{val_str}', mapped to 0")
        return 0

gdf["fire_hazard_class"] = gdf[hazard_col].astype(str)
gdf["fire_hazard_score"] = gdf[hazard_col].apply(map_hazard_value)

# Report mapping summary
print("Hazard score mapping summary:")
score_summary = gdf.groupby('fire_hazard_class')['fire_hazard_score'].first().sort_values(ascending=False)
for hazard, score in score_summary.items():
    count = (gdf['fire_hazard_class'] == hazard).sum()
    print(f"  {hazard}: {score} ({count} features)")
print()

# ---------------------------------------------------------------------
# 4️⃣ Simplify geometries to reduce file size
# ---------------------------------------------------------------------
print("🪄 Simplifying and dissolving geometries for web use...")

# Keep only needed columns
gdf = gdf[["fire_hazard_class", "fire_hazard_score", "geometry"]]

# Merge polygons by hazard level
gdf = gdf.dissolve(by="fire_hazard_class", as_index=False)

# Add area column before simplification for filtering small areas
gdf["area"] = gdf.geometry.area

print(f"📊 Features before simplification: {len(gdf)}")

# Remove very small polygons (< 0.1% of total area) to reduce noise
total_area = gdf["area"].sum()
area_threshold = total_area * 0.001
gdf = gdf[gdf["area"] > area_threshold].copy()
print(f"🗜️  Removed small polygons, {len(gdf)} features remaining")

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

print(f"✅ Final feature count: {len(gdf)}")


# ---------------------------------------------------------------------
# 5️⃣ Keep only relevant columns
# ---------------------------------------------------------------------
keep_cols = ["fire_hazard_class", "fire_hazard_score", "geometry"]
gdf = gdf[keep_cols]



# ---------------------------------------------------------------------
# 6️⃣ Export to clean GeoJSON with reduced precision
# ---------------------------------------------------------------------
output_dir = "data"
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, "cal_fire_heatmap.json")

print("💾 Saving to GeoJSON for Leaflet...")
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
    print(f"✅ Saved {len(gdf)} features to {output_path}")
    print(f"📦 File size: {file_size:.2f} MB")
    
    # GitHub file size guidelines
    if file_size > 50:
        print("\n⚠️  WARNING: File exceeds GitHub's recommended 50MB limit!")
        print("   Consider increasing SIMPLIFICATION_TOLERANCE to 0.005 or higher")
    elif file_size > 10:
        print("\n⚠️  NOTE: File is over 10MB - may take longer to load")
        print("   For faster loading, consider SIMPLIFICATION_TOLERANCE = 0.005")
    else:
        print("✅ File size is good for GitHub!")
except Exception as e:
    raise RuntimeError(f"Error saving GeoJSON: {e}")

print("\n🚀 Done! You can now use this file directly in Leaflet or Postman.")
print("Example Leaflet usage:")
print("""
fetch('https://raw.githubusercontent.com/<username>/<repo>/main/data/cal_fire_heatmap.json')
  .then(res => res.json())
  .then(data => {
    L.geoJSON(data, {
      style: f => ({
        fillColor: f.properties.fire_hazard_score > 0.9 ? '#ff0000' :
                   f.properties.fire_hazard_score > 0.7 ? '#ff8000' :
                   f.properties.fire_hazard_score > 0.5 ? '#ffff00' :
                                                          '#00ff00',
        fillOpacity: 0.6,
        color: '#333',
        weight: 0.4
      }),
      onEachFeature: (f, layer) => {
        layer.bindPopup(
          `Hazard: ${f.properties.fire_hazard_class} (score ${f.properties.fire_hazard_score})`
        );
      }
    }).addTo(map);
  });
""")