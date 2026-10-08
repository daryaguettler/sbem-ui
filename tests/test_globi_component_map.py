import json
import shutil
import tempfile
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from conftest import open_temp_workspace
from main import app
from services.globi_component_map import structural_errors, to_globi
from services.workspace import ProjectWorkspace

client = TestClient(app)

TRONDHEIM = Path.home() / "globi-partners-data/data/partners/Trondheim"

EDITOR_TREE = {
    "Envelope": {
        "selector": {"source_fields": ["Region", "Typology"], "suffix": None},
        "Window": {},
        "Assemblies": {"RoofAssembly": {}},
    },
    "Operations": {
        "SpaceUse": {"selector": {"source_fields": ["Region"]}},
        "HVAC": {},
    },
}


def test_to_globi_prunes_empty_nodes_and_null_keys():
    assert to_globi(EDITOR_TREE) == {
        "Envelope": {"selector": {"source_fields": ["Region", "Typology"]}},
        "Operations": {"SpaceUse": {"selector": {"source_fields": ["Region"]}}},
    }


def test_structural_errors_flag_unknown_nodes():
    assert structural_errors(to_globi(EDITOR_TREE)) == []
    errors = structural_errors({"Envelope": {"Bogus": {"selector": {"source_fields": ["Region"]}}}})
    assert errors and "Bogus" in errors[0]


def test_saving_the_editor_tree_writes_globi_component_map():
    workspace = open_temp_workspace()
    response = client.post("/api/artifacts/component-map", json={"payload": EDITOR_TREE})
    assert response.status_code == 200
    generated = yaml.safe_load((workspace.root / "component-map.yaml").read_text())
    assert generated == to_globi(EDITOR_TREE)
    # the editor's own file keeps the full tree
    selectors = yaml.safe_load((workspace.root / "component-map.selectors.yaml").read_text())
    assert "Window" in selectors["Envelope"]


def _repo_project(files: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp()) / "inputs"
    (root / "globi").mkdir(parents=True)
    (root / "project.json").write_text(
        json.dumps({"name": "Repo", "schema_version": 1, "files": files})
    )
    return root


def test_an_existing_globi_map_opens_in_the_editor():
    root = _repo_project({"component_map": "globi/component-map.yaml"})
    (root / "globi" / "component-map.yaml").write_text(
        yaml.safe_dump({"Envelope": {"selector": {"source_fields": ["Region"]}}})
    )
    app.state.workspace = ProjectWorkspace.open(root)
    artifact = client.get("/api/artifacts/component-map").json()
    assert artifact["exists"] is True
    assert artifact["content"]["Envelope"]["selector"]["source_fields"] == ["Region"]


def test_check_requires_a_saved_map():
    open_temp_workspace()
    assert client.post("/api/component-map/check").status_code == 400


@pytest.mark.skipif(not TRONDHEIM.exists(), reason="optional: needs a real component library (Trondheim bundle) locally")
def test_check_against_trondheim_library():
    root = _repo_project({
        "semantic_fields": "globi/semantic-fields.yaml",
        "component_map_selectors": "globi/component-map.yaml",
        "component_map": "globi/component-map.yaml",
        "components_db": "globi/components-lib.db",
    })
    for name in ("semantic-fields.yaml", "component-map.yaml", "components-lib.db"):
        shutil.copy(TRONDHEIM / name, root / "globi" / name)
    app.state.workspace = ProjectWorkspace.open(root)

    result = client.post("/api/component-map/check?n_tests=50").json()
    assert result == {"ok": True, "tested": 50, "failed": 0, "errors": []}

    # a selector that builds names the db lacks is reported, not raised
    broken = yaml.safe_load((root / "globi" / "component-map.yaml").read_text())
    broken["Operations"]["DHW"]["selector"]["source_fields"] = ["Typology"]
    client.post("/api/artifacts/component-map", json={"payload": broken})
    result = client.post("/api/component-map/check?n_tests=20").json()
    assert result["ok"] is False and result["failed"] == 20 and result["errors"]
