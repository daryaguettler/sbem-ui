import tempfile
from pathlib import Path

import pytest

from services.workspace import ProjectWorkspace, WorkspaceError


def _tmp_root() -> Path:
    return Path(tempfile.mkdtemp()) / "workspace"


def test_create_scaffolds_expected_layout():
    workspace = ProjectWorkspace.create(_tmp_root(), "My Project", init_db=False)

    assert (workspace.root / "project.json").exists()
    assert (workspace.root / "semantic-fields.yaml").exists()
    assert (workspace.root / "component-map.selectors.yaml").exists()
    assert (workspace.root / "gis").is_dir()
    assert (workspace.root / "priors").is_dir()
    assert workspace.status()["name"] == "My Project"


def test_create_adopts_a_non_empty_directory_without_touching_its_files():
    root = _tmp_root()
    root.mkdir(parents=True)
    (root / "existing.txt").write_text("hello")
    (root / "semantic-fields.yaml").write_text("Name: kept\nFields: []\n")

    workspace = ProjectWorkspace.create(root, "My Project", init_db=False)
    assert (root / "existing.txt").read_text() == "hello"
    assert workspace.read_semantic_fields()["Name"] == "kept"


def test_create_refuses_an_existing_project():
    root = _tmp_root()
    ProjectWorkspace.create(root, "My Project", init_db=False)
    with pytest.raises(WorkspaceError):
        ProjectWorkspace.create(root, "Again", init_db=False)


def test_project_json_files_map_relocates_artifacts():
    import json

    root = _tmp_root()
    root.mkdir(parents=True)
    (root / "project.json").write_text(
        json.dumps({
            "name": "Repo",
            "schema_version": 1,
            "runner": "..",
            "files": {"semantic_fields": "globi/semantic-fields.yaml", "priors": "priors.yaml"},
        })
    )
    workspace = ProjectWorkspace.open(root)
    workspace.write_semantic_fields({"Name": "x", "Fields": []})
    workspace.write_priors({"registry": {"fields": []}})
    assert (root / "globi" / "semantic-fields.yaml").exists()
    assert (root / "priors.yaml").exists()
    assert workspace.relative("component_map_selectors") == "component-map.selectors.yaml"
    assert workspace.runner == root.parent.resolve()


def test_open_round_trips_a_created_workspace():
    root = _tmp_root()
    ProjectWorkspace.create(root, "My Project", init_db=False)

    reopened = ProjectWorkspace.open(root)
    assert reopened.status()["name"] == "My Project"


def test_open_rejects_missing_project_file():
    root = _tmp_root()
    root.mkdir(parents=True)

    with pytest.raises(WorkspaceError):
        ProjectWorkspace.open(root)


def test_open_rejects_incompatible_schema_version():
    root = _tmp_root()
    ProjectWorkspace.create(root, "My Project", init_db=False)
    project_file = root / "project.json"
    project_file.write_text(project_file.read_text().replace('"schema_version": 1', '"schema_version": 999'))

    with pytest.raises(WorkspaceError):
        ProjectWorkspace.open(root)


def test_semantic_fields_round_trip():
    workspace = ProjectWorkspace.create(_tmp_root(), "My Project", init_db=False)
    config = {"name": "My Project", "fields": [{"id": "f1", "name": "Age_bracket"}]}

    workspace.write_semantic_fields(config)

    assert workspace.read_semantic_fields() == config


def test_component_map_selectors_round_trip():
    workspace = ProjectWorkspace.create(_tmp_root(), "My Project", init_db=False)
    selectors = {"Operations.SpaceUse.Lighting": {"source_fields": ["Age_bracket"]}}

    workspace.write_component_map_selectors(selectors)

    assert workspace.read_component_map_selectors() == selectors


def test_generated_component_map_defaults_to_none():
    workspace = ProjectWorkspace.create(_tmp_root(), "My Project", init_db=False)

    assert workspace.read_generated_component_map() is None

    workspace.write_generated_component_map({"Envelope": {"selector": None}})
    assert workspace.read_generated_component_map() == {"Envelope": {"selector": None}}


def test_priors_round_trip():
    workspace = ProjectWorkspace.create(_tmp_root(), "My Project", init_db=False)
    priors = {"registry": {"fields": [{"name": "Heating", "values": ["Gas", "Electric"]}]}}

    workspace.write_priors(priors)

    assert workspace.read_priors() == priors


def test_gis_dataset_round_trip():
    workspace = ProjectWorkspace.create(_tmp_root(), "My Project", init_db=False)

    assert workspace.read_gis_dataset() is None

    dataset = {"filename": "buildings.csv", "rows": [{"a": 1}]}
    workspace.write_gis_dataset(dataset)
    assert workspace.read_gis_dataset() == dataset

    workspace.clear_gis_dataset()
    assert workspace.read_gis_dataset() is None


def test_create_and_open_components_db():
    workspace = ProjectWorkspace.create(_tmp_root(), "My Project", init_db=True)

    assert workspace.components_db_path.exists()

    client = workspace.prisma_client()
    client.connect()
    try:
        assert client.lighting.count() == 0
    finally:
        client.disconnect()
