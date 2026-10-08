import sys
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent / "server"
sys.path.insert(0, str(SERVER_DIR))

from services.gis_parser import parse_csv_content, validate_dataset
from services.template_loader import resolve_template_path


def test_parse_csv_content_infers_columns():
    content = b"building_id,num_floors,building_type\nb1,2,SFH\nb2,3,MFH\n"
    parsed = parse_csv_content(content)

    assert parsed["row_count"] == 2
    assert len(parsed["columns"]) == 3
    assert parsed["columns"][0]["name"] == "building_id"


def test_validate_dataset_flags_missing_required_columns():
    dataset = {
        "row_count": 1,
        "columns": [{"name": "building_id", "null_count": 0}],
    }
    result = validate_dataset(
        dataset,
        column_mappings={"building_id": "building_id", "num_floors": "missing_col"},
        validate_columns=["building_id"],
    )

    assert result["valid"] is False
    assert "missing_col" in result["missing_columns"]


def test_validate_dataset_ignores_unselected_null_columns():
    dataset = {
        "row_count": 2,
        "columns": [
            {"name": "building_id", "null_count": 0},
            {"name": "CT2020", "null_count": 2},
        ],
    }
    result = validate_dataset(
        dataset,
        column_mappings={"building_id": "building_id", "num_floors": "building_id"},
        validate_columns=["building_id"],
    )

    assert result["valid"] is True


def test_suggest_column_mappings_matches_assessor_area():
    from services.globi_columns import suggest_column_mappings

    suggestions = suggest_column_mappings(["OID", "sqft_assessor", "Story", "CT2020"])

    assert suggestions.get("building_id") == "OID"
    assert suggestions.get("footprint_area") == "sqft_assessor"
    assert suggestions.get("num_floors") == "Story"
    assert "CT2020" not in suggestions.values()


def test_drop_incomplete_rows_removes_rows_with_missing_values():
    from services.gis_parser import drop_incomplete_rows

    dataset = {
        "row_count": 3,
        "rows": [
            {"building_id": "b1", "sqft_assessor": "1000"},
            {"building_id": "", "sqft_assessor": "900"},
            {"building_id": "b3", "sqft_assessor": ""},
        ],
        "columns": [],
        "column_mappings": {"building_id": "building_id", "footprint_area": "sqft_assessor"},
        "validated_columns": ["building_id", "sqft_assessor"],
        "source_format": "csv",
    }
    cleaned = drop_incomplete_rows(dataset, ["building_id", "sqft_assessor"])

    assert cleaned["row_count"] == 1
    assert cleaned["rows"][0]["building_id"] == "b1"
    assert cleaned["dropped_row_count"] == 2


def test_build_cleaned_geojson_keeps_geometry_and_filtered_properties():
    from services.gis_parser import build_cleaned_geojson, drop_incomplete_rows

    dataset = {
        "row_count": 1,
        "rows": [{"building_id": "b1", "CT2020": "x", "sqft_assessor": "1000"}],
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [1, 2]},
                "properties": {"building_id": "b1", "CT2020": "x", "sqft_assessor": "1000"},
            }
        ],
        "column_mappings": {"building_id": "building_id", "footprint_area": "sqft_assessor"},
        "validated_columns": ["building_id", "sqft_assessor"],
        "source_format": "geojson",
    }
    cleaned = drop_incomplete_rows(dataset, ["building_id", "sqft_assessor"])
    geojson = build_cleaned_geojson(cleaned)

    assert len(geojson["features"]) == 1
    assert geojson["features"][0]["geometry"]["coordinates"] == [1, 2]
    assert set(geojson["features"][0]["properties"].keys()) == {"building_id", "sqft_assessor"}


def test_resolve_template_path_blocks_traversal():
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        resolve_template_path("semantic_fields", "../component_maps/residential.yml")
