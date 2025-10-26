# transform_smart_farming.py
# ---------------------------------------------------------------------
# Smart Farming 2024 -> JSON for dashboard (crop stress, irrigation, fire risk)
# Run: python transform_smart_farming.py
# ---------------------------------------------------------------------

import pandas as pd
import kagglehub
import sys
from kagglehub import KaggleDatasetAdapter
from datetime import date

# Load dataset into pandas
print("Loading Smart Farming dataset...")
try:
    df = kagglehub.load_dataset(
        KaggleDatasetAdapter.PANDAS,
        "datasetengineer/smart-farming-data-2024-sf24",
        "Crop_recommendationV2.csv"
    )
except Exception as e:
    print(f"Error loading dataset 'datasetengineer/smart-farming-data-2024-sf24': {str(e)}")
    sys.exit(1)

# Clean columns
df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

# Check expected columns
expected_cols = ["n","p","k","temperature","humidity","ph","rainfall","label","soil_moisture","soil_type"]
missing = [c for c in expected_cols if c not in df.columns]
if missing:
    print("Missing columns:", missing)
    exit(1)

# Derive new metrics
def compute_crop_stress(row):
    # Normalize soil moisture & temperature
    sm = max(0, min(100, row.get("soil_moisture", 0)))
    temp = row.get("temperature", 25)
    stress = (1 - sm/100) * (temp/40)
    return round(min(stress, 1), 3)

def irrigation_recommendation(row):
    sm = row.get("soil_moisture", 0)
    hum = row.get("humidity", 0)
    if sm < 30 and hum < 50:
        return "Increase"
    elif 30 <= sm <= 60:
        return "Maintain"
    else:
        return "Reduce"

def compute_fire_risk(row):
    t = row.get("temperature", 25)
    h = row.get("humidity", 50)
    h_clamped = max(0, min(100, h))
    risk = (t / 45) * (1 - h_clamped/100)
    return round(max(0, min(1, risk)), 3)

df["crop_stress_index"] = df.apply(compute_crop_stress, axis=1)
df["irrigation_recommendation"] = df.apply(irrigation_recommendation, axis=1)
df["fire_risk_index"] = df.apply(compute_fire_risk, axis=1)
df["timestamp"] = date.today().isoformat()

# Select useful fields for export
export_cols = [
    "timestamp","soil_type","n","p","k","temperature","humidity",
    "rainfall","ph","soil_moisture","crop_stress_index",
    "irrigation_recommendation","fire_risk_index","label"
]
out_df = df[export_cols]

# Export to JSON
output_path = "data/smart_farming.json"
try:
    out_df.to_json(output_path, orient="records", indent=2)
    print(f"Saved {len(out_df)} records to {output_path}")
except Exception as e:
    print(f"Failed to write output file: {e}")
    exit(1)