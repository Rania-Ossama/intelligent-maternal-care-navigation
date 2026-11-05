
import argparse
import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd

from pyrosm import OSM
from shapely import make_valid
from shapely.geometry import Point


# ============================================================
# CONFIGURATION
# ============================================================

# Broad Egypt bounding box:
# These bounds are intentionally generous.
# They are NOT a replacement for the official Egypt boundary.
EGYPT_BBOX = {
    "min_lon": 24.0,
    "max_lon": 38.0,
    "min_lat": 21.0,
    "max_lat": 32.5,
}

# Pyrosm combines these filters using OR.
# healthcare=True captures all values of the healthcare key.
OSM_FILTER = {
    "healthcare": True,

    "amenity": [
        "hospital",
        "clinic",
        "doctors",
        "dentist",
        "pharmacy",
        "blood_bank",
        "nursing_home",
        "health_post",
        "ambulance_station",
    ],

    "shop": [
        "chemist",
        "medical_supply",
        "optician",
        "hearing_aids",
    ],

    "office": [
        "physician",
        "therapist",
    ],
}

# Common OSM tags that we want as convenient CSV columns.
# Everything else remains available in all_tags.
TAG_COLUMN_MAP = {
    "name": "name",
    "name:en": "name_en",
    "name:ar": "name_ar",
    "official_name": "official_name",
    "short_name": "short_name",

    "brand": "brand",
    "operator": "operator",
    "operator:type": "operator_type",
    "network": "network",
    "ref": "ref",

    "phone": "phone",
    "contact:phone": "contact_phone",
    "email": "email",
    "contact:email": "contact_email",
    "website": "website",
    "contact:website": "contact_website",
    "fax": "fax",

    "addr:full": "addr_full",
    "addr:street": "addr_street",
    "addr:housenumber": "addr_housenumber",
    "addr:city": "addr_city",
    "addr:suburb": "addr_suburb",
    "addr:district": "addr_district",
    "addr:postcode": "addr_postcode",
    "addr:state": "addr_state",
    "addr:country": "addr_country",

    "beds": "beds",
    "staff_count": "staff_count",
    "emergency": "emergency",
    "wheelchair": "wheelchair",
    "opening_hours": "opening_hours",

    "healthcare:speciality": "healthcare_speciality",
    "healthcare:specialty": "healthcare_specialty",

    "ownership": "ownership",
    "level": "level",
    "access": "access",
    "fee": "fee",
    "dispensing": "dispensing",

    "building": "building",
    "description": "description",
    "note": "note",
    "source": "source",
}

STRUCTURAL_COLUMNS = {
    "id",
    "osm_id",
    "osm_type",
    "timestamp",
    "version",
    "changeset",
    "tags",
    "geometry",
}


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def is_missing(value):
    """Safely check whether a value is missing."""

    if value is None:
        return True

    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def parse_tags(row):
    """
    Recover the complete tag dictionary.

    Pyrosm may return some requested/filter tags as separate
    columns and the remaining tags in the 'tags' column.
    We combine both.
    """

    tags = {}

    raw_tags = row.get("tags")

    if isinstance(raw_tags, dict):
        tags.update(raw_tags)

    elif isinstance(raw_tags, str):
        try:
            parsed = json.loads(raw_tags)

            if isinstance(parsed, dict):
                tags.update(parsed)

        except json.JSONDecodeError:
            pass

    # Recover any tags that Pyrosm exposed as separate columns.
    for key, value in row.items():

        if key in STRUCTURAL_COLUMNS:
            continue

        if is_missing(value):
            continue

        tags.setdefault(str(key), str(value))

    # Ensure values are JSON serializable.
    return {
        str(key): str(value)
        for key, value in tags.items()
        if value is not None
    }


def classify_facility(tags):
    """
    Create a normalized facility category.

    Original OSM classifications remain untouched in all_tags.
    """

    healthcare = tags.get("healthcare")
    amenity = tags.get("amenity")
    shop = tags.get("shop")
    office = tags.get("office")

    # Prefer a specific healthcare classification.
    if healthcare and healthcare.lower() not in {"yes", "no"}:
        return healthcare.lower()

    amenity_mapping = {
        "doctors": "doctor",
        "dentist": "dentist",
        "hospital": "hospital",
        "clinic": "clinic",
        "pharmacy": "pharmacy",
        "blood_bank": "blood_bank",
        "nursing_home": "nursing_home",
        "health_post": "health_post",
        "ambulance_station": "ambulance_station",
    }

    if amenity in amenity_mapping:
        return amenity_mapping[amenity]

    shop_mapping = {
        "chemist": "pharmacy",
        "medical_supply": "medical_supply",
        "optician": "optician",
        "hearing_aids": "hearing_aids",
    }

    if shop in shop_mapping:
        return shop_mapping[shop]

    if office:
        return office

    if healthcare:
        return "unclassified_healthcare"

    return "unclassified_medical"


def repair_geometry(geometry):
    """
    Return a valid geometry when possible.

    The original WKT is preserved separately.
    """

    if geometry is None or geometry.is_empty:
        return geometry, False, False

    original_valid = geometry.is_valid

    if original_valid:
        return geometry, True, False

    try:
        repaired = make_valid(geometry)

        if repaired is not None and not repaired.is_empty:
            return repaired, False, True

    except Exception:
        pass

    return geometry, False, False


def get_coordinates(geometry):
    """
    Generate a representative coordinate.

    Points retain their original coordinates.
    Other geometries use representative_point(), which
    guarantees a point within the geometry where possible.
    """

    if geometry is None or geometry.is_empty:
        return None, None, "unavailable"

    try:
        if geometry.geom_type == "Point":
            point = geometry
            source = "original_point"
        else:
            point = geometry.representative_point()
            source = "representative_point"

        return point.y, point.x, source

    except Exception:
        return None, None, "unavailable"


def validate_coordinates(latitude, longitude):
    """Validate coordinate ranges and approximate Egypt location."""

    if latitude is None or longitude is None:
        return False, None, "Missing coordinates"

    if not (-90 <= latitude <= 90):
        return False, False, "Invalid latitude"

    if not (-180 <= longitude <= 180):
        return False, False, "Invalid longitude"

    inside_bbox = (
        EGYPT_BBOX["min_lon"] <= longitude <= EGYPT_BBOX["max_lon"]
        and EGYPT_BBOX["min_lat"] <= latitude <= EGYPT_BBOX["max_lat"]
    )

    if not inside_bbox:
        return True, False, "Outside approximate Egypt bounding box"

    return True, True, ""


def get_osm_timestamp(value):
    """Convert OSM timestamps to UTC pandas timestamps."""

    if is_missing(value):
        return pd.NaT

    return pd.to_datetime(value, utc=True, errors="coerce")


# ============================================================
# PROCESS FACILITIES
# ============================================================

def process_facilities(raw_gdf):

    if raw_gdf is None or raw_gdf.empty:
        raise RuntimeError(
            "No medical facilities were found in the PBF file."
        )

    logger.info("Raw extracted objects: %s", len(raw_gdf))

    records = []
    geometries = []

    for _, row in raw_gdf.iterrows():

        tags = parse_tags(row)

        original_geometry = row.get("geometry")

        if original_geometry is None:
            original_wkt = None
            geometry_type = None
        else:
            original_wkt = original_geometry.wkt
            geometry_type = original_geometry.geom_type

        geometry, original_valid, repaired = repair_geometry(
            original_geometry
        )

        latitude, longitude, coordinate_source = get_coordinates(
            geometry
        )

        coordinate_valid, inside_bbox, coordinate_note = (
            validate_coordinates(latitude, longitude)
        )

        # OSM metadata.
        version = row.get("version")
        timestamp = get_osm_timestamp(row.get("timestamp"))

        try:
            version = int(version) if not is_missing(version) else None
        except (TypeError, ValueError):
            version = None

        # The creation time is only known from a current version 1.
        created_at = (
            timestamp
            if version == 1
            else pd.NaT
        )

        osm_id = row.get("id", row.get("osm_id"))
        osm_type = row.get("osm_type")

        try:
            osm_id = int(osm_id)
        except (TypeError, ValueError):
            osm_id = None

        # Basic validation notes.
        notes = []

        if not coordinate_valid:
            notes.append("Invalid or missing coordinates")

        if inside_bbox is False:
            notes.append("Outside approximate Egypt bounding box")

        if not original_valid and repaired:
            notes.append("Geometry repaired")

        if not original_valid and not repaired:
            notes.append("Invalid geometry could not be repaired")

        if not tags.get("name"):
            notes.append("Missing facility name")

        # Standardized record.
        record = {
            "osm_id": osm_id,
            "osm_type": osm_type,

            "osm_version": version,
            "osm_changeset": row.get("changeset"),

            "osm_created_at": created_at,
            "osm_last_edited_at": timestamp,

            "facility_type": classify_facility(tags),
            "facility_type_source": (
                "healthcare" if tags.get("healthcare")
                else "amenity" if tags.get("amenity")
                else "shop" if tags.get("shop")
                else "office" if tags.get("office")
                else "other"
            ),

            "latitude": latitude,
            "longitude": longitude,

            "geometry_type": geometry_type,
            "geometry_original_wkt": original_wkt,

            "coordinate_source": coordinate_source,
            "coordinate_valid": coordinate_valid,
            "inside_egypt_bbox": inside_bbox,

            "geometry_valid_original": original_valid,
            "geometry_repaired": repaired,

            "validation_notes": "; ".join(notes),

            "all_tags": json.dumps(
                tags,
                ensure_ascii=False,
                sort_keys=True,
            ),

            "extraction_date": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        # Add convenient standardized tag columns.
        for osm_tag, output_column in TAG_COLUMN_MAP.items():
            record[output_column] = tags.get(osm_tag)

        records.append(record)
        geometries.append(geometry)

    result = gpd.GeoDataFrame(
        records,
        geometry=geometries,
        crs="EPSG:4326",
    )

    # Remove only exact duplicate OSM objects.
    # Different OSM objects are retained even if they overlap.
    before = len(result)

    result = result.drop_duplicates(
        subset=["osm_type", "osm_id"],
        keep="last",
    ).reset_index(drop=True)

    logger.info(
        "Removed %s duplicate OSM object IDs.",
        before - len(result),
    )

    return result


# ============================================================
# EXPORT
# ============================================================

def export_results(gdf, output_dir):

    output_dir.mkdir(parents=True, exist_ok=True)

    parquet_path = output_dir / "egypt_medical_facilities.parquet"
    csv_path = output_dir / "egypt_medical_facilities.csv"
    issues_path = output_dir / "facilities_validation_issues.csv"
    report_path = output_dir / "extraction_report.json"

    # 1. GeoParquet: retains real geometry.
    logger.info("Writing GeoParquet...")

    gdf.to_parquet(
        parquet_path,
        index=False,
    )

    # 2. CSV: convert geometry into WKT text.
    logger.info("Writing CSV...")

    csv_df = pd.DataFrame(gdf.drop(columns="geometry"))

    csv_df["geometry_wkt"] = gdf.geometry.to_wkt()

    csv_df.to_csv(
        csv_path,
        index=False,
        encoding="utf-8-sig",
    )

    # 3. Validation issues.
    issues = gdf[
        (~gdf["coordinate_valid"])
        | (gdf["inside_egypt_bbox"] == False)
        | (~gdf["geometry_valid_original"])
    ].copy()

    issues_df = pd.DataFrame(issues.drop(columns="geometry"))
    issues_df["geometry_wkt"] = issues.geometry.to_wkt()

    issues_df.to_csv(
        issues_path,
        index=False,
        encoding="utf-8-sig",
    )

    # 4. Extraction summary.
    tag_counter = Counter()

    for raw_tags in gdf["all_tags"].dropna():
        try:
            tags = json.loads(raw_tags)
            tag_counter.update(tags.keys())
        except (TypeError, json.JSONDecodeError):
            continue

    report = {
        "extraction_date": datetime.now(
            timezone.utc
        ).isoformat(),

        "total_facilities": len(gdf),

        "facility_type_counts": {
            str(k): int(v)
            for k, v in gdf["facility_type"].value_counts().items()
        },

        "osm_type_counts": {
            str(k): int(v)
            for k, v in gdf["osm_type"].value_counts().items()
        },

        "valid_coordinates": int(gdf["coordinate_valid"].sum()),

        "outside_egypt_bbox": int(
            (gdf["inside_egypt_bbox"] == False).sum()
        ),

        "repaired_geometries": int(
            gdf["geometry_repaired"].sum()
        ),

        "missing_names": int(
            gdf["name"].isna().sum()
        ),

        "most_common_osm_tags": tag_counter.most_common(50),

        "output_files": [
            parquet_path.name,
            csv_path.name,
            issues_path.name,
        ],
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(
            report,
            f,
            ensure_ascii=False,
            indent=4,
            default=str,
        )

    logger.info("Extraction completed.")
    logger.info("Total facilities: %s", len(gdf))
    logger.info("CSV: %s", csv_path)
    logger.info("GeoParquet: %s", parquet_path)
    logger.info("Issues: %s", issues_path)
    logger.info("Report: %s", report_path)


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="Extract all mapped medical facilities from an Egypt OSM PBF."
    )

    parser.add_argument(
        "--pbf",
        required=True,
        help="Path to the Egypt .osm.pbf file",
    )

    parser.add_argument(
        "--output",
        default="data/medical_facilities",
        help="Output directory",
    )

    args = parser.parse_args()

    pbf_path = Path(args.pbf)
    output_dir = Path(args.output)

    if not pbf_path.exists():
        raise FileNotFoundError(
            f"PBF file not found: {pbf_path}"
        )

    logger.info("Reading PBF: %s", pbf_path)
    logger.info("This may take some time for the full Egypt extract.")

    osm = OSM(
        str(pbf_path),
        keep_metadata=True,
        complete_relations=True,
        engine="out_of_core",
    )

    logger.info("Extracting healthcare-related objects...")

    raw_gdf = osm.get_data_by_custom_criteria(
        custom_filter=OSM_FILTER,
        keep_nodes=True,
        keep_ways=True,
        keep_relations=True,
        tags_as_columns=[],
        keep_other_tags=True,
    )

    logger.info("Processing extracted objects...")

    facilities = process_facilities(raw_gdf)

    logger.info("Exporting results...")

    export_results(
        facilities,
        output_dir,
    )


if __name__ == "__main__":
    main()
