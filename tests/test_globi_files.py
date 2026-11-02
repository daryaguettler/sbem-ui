"""Template projects, the sample GIS, and generating globi's run files from a project."""

import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent / "server"
sys.path.insert(0, str(SERVER_DIR))

import yaml
from fastapi.testclient import TestClient
from main import app

from services.template_loader import TEMPLATES_DIR
from services.workspace import ProjectWorkspace

client = TestClient(app)

TEMPLATE_DIR = TEMPLATES_DIR / "projects" / "globi-tutorial"
WEATHER = "weather/USA_MA_Boston-Logan.Intl.AP.725090_TMYx.2009-2023.zip"
E2E_MAP = {
    "Envelope": {"selector": {"source_fields": ["Region", "Typology", "Scenario", "Age_bracket"]}},
    "Operations": {
        "SpaceUse": {"selector": {"source_fields": ["Region", "Typology", "Income", "Scenario"]}},
        "HVAC": {"selector": {"source_fields": ["Region", "Typology", "Scenario", "Age_bracket"]}},
        "DHW": {"selector": {"source_fields": ["Region", "Typology"]}},
    },
}
FIELDS = {
    "Region": ["TestRegion"],
    "Typology": ["Office", "School", "Residential", "Hospital", "Hotel"],
    "Age_bracket": ["Pre_1980", "1980_to_2000", "Post_2000"],
    "Income": ["Low", "High"],
    "Scenario": ["Baseline", "Retrofit"],
}
CONTEXT = {"Region": "TestRegion", "Typology": "Office", "Age_bracket": "Post_2000", "Income": "Low", "Scenario": "Baseline"}


def template_project() -> ProjectWorkspace:
    root = Path(tempfile.mkdtemp()) / "workspace"
    # init_db=True: a template's db must make the (raising) empty-db init a no-op
    workspace = ProjectWorkspace.create(root, "Demo", init_db=True, template_dir=TEMPLATE_DIR)
    app.state.workspace = workspace
    return workspace


def saved_project(fields=FIELDS) -> ProjectWorkspace:
    workspace = template_project()
    workspace.write_semantic_fields(
        {"Name": "Demo", "Fields": [{"Name": name, "Options": options} for name, options in fields.items()]}
    )
    assert client.post("/api/artifacts/component-map", json={"payload": E2E_MAP}).status_code == 200
    return workspace


def generate(**overrides):
    body = {"name": "Demo run", "epwzip_file": WEATHER, "context": CONTEXT, **overrides}
    return client.post("/api/globi-files/generate", json=body)


def test_template_is_listed_and_copied_into_a_new_project():
    templates = client.get("/api/workspace/templates").json()["templates"]
    assert [t["filename"] for t in templates] == ["globi-tutorial.yml"]

    workspace = template_project()
    assert workspace.path("components_db").stat().st_size == (TEMPLATE_DIR / "components-lib.db").stat().st_size
    assert (workspace.root / WEATHER).exists()


def test_sample_gis_loads_like_an_upload():
    template_project()
    data = client.post("/api/gis/sample").json()
    assert data["rowCount"] == 100
    assert data["columnMappings"]["num_floors"] == "num_storeys"


def test_saved_semantic_fields_carry_every_column_role_from_gis_cleaning():
    workspace = template_project()
    client.post("/api/gis/sample")
    mappings = {"building_id": "building_id", "num_floors": "num_storeys", "height": "height", "wwr": "WWR"}
    client.post("/api/gis/clean", json={"column_mappings": mappings, "validate_columns": []})

    client.post("/api/artifacts/semantic-fields", json={"payload": {"name": "Demo", "fields": []}})
    saved = yaml.safe_load(workspace.path("semantic_fields").read_text())
    assert saved["Height_col"] == "height"
    assert saved["WWR_col"] == "WWR"
    assert saved["Num_Floors_col"] == "num_storeys"


def test_generates_building_file_only_until_a_gis_is_saved():
    workspace = saved_project()
    result = generate()
    assert result.status_code == 200, result.text
    assert result.json()["written"] == ["building.yml"]
    assert "No GIS saved" in result.json()["warnings"][0]

    building = yaml.safe_load(workspace.path("building").read_text())
    assert building["semantic_field_context"] == CONTEXT
    assert building["component_map_file"] == str(workspace.path("component_map").resolve())


def test_generates_batch_files_from_a_saved_gis():
    workspace = saved_project()
    shutil.copy(TEMPLATES_DIR / "gis" / "buildings-100.geojson", workspace.path("gis_dir") / "buildings.geojson")

    result = generate().json()
    assert result["written"] == ["building.yml", "artifacts.yml", "gis-preprocessor.yml", "manifest.yml"]
    assert result["warnings"] == []
    manifest = yaml.safe_load(workspace.path("manifest").read_text())
    assert manifest["file_config"] == str(workspace.path("artifacts").resolve())
    assert "--max-sims 5" in result["commands"]["batch"]


def test_batch_warns_about_fields_the_gis_has_no_column_for():
    workspace = saved_project({**FIELDS, "Heating": ["Gas", "HeatPump"]})
    shutil.copy(TEMPLATES_DIR / "gis" / "buildings-100.geojson", workspace.path("gis_dir") / "buildings.geojson")
    result = generate(context={**CONTEXT, "Heating": "Gas"}).json()
    assert "Heating" in result["warnings"][0]


def test_rejects_a_building_value_outside_the_field_options():
    saved_project()
    result = generate(context={**CONTEXT, "Typology": "Warehouse"})
    assert result.status_code == 400
    assert "Typology" in result.json()["detail"]
