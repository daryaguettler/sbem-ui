"""Prior tree generation, validation, and sampling."""

import random
import sys
from io import BytesIO
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent / "server"
sys.path.insert(0, str(SERVER_DIR))

import pytest
from fastapi.testclient import TestClient
from main import app
from semantic_priors import RegionConfig

from conftest import open_temp_workspace

client = TestClient(app)


def setup_function():
    open_temp_workspace()


# The stock the tests condition on: heating fuel depends on construction era, so an
# empirical generation has a signal to find and a uniform one does not.
AGE_FUEL_WEIGHTS = {
    "pre_1975": [0.1, 0.2, 0.7],
    "btw_1975_2003": [0.3, 0.6, 0.1],
    "post_2003": [0.7, 0.3, 0.0],
}
FUELS = ["Electricity", "NaturalGas", "FuelOil"]


def _upload_stock(rows: int = 400, missing_share: float = 0.1) -> None:
    """Upload a synthetic building stock and mark it validated."""
    rng = random.Random(7)
    lines = ["building_id,num_floors,year_built,typology,heating_fuel,wwr"]
    for index in range(rows):
        year = rng.choice([1930, 1960, 1985, 1998, 2008, 2018])
        bracket = "pre_1975" if year < 1975 else ("btw_1975_2003" if year < 2004 else "post_2003")
        fuel = rng.choices(FUELS, AGE_FUEL_WEIGHTS[bracket])[0]
        if rng.random() < missing_share:
            fuel = ""
        typology = rng.choice(["SFH", "MFH"])
        lines.append(
            f"b{index},{rng.randint(1, 4)},{year},{typology},{fuel},{rng.uniform(0.1, 0.3):.3f}"
        )

    content = ("\n".join(lines) + "\n").encode()
    upload = client.post(
        "/api/gis/upload", files={"file": ("stock.csv", BytesIO(content), "text/csv")}
    )
    assert upload.status_code == 200
    mappings = upload.json()["columnMappings"]
    mappings["building_id"] = "building_id"
    cleaned = client.post(
        "/api/gis/clean",
        json={"column_mappings": mappings, "validate_columns": ["building_id"]},
    )
    assert cleaned.json()["validation"]["valid"]


AGE_FIELD = {
    "id": "f-age",
    "name": "Age_bracket",
    "type": "deterministic",
    # The editor tags a numeric_range field by its *source* column's type, which is
    # numeric even though the field itself produces era labels.
    "data_type": "numeric",
    "options": ["pre_1975", "btw_1975_2003", "post_2003"],
    "transformation_rule": {
        "id": "t-age",
        "type": "numeric_range",
        "source_column": "year_built",
        "target_field": "Age_bracket",
        "numeric_ranges": [
            {"min": 0, "max": 1974, "label": "pre_1975"},
            {"min": 1975, "max": 2003, "label": "btw_1975_2003"},
            {"min": 2004, "max": 3000, "label": "post_2003"},
        ],
    },
}

TYPOLOGY_FIELD = {
    "id": "f-typ",
    "name": "Typology",
    "type": "deterministic",
    "data_type": "categorical",
    "options": ["SFH", "MFH"],
    "transformation_rule": {
        "id": "t-typ",
        "type": "categorical_mapping",
        "source_column": "typology",
        "target_field": "Typology",
        "categorical_groups": [
            {"group_label": "SFH", "source_values": ["SFH"]},
            {"group_label": "MFH", "source_values": ["MFH"]},
        ],
    },
}

HEATING_FIELD = {
    "id": "f-heat",
    "name": "HeatingFuel",
    "type": "stochastic",
    "data_type": "categorical",
    "options": FUELS,
    "requires_prior": True,
}

FIELDS = [AGE_FIELD, TYPOLOGY_FIELD, HEATING_FIELD]


def _generate(**overrides):
    body = {
        "fields": FIELDS,
        "target": "HeatingFuel",
        "target_values": FUELS,
        "condition_on": ["Age_bracket"],
        "method": "uniform",
    }
    body.update(overrides)
    return client.post("/api/prior-trees/generate", json=body)


def _config_from(generated: dict) -> dict:
    """A complete config around one generated joint, with the registry filled in."""
    config = {"registry": {"fields": []}, "priors": {}, "joints": [generated["joint"]], "scenarios": []}
    suggestions = client.post(
        "/api/prior-trees/registry-suggestions", json={"fields": FIELDS, "config": config}
    ).json()["fields"]
    config["registry"]["fields"] = suggestions
    return config


# -- what can be conditioned on ---------------------------------------------


def test_conditioning_candidates_span_semantic_fields_and_raw_gis_columns():
    _upload_stock()
    response = client.post("/api/prior-trees/fields", json={"fields": FIELDS})
    assert response.status_code == 200

    candidates = {item["name"]: item for item in response.json()["candidates"]}
    # A deterministic semantic field is observed once its rule is applied to the rows.
    assert candidates["Age_bracket"]["source"] == "semantic"
    assert candidates["Age_bracket"]["coverage"] == 1.0
    assert set(candidates["Age_bracket"]["observedValues"]) == set(AGE_FUEL_WEIGHTS)
    # A raw GIS column the user never made a semantic field of is still usable.
    assert candidates["heating_fuel"]["source"] == "gis"
    assert candidates["heating_fuel"]["conditionable"] is True
    # A stochastic field has no observed values but can be conditioned on.
    assert candidates["HeatingFuel"]["source"] == "sampled"
    assert candidates["HeatingFuel"]["presentCount"] == 0


def test_a_numeric_range_field_is_conditionable_because_it_produces_buckets():
    _upload_stock()
    candidates = {
        item["name"]: item
        for item in client.post("/api/prior-trees/fields", json={"fields": FIELDS}).json()["candidates"]
    }
    # Age_bracket reads a year (numeric) but produces era labels, so it keys a table.
    assert candidates["Age_bracket"]["dtype"] == "categorical"
    assert candidates["Age_bracket"]["conditionable"] is True


def test_numeric_gis_columns_cannot_be_conditioned_on_directly():
    _upload_stock()
    candidates = {
        item["name"]: item
        for item in client.post("/api/prior-trees/fields", json={"fields": FIELDS}).json()["candidates"]
    }
    # A compound key is a string join, so a continuous column has to be bucketed first.
    assert candidates["wwr"]["dtype"] == "numeric"
    assert candidates["wwr"]["conditionable"] is False
    assert candidates["wwr"]["numericSummary"]["min"] >= 0.1


def test_condition_preview_counts_only_combinations_that_occur():
    _upload_stock()
    response = client.post(
        "/api/prior-trees/condition-preview",
        json={"fields": FIELDS, "condition_on": ["Typology", "Age_bracket"]},
    )
    payload = response.json()
    assert payload["compoundKey"] == "compound.Typology.Age_bracket"
    assert payload["keyCount"] == 6  # 2 typologies x 3 age brackets, all present
    assert payload["coverage"] == 1.0


# -- generating --------------------------------------------------------------


def test_uniform_generation_spreads_weight_evenly_over_every_combination():
    _upload_stock()
    generated = _generate(condition_on=["Typology", "Age_bracket"]).json()

    assert generated["mode"] == "joint"
    assert len(generated["keys"]) == 6
    for row in generated["joint"]["table"].values():
        assert row == pytest.approx({fuel: 1 / 3 for fuel in FUELS}, abs=1e-4)
    assert all(not key["estimated"] for key in generated["keys"])


def test_empirical_generation_recovers_the_signal_in_the_gis_data():
    _upload_stock(rows=1200, missing_share=0.05)
    generated = _generate(
        condition_on=["Age_bracket"], method="empirical", observed_column="heating_fuel"
    ).json()

    table = generated["joint"]["table"]
    assert set(table) == set(AGE_FUEL_WEIGHTS)
    # Oil dominates the old stock and disappears from the new, as the data says.
    assert table["pre_1975"]["FuelOil"] > 0.5
    assert table["post_2003"]["FuelOil"] < 0.1
    assert table["post_2003"]["Electricity"] > table["pre_1975"]["Electricity"]
    assert all(key["estimated"] for key in generated["keys"])
    # The fallback is the stock-wide marginal, for combinations not in the table.
    assert sum(generated["fallback"].values()) == pytest.approx(1.0, abs=1e-4)


def test_thin_combinations_inherit_the_overall_distribution():
    _upload_stock(rows=200)
    generated = _generate(
        condition_on=["Typology", "Age_bracket"],
        method="empirical",
        observed_column="heating_fuel",
        min_count=10_000,  # nothing can clear this, so every row falls back
    ).json()

    assert all(not key["estimated"] for key in generated["keys"])
    assert any("fewer than" in warning for warning in generated["warnings"])
    for row in generated["joint"]["table"].values():
        assert row == pytest.approx(generated["fallback"], abs=1e-6)


def test_generating_without_conditions_gives_one_distribution_for_the_whole_stock():
    _upload_stock()
    generated = _generate(
        condition_on=[], method="empirical", observed_column="heating_fuel"
    ).json()

    assert generated["mode"] == "unconditional"
    assert generated["joint"] is None
    assert generated["prior"]["sampler"]["values"] == FUELS
    assert sum(generated["prior"]["sampler"]["weights"]) == pytest.approx(1.0, abs=1e-4)


def test_a_numeric_target_is_fitted_as_a_clipped_normal():
    _upload_stock()
    generated = _generate(
        target="wwr_prior",
        target_values=[],
        condition_on=[],
        dtype="numeric",
        method="empirical",
        observed_column="wwr",
    ).json()

    sampler = generated["prior"]["sampler"]
    assert 0.1 <= sampler["mean"] <= 0.3
    assert sampler["clip_min"] >= 0.1
    assert sampler["clip_max"] <= 0.3


def test_estimating_from_a_column_whose_values_dont_match_falls_back_to_uniform():
    _upload_stock()
    generated = _generate(
        target_values=["Heat pump", "Boiler"],
        method="empirical",
        observed_column="heating_fuel",
    ).json()

    assert any("outside the field's declared options" in w for w in generated["warnings"])
    for row in generated["joint"]["table"].values():
        assert row == pytest.approx({"Heat pump": 0.5, "Boiler": 0.5}, abs=1e-4)


def test_estimating_without_an_observed_column_is_rejected():
    _upload_stock()
    response = _generate(method="empirical", observed_column=None)
    assert response.status_code == 400
    assert "observed column" in response.json()["detail"]


# -- validating --------------------------------------------------------------


def test_a_generated_prior_validates_and_loads_in_the_sampling_engine():
    _upload_stock()
    config = _config_from(_generate(condition_on=["Typology", "Age_bracket"]).json())

    result = client.post(
        "/api/prior-trees/validate",
        json={"config": config, "required_targets": ["HeatingFuel"], "fields": FIELDS},
    ).json()

    assert result["valid"], result["errors"]
    assert result["contextFields"] == ["Age_bracket", "Typology"]
    # The same document the UI holds is what semantic_priors loads.
    assert "HeatingFuel" in RegionConfig.from_dict(config).to_priors().sampled_features


def test_validation_reports_a_stochastic_field_with_no_prior():
    result = client.post(
        "/api/prior-trees/validate",
        json={"config": {}, "required_targets": ["HeatingFuel"], "fields": FIELDS},
    ).json()

    assert result["valid"] is False
    assert any("HeatingFuel" in error and "no prior" in error for error in result["errors"])


def test_validation_catches_weights_on_values_the_registry_never_declared():
    _upload_stock()
    config = _config_from(_generate().json())
    for field in config["registry"]["fields"]:
        if field["name"] == "HeatingFuel":
            field["values"] = ["Electricity"]  # the table still weights gas and oil

    result = client.post(
        "/api/prior-trees/validate",
        json={"config": config, "required_targets": ["HeatingFuel"], "fields": FIELDS},
    ).json()

    assert result["valid"] is False
    assert any("undeclared values" in error for error in result["errors"])


def test_validation_rejects_a_structurally_broken_config_rather_than_crashing():
    result = client.post(
        "/api/prior-trees/validate",
        json={"config": {"joints": [{"target": "X"}]}, "required_targets": [], "fields": []},
    ).json()

    assert result["valid"] is False
    assert result["errors"]


def test_the_dependency_graph_orders_context_then_compound_key_then_target():
    _upload_stock()
    config = _config_from(_generate(condition_on=["Typology", "Age_bracket"]).json())

    graph = client.post(
        "/api/prior-trees/dependencies", json={"config": config, "fields": FIELDS}
    ).json()

    kinds = {node["name"]: node["kind"] for node in graph["nodes"]}
    depths = {node["name"]: node["depth"] for node in graph["nodes"]}
    assert kinds["Age_bracket"] == "context"
    assert kinds["compound.Typology.Age_bracket"] == "compound"
    assert kinds["HeatingFuel"] == "conditional"
    assert depths["Age_bracket"] < depths["compound.Typology.Age_bracket"] < depths["HeatingFuel"]


# -- sampling ----------------------------------------------------------------


def test_sampling_runs_over_the_projects_own_buildings():
    _upload_stock(rows=1200, missing_share=0.05)
    config = _config_from(
        _generate(
            condition_on=["Age_bracket"], method="empirical", observed_column="heating_fuel"
        ).json()
    )

    sample = client.post(
        "/api/prior-trees/sample", json={"config": config, "fields": FIELDS, "n": 3000, "seed": 0}
    ).json()

    assert sample["contextSource"] == "gis"
    assert sample["contextFields"] == ["Age_bracket"]
    assert len(sample["sampleRows"]) == 25

    heating = next(d for d in sample["distributions"] if d["feature"] == "HeatingFuel")
    assert heating["kind"] == "conditional"
    assert sum(entry["share"] for entry in heating["marginal"]) == pytest.approx(1.0, abs=1e-3)

    # The breakdown is what shows the conditioning worked: old stock burns oil, new doesn't.
    rows = {row["key"]: row for row in heating["breakdown"]["rows"]}
    oil = heating["breakdown"]["values"].index("FuelOil")
    assert rows["pre_1975"]["shares"][oil] > rows["post_2003"]["shares"][oil]


def test_sampling_an_unconditioned_prior_needs_no_gis_context():
    config = {
        "registry": {"fields": [{"name": "HeatingFuel", "values": FUELS}]},
        "priors": {"HeatingFuel": {"sampler": {"values": FUELS, "weights": [0.5, 0.3, 0.2]}}},
        "joints": [],
        "scenarios": [],
    }

    sample = client.post(
        "/api/prior-trees/sample", json={"config": config, "fields": [], "n": 4000, "seed": 3}
    ).json()

    assert sample["contextSource"] == "synthetic"
    shares = {entry["value"]: entry["share"] for entry in sample["distributions"][0]["marginal"]}
    assert shares["Electricity"] == pytest.approx(0.5, abs=0.03)


def test_sampling_explains_itself_when_the_conditioning_fields_arent_in_the_gis_data():
    # No GIS upload at all, but the prior conditions on fields that would come from it.
    config = _config_from(
        {
            "joint": {
                "target": "HeatingFuel",
                "condition_on": ["Age_bracket"],
                "table": {"pre_1975": {fuel: 1 / 3 for fuel in FUELS}},
                "fallback": {fuel: 1 / 3 for fuel in FUELS},
                "separator": ".",
            }
        }
    )

    response = client.post(
        "/api/prior-trees/sample", json={"config": config, "fields": FIELDS, "n": 100, "seed": 0}
    )
    assert response.status_code == 400
    assert "Age_bracket" in response.json()["detail"]


def test_sampling_an_empty_config_is_rejected():
    response = client.post(
        "/api/prior-trees/sample", json={"config": {}, "fields": [], "n": 100, "seed": 0}
    )
    assert response.status_code == 400
    assert "no priors" in response.json()["detail"].lower()


# -- round trip --------------------------------------------------------------


def test_a_generated_prior_saves_into_the_project_and_reads_back():
    _upload_stock()
    config = _config_from(_generate(condition_on=["Age_bracket"]).json())

    saved = client.post("/api/artifacts/priors", json={"payload": config})
    assert saved.status_code == 200
    assert saved.json()["path"] == "priors/priors.yaml"

    reread = client.get("/api/prior-trees/").json()["config"]
    assert reread == config
    assert RegionConfig.from_dict(reread).to_priors().sampled_features


# -- conditioned numeric priors ----------------------------------------------
#
# A numeric target can't go in `joints` (that model compiles to categorical
# samplers), so it becomes two `priors` entries: the compound key, and a
# ConditionalPrior of clipped normals dispatching on it.

WWR_FIELD = {
    "id": "f-wwr",
    "name": "WindowRatio",
    "type": "stochastic",
    "data_type": "numeric",
    "options": [],
    "requires_prior": True,
}

NUMERIC_FIELDS = [AGE_FIELD, TYPOLOGY_FIELD, WWR_FIELD]


def _generate_numeric(**overrides):
    body = {
        "fields": NUMERIC_FIELDS,
        "target": "WindowRatio",
        "target_values": [],
        "condition_on": ["Age_bracket"],
        "dtype": "numeric",
        "method": "empirical",
        "observed_column": "wwr",
    }
    body.update(overrides)
    return client.post("/api/prior-trees/generate", json=body)


def _numeric_config(generated: dict) -> dict:
    config = {"registry": {"fields": []}, "priors": generated["priors"], "joints": [], "scenarios": []}
    config["registry"]["fields"] = client.post(
        "/api/prior-trees/registry-suggestions", json={"fields": NUMERIC_FIELDS, "config": config}
    ).json()["fields"]
    return config


def test_a_conditioned_numeric_prior_emits_its_compound_key_alongside_the_target():
    _upload_stock()
    generated = _generate_numeric(condition_on=["Typology", "Age_bracket"]).json()

    assert generated["mode"] == "conditional"
    assert generated["joint"] is None
    assert generated["compoundKey"] == "compound.Typology.Age_bracket"
    # The key has to be sampled before the target that dispatches on it.
    assert set(generated["priors"]) == {"compound.Typology.Age_bracket", "WindowRatio"}
    key_prior = generated["priors"]["compound.Typology.Age_bracket"]
    assert key_prior["sampler"]["features_to_concatenate"] == ["Typology", "Age_bracket"]
    target_prior = generated["priors"]["WindowRatio"]
    assert target_prior["source_feature"] == "compound.Typology.Age_bracket"
    assert len(target_prior["conditions"]) == 6
    assert target_prior["fallback_prior"]["std"] > 0


def test_each_combination_gets_its_own_normal_fitted_to_that_combination():
    # wwr in the shared stock is uniform 0.1-0.3 regardless of era, so instead assert
    # the fits are per-combination rather than all identical to the overall one.
    _upload_stock(rows=1200)
    generated = _generate_numeric(condition_on=["Age_bracket"]).json()

    means = [key["numeric"]["mean"] for key in generated["keys"]]
    assert len(means) == 3
    assert all(key["estimated"] for key in generated["keys"])
    # Every fit is clipped to what that combination actually spans.
    for key in generated["keys"]:
        assert key["numeric"]["clip_min"] <= key["numeric"]["mean"] <= key["numeric"]["clip_max"]
        assert key["numeric"]["std"] > 0


def test_a_thin_combination_inherits_the_overall_normal():
    _upload_stock(rows=200)
    generated = _generate_numeric(condition_on=["Typology", "Age_bracket"], min_count=10_000).json()

    assert all(not key["estimated"] for key in generated["keys"])
    assert any("fewer than" in warning for warning in generated["warnings"])
    for key in generated["keys"]:
        assert key["numeric"] == generated["fallbackNumeric"]


def test_a_numeric_prior_with_no_conditions_is_still_a_single_normal():
    _upload_stock()
    generated = _generate_numeric(condition_on=[]).json()

    assert generated["mode"] == "unconditional"
    assert set(generated["priors"]) == {"WindowRatio"}
    assert generated["priors"]["WindowRatio"]["sampler"]["std"] > 0


def test_the_registry_declares_the_conditioning_fields_not_the_generated_key():
    _upload_stock()
    config = _numeric_config(_generate_numeric(condition_on=["Typology", "Age_bracket"]).json())

    declared = {field["name"]: field for field in config["registry"]["fields"]}
    # The compound key is machinery; the fields it joins are what must be declared.
    assert not any(name.startswith("compound.") for name in declared)
    assert {"Typology", "Age_bracket", "WindowRatio"} <= set(declared)
    assert declared["WindowRatio"]["dtype"] == "numeric"


def test_a_conditioned_numeric_prior_validates_and_samples_per_combination():
    _upload_stock(rows=1200)
    config = _numeric_config(_generate_numeric(condition_on=["Age_bracket"]).json())

    result = client.post(
        "/api/prior-trees/validate",
        json={"config": config, "required_targets": ["WindowRatio"], "fields": NUMERIC_FIELDS},
    ).json()
    assert result["valid"], result["errors"]
    # The compound key is not reported as a prior target the user has to care about.
    assert result["priorTargets"] == ["WindowRatio"]

    kinds = {node["name"]: node["kind"] for node in result["dependencies"]["nodes"]}
    assert kinds["compound.Age_bracket"] == "compound"
    assert kinds["WindowRatio"] == "conditional"

    sample = client.post(
        "/api/prior-trees/sample",
        json={"config": config, "fields": NUMERIC_FIELDS, "n": 3000, "seed": 0},
    ).json()
    distribution = next(d for d in sample["distributions"] if d["feature"] == "WindowRatio")
    assert distribution["dtype"] == "numeric"
    assert distribution["histogram"] is not None
    # The per-combination summary is what shows the conditioning took effect.
    rows = {row["key"]: row for row in distribution["numericBreakdown"]["rows"]}
    assert set(rows) == {"pre_1975", "btw_1975_2003", "post_2003"}
    assert all(row["count"] > 0 and row["std"] > 0 for row in rows.values())


def test_a_conditioned_numeric_prior_recovers_a_real_signal():
    """Window ratio that genuinely grows with construction era should come back out."""
    import random
    from io import BytesIO

    rng = random.Random(5)
    means = {"pre_1975": 0.12, "btw_1975_2003": 0.20, "post_2003": 0.31}
    lines = ["building_id,num_floors,year_built,typology,wwr"]
    for index in range(900):
        year = rng.choice([1930, 1965, 1985, 1999, 2010, 2019])
        bracket = "pre_1975" if year < 1975 else ("btw_1975_2003" if year < 2004 else "post_2003")
        value = max(0.02, rng.gauss(means[bracket], 0.03))
        lines.append(f"b{index},{rng.randint(1, 3)},{year},SFH,{value:.4f}")
    content = ("\n".join(lines) + "\n").encode()

    upload = client.post(
        "/api/gis/upload", files={"file": ("wwr.csv", BytesIO(content), "text/csv")}
    )
    mappings = upload.json()["columnMappings"]
    mappings["building_id"] = "building_id"
    client.post(
        "/api/gis/clean",
        json={"column_mappings": mappings, "validate_columns": ["building_id"]},
    )

    generated = _generate_numeric(condition_on=["Age_bracket"]).json()
    fitted = {key["key"]: key["numeric"]["mean"] for key in generated["keys"]}
    for bracket, expected in means.items():
        assert fitted[bracket] == pytest.approx(expected, abs=0.02)

    sample = client.post(
        "/api/prior-trees/sample",
        json={"config": _numeric_config(generated), "fields": NUMERIC_FIELDS, "n": 6000, "seed": 1},
    ).json()
    rows = {
        row["key"]: row["mean"]
        for row in sample["distributions"][0]["numericBreakdown"]["rows"]
    }
    assert rows["pre_1975"] < rows["btw_1975_2003"] < rows["post_2003"]


def test_removing_a_conditioned_numeric_prior_is_covered_by_pruning_its_key():
    """The engine must reject a config whose compound key was dropped but is still used."""
    _upload_stock()
    generated = _generate_numeric(condition_on=["Age_bracket"]).json()
    config = _numeric_config(generated)
    del config["priors"]["compound.Age_bracket"]

    result = client.post(
        "/api/prior-trees/validate",
        json={"config": config, "required_targets": ["WindowRatio"], "fields": NUMERIC_FIELDS},
    ).json()
    assert result["valid"] is False
    assert any("compound.Age_bracket" in error for error in result["errors"])


# -- scenarios ---------------------------------------------------------------
#
# A scenario overrides sampled features on an already-drawn stock and resamples
# whatever depends on them. Baseline and scenario share one draw, so a reported
# difference is the scenario's doing rather than sampling noise.


def _scenario_config(scenarios: list[dict]) -> dict:
    """A validated heating config with `scenarios` attached."""
    config = _config_from(_generate(condition_on=["Age_bracket"]).json())
    config["scenarios"] = scenarios
    return config


ELECTRIFY_ALL = {"name": "Electrify", "overrides": {"HeatingFuel": "Electricity"}}
ELECTRIFY_NEW = {
    "name": "NewBuildOnly",
    "overrides": {
        "HeatingFuel": {
            "based_on": "Age_bracket",
            "equals": "post_2003",
            "then": "Electricity",
            "otherwise": "$keep",
        }
    },
}


def test_scenario_targets_separate_what_can_be_changed_from_what_can_be_tested():
    _upload_stock()
    config = _config_from(_generate(condition_on=["Age_bracket"]).json())

    targets = {item["name"]: item for item in
               client.post("/api/prior-trees/scenario-targets",
                           json={"config": config, "fields": FIELDS}).json()["targets"]}

    # A sampled feature can be overridden; a GIS-derived one can only be branched on.
    assert targets["HeatingFuel"].get("contextOnly") is not True
    assert targets["HeatingFuel"]["values"] == FUELS
    assert targets["Age_bracket"]["contextOnly"] is True
    # The generated join key is machinery, never something a scenario touches.
    assert not any(name.startswith("compound.") for name in targets)


def test_a_fixed_override_moves_the_whole_stock():
    _upload_stock(rows=800)
    config = _scenario_config([ELECTRIFY_ALL])

    preview = client.post(
        "/api/prior-trees/scenarios/preview",
        json={"config": config, "fields": FIELDS, "n": 2000, "seed": 0},
    ).json()

    scenario = preview["scenarios"][0]
    assert scenario["name"] == "Electrify"
    assert scenario["changed"] == ["HeatingFuel"]
    shares = {row["value"]: row for row in scenario["features"][0]["shares"]}
    assert shares["Electricity"]["scenario"] == pytest.approx(1.0)
    assert shares["Electricity"]["baseline"] < 1.0
    assert shares["FuelOil"]["scenario"] == pytest.approx(0.0)


def test_a_conditional_override_leaves_the_rest_of_the_stock_alone():
    _upload_stock(rows=1200, missing_share=0.05)
    config = _scenario_config([ELECTRIFY_NEW])

    preview = client.post(
        "/api/prior-trees/scenarios/preview",
        json={"config": config, "fields": FIELDS, "n": 3000, "seed": 0},
    ).json()

    shares = {row["value"]: row for row in preview["scenarios"][0]["features"][0]["shares"]}
    # Electricity rises, but nowhere near everything -- only post-2003 buildings convert.
    assert shares["Electricity"]["baseline"] < shares["Electricity"]["scenario"] < 1.0
    # `$keep` means the untouched stock still burns what it burned.
    assert shares["FuelOil"]["scenario"] > 0


def test_every_scenario_is_compared_against_the_same_baseline():
    _upload_stock(rows=800)
    config = _scenario_config([ELECTRIFY_ALL, ELECTRIFY_NEW])

    preview = client.post(
        "/api/prior-trees/scenarios/preview",
        json={"config": config, "fields": FIELDS, "n": 2000, "seed": 0},
    ).json()

    assert [scenario["name"] for scenario in preview["scenarios"]] == ["Electrify", "NewBuildOnly"]
    baselines = [
        {row["value"]: row["baseline"] for row in scenario["features"][0]["shares"]}
        for scenario in preview["scenarios"]
    ]
    assert baselines[0] == baselines[1]


def test_a_scenario_resamples_what_depends_on_what_it_changed():
    """Overriding an upstream field redraws the prior that conditions on it."""
    _upload_stock(rows=900, missing_share=0.05)
    # Estimated, not uniform: a uniform table is identical across eras, so changing
    # the era could not move the result and the test would prove nothing.
    config = _config_from(
        _generate(
            condition_on=["Age_bracket"], method="empirical", observed_column="heating_fuel"
        ).json()
    )
    # Make Age_bracket itself sampled, so HeatingFuel becomes downstream of it.
    config["priors"]["Age_bracket"] = {
        "sampler": {"values": ["pre_1975", "btw_1975_2003", "post_2003"], "weights": [0.4, 0.4, 0.2]}
    }
    config["scenarios"] = [{"name": "AllNew", "overrides": {"Age_bracket": "post_2003"}}]

    preview = client.post(
        "/api/prior-trees/scenarios/preview",
        json={"config": config, "fields": FIELDS, "n": 3000, "seed": 0},
    ).json()

    scenario = preview["scenarios"][0]
    assert scenario["changed"] == ["Age_bracket"]
    assert "HeatingFuel" in scenario["downstream"]

    heating = next(f for f in scenario["features"] if f["feature"] == "HeatingFuel")
    shares = {row["value"]: row for row in heating["shares"]}
    # The whole stock is now post-2003, whose prior is oil-free.
    assert shares["FuelOil"]["scenario"] < shares["FuelOil"]["baseline"]


def test_scenario_validation_catches_undeclared_values_and_unknown_fields():
    _upload_stock()
    config = _scenario_config(
        [
            {"name": "Bad", "overrides": {"HeatingFuel": "Hydrogen"}},
            {"name": "Ghost", "overrides": {"NotAField": "x"}},
            {
                "name": "BadRef",
                "overrides": {
                    "HeatingFuel": {
                        "based_on": "Nowhere",
                        "equals": "y",
                        "then": "$nothing",
                        "otherwise": "$keep",
                    }
                },
            },
        ]
    )

    result = client.post(
        "/api/prior-trees/validate",
        json={"config": config, "required_targets": ["HeatingFuel"], "fields": FIELDS},
    ).json()

    assert result["valid"] is False
    joined = " | ".join(result["errors"])
    assert "Hydrogen" in joined
    assert "NotAField" in joined
    assert "Nowhere" in joined
    assert "$nothing" in joined
    assert result["scenarios"] == ["Bad", "Ghost", "BadRef"]


def test_duplicate_scenario_names_are_rejected():
    _upload_stock()
    config = _scenario_config([ELECTRIFY_ALL, {**ELECTRIFY_ALL}])

    result = client.post(
        "/api/prior-trees/validate",
        json={"config": config, "required_targets": ["HeatingFuel"], "fields": FIELDS},
    ).json()
    assert any("both named 'Electrify'" in error for error in result["errors"])


def test_a_valid_scenario_passes_validation_and_the_engine_agrees():
    _upload_stock()
    config = _scenario_config([ELECTRIFY_ALL, ELECTRIFY_NEW])

    result = client.post(
        "/api/prior-trees/validate",
        json={"config": config, "required_targets": ["HeatingFuel"], "fields": FIELDS},
    ).json()
    assert result["valid"], result["errors"]

    parsed = RegionConfig.from_dict(config)
    assert [scenario.name for scenario in parsed.scenarios] == ["Electrify", "NewBuildOnly"]
    # The shorthand string form round-trips into a FixedOverride.
    assert parsed.scenarios_by_name["Electrify"].overrides["HeatingFuel"].set == "Electricity"


def test_previewing_with_no_scenarios_says_so():
    _upload_stock()
    config = _scenario_config([])
    response = client.post(
        "/api/prior-trees/scenarios/preview",
        json={"config": config, "fields": FIELDS, "n": 100, "seed": 0},
    )
    assert response.status_code == 400
    assert "no scenarios" in response.json()["detail"].lower()


def test_the_bundled_template_ships_a_working_scenario():
    """The residential template's Electrification scenario has to actually apply."""
    template = client.get("/api/prior-trees/templates/residential_heating.yml").json()
    config = {key: template[key] for key in ("registry", "priors", "joints", "scenarios")}

    result = client.post(
        "/api/prior-trees/validate",
        json={"config": config, "required_targets": [], "fields": []},
    ).json()
    assert result["valid"], result["errors"]
    assert result["scenarios"] == ["Electrification"]

    # No GIS data here, so the conditioning fields have to be sampled for the preview.
    config["priors"] = {
        "Typology": {"sampler": {"values": ["SFH", "MFH"], "weights": [0.7, 0.3]}},
        "Age_bracket": {
            "sampler": {
                "values": ["pre_1975", "btw_1975_2003", "post_2003"],
                "weights": [0.4, 0.4, 0.2],
            }
        },
    }
    preview = client.post(
        "/api/prior-trees/scenarios/preview",
        json={"config": config, "fields": [], "n": 3000, "seed": 0},
    ).json()

    scenario = preview["scenarios"][0]
    assert scenario["name"] == "Electrification"
    heating = next(f for f in scenario["features"] if f["feature"] == "Heating")
    shares = {row["value"]: row for row in heating["shares"]}
    # Post-2003 stock switches to a heat pump; everything older keeps what it had.
    assert shares["ASHPHeating"]["scenario"] > shares["ASHPHeating"]["baseline"]
    assert shares["OilHeating"]["scenario"] > 0
