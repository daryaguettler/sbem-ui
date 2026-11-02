"""Sampling: building selection, prior draws written into the GIS globi runs."""

import json
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent / "server"
sys.path.insert(0, str(SERVER_DIR))

from fastapi.testclient import TestClient
from main import app

from conftest import open_temp_workspace

client = TestClient(app)

TYPOLOGIES = ["Hospital", "Hotel", "Office", "Residential", "School"]
TYPOLOGY = {
    "id": "f-typ",
    "name": "Typology",
    "type": "deterministic",
    "data_type": "categorical",
    "options": TYPOLOGIES,
    "requires_prior": False,
    "transformation_rule": {
        "id": "t-typ",
        "type": "categorical_mapping",
        "source_column": "Typology",
        "target_field": "Typology",
        "categorical_groups": [{"group_label": t, "source_values": [t]} for t in TYPOLOGIES],
    },
}
HEATING = {
    "id": "f-heat",
    "name": "Heating",
    "type": "stochastic",
    "data_type": "categorical",
    "options": ["Gas", "HeatPump"],
    "requires_prior": True,
}
FIELDS = [TYPOLOGY, HEATING]


def setup_function():
    open_temp_workspace()
    assert client.post("/api/gis/sample").status_code == 200
    mappings = {"building_id": "building_id", "num_floors": "num_storeys", "height": "height"}
    cleaned = client.post("/api/gis/clean", json={"column_mappings": mappings, "validate_columns": ["building_id"]})
    assert cleaned.json()["validation"]["valid"]


def heating_config() -> dict:
    generated = client.post(
        "/api/prior-trees/generate",
        json={"fields": FIELDS, "target": "Heating", "target_values": ["Gas", "HeatPump"],
              "condition_on": ["Typology"], "method": "uniform"},
    ).json()
    config = {"registry": {"fields": []}, "priors": {}, "joints": [generated["joint"]], "scenarios": []}
    config["registry"]["fields"] = client.post(
        "/api/prior-trees/registry-suggestions", json={"fields": FIELDS, "config": config}
    ).json()["fields"]
    return config


def post(path: str, settings: dict, fields=FIELDS, config=None):
    body = {"fields": fields, "config": heating_config() if config is None else config, "settings": settings}
    return client.post(f"/api/sampling/{path}", json=body)


def test_preview_counts_buildings_times_draws():
    summary = post("preview", {"draws": 3, "buildings": {"mode": "random", "n": 10}}).json()
    assert summary["buildings"] == 10
    assert summary["simulations"] == 30
    assert summary["estimated"] == ["Heating"]


def test_write_draws_every_estimated_characteristic_with_unique_ids():
    result = post("write", {"draws": 2, "seed": 1, "buildings": {"mode": "random", "n": 5}})
    assert result.status_code == 200, result.text
    assert result.json()["rows"] == 10

    workspace = app.state.workspace
    features = json.loads((workspace.root / "gis" / "buildings-sampled.geojson").read_text())["features"]
    ids = [f["properties"]["building_id"] for f in features]
    assert len(set(ids)) == 10 and all("__" in i for i in ids)
    assert {f["properties"]["Heating"] for f in features} <= {"Gas", "HeatPump"}
    assert all(f["properties"]["Typology"] in TYPOLOGIES and f["geometry"] for f in features)
    assert (workspace.root / "sampling.yaml").exists()


def test_same_seed_same_sample():
    settings = {"draws": 2, "seed": 7, "buildings": {"mode": "random", "n": 8}}
    path = Path(app.state.workspace.root) / "gis" / "buildings-sampled.geojson"
    post("write", settings)
    first = path.read_text()
    post("write", settings)
    assert path.read_text() == first


def test_stratified_takes_n_per_combination():
    summary = post("preview", {"buildings": {"mode": "stratified", "per_stratum": 2, "strata": ["Typology"]}}).json()
    assert summary["strata"] == 5
    assert summary["buildings"] == 10


def test_without_estimates_one_draw_per_building():
    summary = post("preview", {"draws": 5}, fields=[TYPOLOGY], config={}).json()
    assert summary["draws"] == 1
    assert summary["simulations"] == 100


def test_refuses_an_estimated_characteristic_without_an_estimate():
    response = post("preview", {}, config={})
    assert response.status_code == 400
    assert "Heating" in response.json()["detail"]
