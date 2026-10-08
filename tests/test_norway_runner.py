import json
import tempfile
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from conftest import open_temp_workspace
from main import app
from services.norway_runner import (
    MAX_TEST_BUILDINGS,
    RunnerError,
    build_argv,
    read_sampling,
    set_yaml_key,
    write_sampling,
)
from services.workspace import ProjectWorkspace

client = TestClient(app)

TRAINING = """# budget comment
n_per_iter: [5000, 5000]
min_per_stratum: 200
norway_training:
  # strata comment
  strata_fields: [weather_station, Typology]
  strata_bins: {}
  context_per_stratum: 2500
"""


def test_set_yaml_key_keeps_comments_and_other_keys():
    out = set_yaml_key(TRAINING, "strata_fields", ["Typology", "Age_bracket"], parent="norway_training")
    out = set_yaml_key(out, "min_per_stratum", 50)
    assert "# strata comment" in out and "# budget comment" in out
    parsed = yaml.safe_load(out)
    assert parsed["norway_training"]["strata_fields"] == ["Typology", "Age_bracket"]
    assert parsed["norway_training"]["context_per_stratum"] == 2500
    assert parsed["min_per_stratum"] == 50


def test_set_yaml_key_appends_missing_keys_and_blocks():
    out = set_yaml_key("seed: 0\n", "partition_field", "kommune")
    out = set_yaml_key(out, "strata_bins", {"num_floors": [1, 3]}, parent="norway_training")
    parsed = yaml.safe_load(out)
    assert parsed == {
        "seed": 0,
        "partition_field": "kommune",
        "norway_training": {"strata_bins": {"num_floors": [1, 3]}},
    }


def test_sampling_round_trip():
    root = Path(tempfile.mkdtemp())
    training, inference = root / "training.yml", root / "inference.yml"
    training.write_text(TRAINING)
    inference.write_text("partition_field: null  # required\nn_samples: 1000\n")
    write_sampling(training, inference, {"partition_field": "kommune", "strata_fields": ["Typology"]})
    settings = read_sampling(training, inference)
    assert settings["partition_field"] == "kommune"
    assert settings["strata_fields"] == ["Typology"]
    assert settings["n_samples"] == 1000


def test_test_run_is_capped():
    assert build_argv("test-run", {"n": 10, "packages": ["A"]})[:5] == [
        "test-run", "--json", "--n", "10", "--samples"
    ]
    with pytest.raises(RunnerError):
        build_argv("test-run", {"n": MAX_TEST_BUILDINGS + 1})
    with pytest.raises(RunnerError):
        build_argv("test-run", {"n": 5, "samples": 10})
    with pytest.raises(RunnerError):
        build_argv("deploy", {})


def test_runner_endpoints():
    open_temp_workspace()
    assert client.get("/api/runner/status").json()["available"] is False
    response = client.post("/api/runner/jobs", json={"command": "validate"})
    assert response.status_code == 400
    assert "runner" in response.json()["detail"]


def test_sampling_endpoint_uses_project_files_map():
    root = Path(tempfile.mkdtemp()) / "inputs"
    (root / "configs").mkdir(parents=True)
    (root / "configs" / "training.yml").write_text(TRAINING)
    (root / "configs" / "inference.yml").write_text("partition_field: null\n")
    (root / "project.json").write_text(json.dumps({"name": "N", "schema_version": 1}))
    app.state.workspace = ProjectWorkspace.open(root)
    response = client.post("/api/runner/sampling", json={"partition_field": "fylke"})
    assert response.status_code == 200
    assert response.json()["partition_field"] == "fylke"
    assert response.json()["strata_fields"] == ["weather_station", "Typology"]
