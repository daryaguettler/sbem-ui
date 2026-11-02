import shutil
from pathlib import Path

import globi
import pytest
from fastapi.testclient import TestClient
from main import app

from conftest import open_temp_workspace

client = TestClient(app)

# globi is a sibling editable checkout; its e2e library has real SpaceUse records.
E2E_DB = Path(globi.__file__).parents[2] / "tests/data/e2e/components-lib.db"
SPACE_USE = "TestRegion_Hospital_High_Baseline"
CONFIG = {
    "seed": 0,
    "semantic_field": "Typology",
    "default": {"time_shift_std_h": 1.0, "hourly_noise_std": 0.05},
    "by_value": {"Hospital": {"time_shift_std_h": 0.0, "hourly_noise_std": 0.0}},
}


def setup_function():
    open_temp_workspace()


def _preview(**body):
    return client.post("/api/schedule-variability/preview", json={"config": CONFIG, "space_use": SPACE_USE, **body})


@pytest.mark.skipif(not E2E_DB.exists(), reason="needs the sibling globi checkout")
def test_preview_returns_seeded_bounded_samples():
    workspace = open_temp_workspace()
    shutil.copy(E2E_DB, workspace.components_db_path)

    response = _preview(n=5)
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["samples"]) == 5
    curves = [s["curves"]["occupancy"] for s in payload["samples"]]
    assert all(len(c) == 24 and all(0 <= v <= 1 for v in c) for c in curves)
    assert len({tuple(c) for c in curves}) == 5
    assert _preview(n=5).json() == payload

    # the Hospital override turns the shape noise off
    hospital = _preview(n=3, value="Hospital").json()
    assert all(s["curves"]["occupancy"] == hospital["base"]["occupancy"] for s in hospital["samples"])


@pytest.mark.skipif(not E2E_DB.exists(), reason="needs the sibling globi checkout")
def test_preview_rejects_unknown_space_use_and_bad_config():
    workspace = open_temp_workspace()
    shutil.copy(E2E_DB, workspace.components_db_path)
    assert _preview(space_use="nope").status_code == 404
    bad = client.post(
        "/api/schedule-variability/preview",
        json={"config": {"default": {"intensity_cv": -1}}, "space_use": SPACE_USE},
    )
    assert bad.status_code == 422


def test_saved_config_round_trips_and_invalid_is_refused():
    saved = client.post("/api/artifacts/schedule-variability", json={"payload": CONFIG})
    assert saved.status_code == 200
    content = client.get("/api/artifacts/schedule-variability").json()["content"]
    assert content["by_value"] == CONFIG["by_value"]
    assert content["default"]["time_shift_std_h"] == 1.0

    refused = client.post("/api/artifacts/schedule-variability", json={"payload": {"by_value": {"x": {}}}})
    assert refused.status_code == 404
