import json
import sys
from io import BytesIO
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent / "server"
sys.path.insert(0, str(SERVER_DIR))

from fastapi.testclient import TestClient
from main import app
from services.semantic_transform import apply_field_to_row, preview_semantic_fields

from conftest import open_temp_workspace

client = TestClient(app)


def setup_function():
    open_temp_workspace()


def test_apply_numeric_range_from_yearblt():
    field = {
        "name": "Age_bracket",
        "type": "deterministic",
        "options": ["pre_1975", "post_1975"],
        "transformation_rule": {
            "type": "numeric_range",
            "source_column": "YEARBLT",
            "numeric_ranges": [
                {"min": 0, "max": 1974, "label": "pre_1975"},
                {"min": 1975, "max": 9999, "label": "post_1975"},
            ],
        },
    }

    assert apply_field_to_row({"YEARBLT": "1960"}, field) == "pre_1975"
    assert apply_field_to_row({"YEARBLT": "1988"}, field) == "post_1975"


def test_preview_reports_unmapped_rows():
    rows = [{"YEARBLT": "1960"}, {"YEARBLT": ""}]
    field = {
        "name": "Age_bracket",
        "type": "deterministic",
        "options": ["pre_1975", "post_1975"],
        "transformation_rule": {
            "type": "numeric_range",
            "source_column": "YEARBLT",
            "numeric_ranges": [
                {"min": 0, "max": 1974, "label": "pre_1975"},
                {"min": 1975, "max": 9999, "label": "post_1975"},
            ],
        },
    }

    preview = preview_semantic_fields(rows, [field], sample_limit=2)
    stats = preview["field_previews"][0]["stats"]

    assert stats["mapped_count"] == 1
    assert stats["unmapped_count"] == 1


def test_semantic_preview_and_enriched_export_endpoints():
    geojson_content = b"""{
      "type": "FeatureCollection",
      "features": [
        {
          "type": "Feature",
          "geometry": {"type": "Point", "coordinates": [-76.6, 39.2]},
          "properties": {"OID": "1", "YEARBLT": "1960", "Story": "2"}
        },
        {
          "type": "Feature",
          "geometry": {"type": "Point", "coordinates": [-76.7, 39.3]},
          "properties": {"OID": "2", "YEARBLT": "1988", "Story": "3"}
        }
      ]
    }"""

    upload = client.post(
        "/api/gis/upload",
        files={"file": ("buildings.geojson", BytesIO(geojson_content), "application/geo+json")},
    )
    assert upload.status_code == 200

    clean = client.post(
        "/api/gis/clean",
        json={
            "column_mappings": {
                "building_id": "OID",
                "num_floors": "Story",
            },
            "validate_columns": ["OID", "Story", "YEARBLT"],
            "drop_incomplete_rows": False,
        },
    )
    assert clean.status_code == 200
    assert clean.json()["validation"]["valid"] is True

    payload = {
        "name": "Test Semantic Fields",
        "building_id_col": "OID",
        "num_floors_col": "Story",
        "fields": [
            {
                "id": "field-1",
                "name": "Age_bracket",
                "type": "deterministic",
                "data_type": "numeric",
                "options": ["pre_1975", "post_1975"],
                "transformation_rule": {
                    "id": "rule-1",
                    "type": "numeric_range",
                    "source_column": "YEARBLT",
                    "target_field": "Age_bracket",
                    "numeric_ranges": [
                        {"min": 0, "max": 1974, "label": "pre_1975"},
                        {"min": 1975, "max": 9999, "label": "post_1975"},
                    ],
                },
            }
        ],
    }

    preview = client.post("/api/semantic-fields/preview", json=payload)
    assert preview.status_code == 200
    assert preview.json()["field_previews"][0]["stats"]["mapped_count"] == 2

    export = client.post("/api/gis/export-enriched", json=payload)
    assert export.status_code == 200
    assert "Age_bracket" in export.text
    assert "pre_1975" in export.text

    saved = client.post("/api/gis/export-enriched?save=true", json=payload)
    assert saved.status_code == 200
    assert saved.json()["path"] == "gis/buildings.geojson"
    written = json.loads((app.state.workspace.root / "gis" / "buildings.geojson").read_text())
    assert written["features"][0]["properties"]["Age_bracket"] == "pre_1975"
