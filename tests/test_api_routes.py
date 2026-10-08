import sys
from io import BytesIO
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent / "server"
sys.path.insert(0, str(SERVER_DIR))

from fastapi.testclient import TestClient
from main import app
from semantic_priors import RegionConfig

from conftest import open_temp_workspace

client = TestClient(app)


def setup_function():
    open_temp_workspace()


def test_component_tree_endpoint_returns_real_epinterface_paths():
    response = client.get("/api/component-tree/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["roots"] == ["Envelope", "Operations"]
    paths = {node["path"] for node in payload["nodes"]}
    assert "Operations.SpaceUse.Lighting" in paths


def test_workspace_lifecycle():
    import tempfile
    from pathlib import Path as _Path

    root = _Path(tempfile.mkdtemp()) / "http-workspace"

    status_before = client.get("/api/workspace/status").json()
    assert status_before["open"] is True  # setup_function already opened a temp workspace

    created = client.post(
        "/api/workspace/create", json={"path": str(root), "name": "HTTP Project"}
    )
    assert created.status_code == 200
    assert created.json()["name"] == "HTTP Project"

    status = client.get("/api/workspace/status").json()
    assert status["open"] is True
    assert status["workspace"]["name"] == "HTTP Project"

    closed = client.post("/api/workspace/close")
    assert closed.status_code == 200
    assert client.get("/api/workspace/status").json()["open"] is False

    # GIS routes require an open workspace once none is open.
    upload = client.post(
        "/api/gis/upload",
        files={"file": ("buildings.csv", BytesIO(b"building_id\nb1\n"), "text/csv")},
    )
    assert upload.status_code == 409

    reopened = client.post("/api/workspace/open", json={"path": str(root)})
    assert reopened.status_code == 200
    assert reopened.json()["name"] == "HTTP Project"


def test_workspace_create_rejects_an_existing_project():
    import tempfile
    from pathlib import Path as _Path

    root = _Path(tempfile.mkdtemp()) / "occupied"
    root.mkdir(parents=True)
    (root / "project.json").write_text("{}")

    response = client.post("/api/workspace/create", json={"path": str(root), "name": "Nope"})
    assert response.status_code == 400


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_semantic_field_templates_list():
    response = client.get("/api/semantic-fields/templates")
    assert response.status_code == 200
    assert len(response.json()["templates"]) >= 1


def test_gis_upload_csv():
    csv_content = b"building_id,num_floors,building_type\nb1,2,SFH\n"
    response = client.post(
        "/api/gis/upload",
        files={"file": ("buildings.csv", BytesIO(csv_content), "text/csv")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rowCount"] == 1
    assert payload["validated"] is False


def test_gis_clean_drop_and_export_geojson():
    geojson_content = b"""{
      "type": "FeatureCollection",
      "features": [
        {
          "type": "Feature",
          "geometry": {"type": "Point", "coordinates": [-76.6, 39.2]},
          "properties": {"OID": "1", "sqft_assessor": "1200", "Story": "2", "CT2020": null}
        },
        {
          "type": "Feature",
          "geometry": {"type": "Point", "coordinates": [-76.7, 39.3]},
          "properties": {"OID": "2", "sqft_assessor": "", "Story": "3", "CT2020": "123"}
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
                "footprint_area": "sqft_assessor",
            },
            "validate_columns": ["OID", "Story", "sqft_assessor"],
            "drop_incomplete_rows": True,
        },
    )
    assert clean.status_code == 200
    payload = clean.json()
    assert payload["validation"]["valid"] is True
    assert payload["dataset"]["rowCount"] == 1
    assert payload["validation"]["dropped_row_count"] == 1

    export = client.get("/api/gis/export")
    assert export.status_code == 200
    assert "application/geo+json" in export.headers["content-type"]
    assert "OID" in export.text
    assert "CT2020" not in export.text


def test_gis_upload_rejects_unsupported_type():
    response = client.post(
        "/api/gis/upload",
        files={"file": ("buildings.txt", BytesIO(b"abc"), "text/plain")},
    )

    assert response.status_code == 400


def test_component_map_template_load_and_validate():
    templates = client.get("/api/component-map/templates").json()["templates"]
    assert templates

    template_name = templates[0]["filename"]
    template = client.get(f"/api/component-map/templates/{template_name}").json()
    response = client.post(
        "/api/component-map/validate",
        json={
            "component_map": template,
            "semantic_fields": [{"name": "Region", "options": ["MD"]}],
        },
    )

    assert response.status_code == 200
    assert "errors" in response.json()


def test_prior_tree_template_load():
    templates = client.get("/api/prior-trees/templates").json()["templates"]
    assert templates

    template_name = templates[0]["filename"]
    response = client.get(f"/api/prior-trees/templates/{template_name}")
    assert response.status_code == 200
    # Prior templates are semantic_priors RegionConfigs, so the sampling engine
    # loads a bundled template as-is.
    template = response.json()
    assert RegionConfig.from_dict(template).to_priors().sampled_features
