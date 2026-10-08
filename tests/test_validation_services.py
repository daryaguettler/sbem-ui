import sys
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent / "server"
sys.path.insert(0, str(SERVER_DIR))

from services.component_map import generate_component_names, validate_component_map
from services.prior_trees import validate_prior_tree
from services.semantic_fields import validate_semantic_field, validate_semantic_fields_config


def test_validate_component_map_detects_unknown_field():
    component_map = {
        "Envelope": {
            "selector": {"source_fields": ["Region", "MissingField"]},
        }
    }
    result = validate_component_map(component_map, ["Region"])

    assert result["valid"] is False
    assert any("MissingField" in error for error in result["errors"])


def test_generate_component_names_creates_combinations():
    component_map = {
        "Heating": {
            "selector": {"source_fields": ["Typology"], "suffix": "Main"},
        }
    }
    semantic_fields = [{"name": "Typology", "options": ["SFH", "MFH"]}]
    names = generate_component_names(component_map, semantic_fields)

    assert "Heating_SFH_Main" not in names
    assert "SFH_Main" in names
    assert "MFH_Main" in names


def test_validate_prior_tree_requires_targets():
    config = {
        "Registry": {"Fields": [{"Name": "Typology"}]},
        "Priors": {},
    }
    result = validate_prior_tree(config, ["Heating"])

    assert result["valid"] is False
    assert any("Heating" in error for error in result["errors"])


def test_validate_semantic_field_requires_options():
    errors = validate_semantic_field({"name": "Typology", "type": "stochastic"}, [])
    assert any("option" in error.lower() for error in errors)


def test_validate_semantic_fields_config_detects_duplicates():
    config = {
        "fields": [
            {"name": "Typology", "options": ["SFH"], "type": "stochastic"},
            {"name": "Typology", "options": ["MFH"], "type": "stochastic"},
        ]
    }
    result = validate_semantic_fields_config(config)

    assert result["valid"] is False
