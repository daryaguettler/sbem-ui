import sys
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent / "server"
sys.path.insert(0, str(SERVER_DIR))

import yaml
from fastapi.testclient import TestClient
from main import app

from conftest import open_temp_workspace

client = TestClient(app)


SEMANTIC_FIELDS_PAYLOAD = {
    "name": "My Fields",
    "building_id_col": "building_id",
    "num_floors_col": "num_floors",
    "fields": [
        {
            "id": "field-0",
            "name": "Age_bracket",
            "type": "deterministic",
            "data_type": "categorical",
            "options": ["pre_1975", "post_1975"],
            "description": "Construction age",
            "requires_prior": False,
            "transformation_rule": {
                "id": "transform-0",
                "type": "numeric_range",
                "source_column": "construction_year",
                "target_field": "Age_bracket",
                "numeric_ranges": [
                    {"min": 0, "max": 1974, "label": "pre_1975"},
                    {"min": 1975, "max": 9999, "label": "post_1975"},
                ],
            },
        }
    ],
}

COMPONENT_MAP_PAYLOAD = {"Envelope": {"Window": {"selector": {"source_fields": ["Region"]}}}}


def setup_function():
    open_temp_workspace()


def test_saving_semantic_fields_writes_the_document_the_export_endpoint_serves():
    workspace = open_temp_workspace()

    saved = client.post("/api/artifacts/semantic-fields", json={"payload": SEMANTIC_FIELDS_PAYLOAD})
    assert saved.status_code == 200
    assert saved.json()["path"] == "semantic-fields.yaml"

    # Same document, from the same converter. (Not byte-identical: /export coerces the
    # payload through Pydantic first, which renders range bounds as 0.0 rather than 0.
    # Saving stays lenient on purpose -- half-finished work is worth saving, and
    # validation is its own button.)
    exported = client.post("/api/semantic-fields/export", json=SEMANTIC_FIELDS_PAYLOAD)
    saved_document = yaml.safe_load((workspace.root / "semantic-fields.yaml").read_text())
    assert saved_document == yaml.safe_load(exported.text)


def test_saved_semantic_fields_read_back_in_template_shape():
    client.post("/api/artifacts/semantic-fields", json={"payload": SEMANTIC_FIELDS_PAYLOAD})

    payload = client.get("/api/artifacts/semantic-fields").json()
    assert payload["exists"] is True
    assert payload["savedAt"] is not None
    # The template shape is what the frontend's loadFromTemplate() already consumes.
    assert payload["content"]["Name"] == "My Fields"
    assert payload["content"]["Fields"][0]["Name"] == "Age_bracket"
    assert payload["content"]["Fields"][0]["Transformation"] == "numeric_range"


def test_component_map_and_priors_round_trip_unchanged():
    client.post("/api/artifacts/component-map", json={"payload": COMPONENT_MAP_PAYLOAD})
    client.post("/api/artifacts/priors", json={"payload": {"Priors": {"Heating": {}}}})

    assert client.get("/api/artifacts/component-map").json()["content"] == COMPONENT_MAP_PAYLOAD
    assert client.get("/api/artifacts/priors").json()["content"] == {"Priors": {"Heating": {}}}


def test_priors_save_creates_the_priors_subdirectory():
    workspace = open_temp_workspace()
    (workspace.root / "priors").rmdir()

    response = client.post("/api/artifacts/priors", json={"payload": {"Priors": {}}})
    assert response.status_code == 200
    assert (workspace.root / "priors" / "priors.yaml").exists()


def test_unsaved_artifact_reports_absent_rather_than_erroring():
    payload = client.get("/api/artifacts/priors").json()
    assert payload["exists"] is False
    assert payload["content"] is None
    assert payload["savedAt"] is None


def test_unknown_artifact_kind_is_a_404():
    assert client.get("/api/artifacts/not-a-kind").status_code == 404
    assert client.post("/api/artifacts/not-a-kind", json={"payload": {}}).status_code == 404


def test_artifact_status_listing_tracks_what_has_been_saved():
    client.post("/api/artifacts/priors", json={"payload": {"Priors": {}}})

    artifacts = {entry["kind"]: entry for entry in client.get("/api/artifacts/").json()["artifacts"]}
    assert set(artifacts) == {"semantic-fields", "component-map", "priors", "retrofits"}
    assert artifacts["priors"]["exists"] is True
    # Scaffolded at project creation, so it exists from the start.
    assert artifacts["semantic-fields"]["exists"] is True


def test_file_listing_covers_the_whole_project_directory():
    workspace = open_temp_workspace()
    client.post("/api/artifacts/component-map", json={"payload": COMPONENT_MAP_PAYLOAD})

    listing = client.get("/api/artifacts/files").json()
    assert listing["root"] == str(workspace.root)

    by_path = {entry["path"]: entry for entry in listing["files"]}
    assert "project.json" in by_path
    assert by_path["component-map.selectors.yaml"]["kind"] == "component-map"
    assert by_path["project.json"]["kind"] is None
    assert by_path["component-map.selectors.yaml"]["size"] > 0
    assert by_path["component-map.selectors.yaml"]["viewable"] is True


def test_file_content_returns_the_raw_text():
    client.post("/api/artifacts/component-map", json={"payload": COMPONENT_MAP_PAYLOAD})

    payload = client.get(
        "/api/artifacts/files/content", params={"path": "component-map.selectors.yaml"}
    ).json()
    assert payload["truncated"] is False
    assert yaml.safe_load(payload["content"]) == COMPONENT_MAP_PAYLOAD


def test_file_content_truncates_oversized_files():
    from services.artifacts import MAX_VIEW_BYTES

    workspace = open_temp_workspace()
    (workspace.root / "gis").mkdir(exist_ok=True)
    (workspace.root / "gis" / "dataset.json").write_text("x" * (MAX_VIEW_BYTES + 100))

    payload = client.get("/api/artifacts/files/content", params={"path": "gis/dataset.json"}).json()
    assert payload["truncated"] is True
    assert len(payload["content"]) == MAX_VIEW_BYTES


def test_binary_files_are_listed_but_not_rendered():
    workspace = open_temp_workspace()
    (workspace.root / "components-lib.db").write_bytes(b"\x00\x01binary")

    payload = client.get("/api/artifacts/files/content", params={"path": "components-lib.db"}).json()
    assert payload["viewable"] is False
    assert payload["content"] is None


def test_file_content_refuses_paths_outside_the_project():
    for path in ("../../etc/passwd", "/etc/passwd"):
        response = client.get("/api/artifacts/files/content", params={"path": path})
        assert response.status_code == 400, path


def test_artifact_routes_require_an_open_workspace():
    app.state.workspace = None
    try:
        assert client.get("/api/artifacts/").status_code == 409
        assert client.get("/api/artifacts/files").status_code == 409
        assert client.post("/api/artifacts/priors", json={"payload": {}}).status_code == 409
    finally:
        open_temp_workspace()
