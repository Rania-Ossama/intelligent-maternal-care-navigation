
from pathlib import Path
import geopandas as gpd


# ==================================================
# CONFIGURATION
# ==================================================

INPUT_DIR = Path("boundaries_data/raw/egy_admin_boundaries.geojson")
OUTPUT_DIR = Path("boundaries_data/processed")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


FILES = {
    "egy_admin1.geojson": "egypt_governorates.geojson",
    "egy_admin2.geojson": "egypt_districts.geojson",
    "egy_admin3.geojson": "egypt_adm3.geojson",
}


# ==================================================
# EXTRACT AND PROCESS
# ==================================================

for input_name, output_name in FILES.items():

    input_path = INPUT_DIR / input_name
    output_path = OUTPUT_DIR / output_name

    print(f"\nProcessing {input_name}...")

    if not input_path.is_file():
        print(f"ERROR: File not found: {input_path}")
        continue

    # Load GeoJSON
    gdf = gpd.read_file(input_path)

    # Check CRS
    if gdf.crs is None:
        raise ValueError(f"Missing CRS in {input_name}")

    # Convert to WGS84 for web maps and coordinate matching
    gdf = gdf.to_crs(epsg=4326)

    # Remove empty or missing geometries
    gdf = gdf[
        gdf.geometry.notna() & ~gdf.geometry.is_empty
    ].copy()

    # Save processed GeoJSON
    gdf.to_file(
        output_path,
        driver="GeoJSON",
        index=False
    )

    print(f"  Features: {len(gdf):,}")
    print(f"  CRS: {gdf.crs}")
    print(f"  Columns: {list(gdf.columns)}")
    print(f"  Saved: {output_path}")


print("\nExtraction completed!")
