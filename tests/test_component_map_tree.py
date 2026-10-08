import sys
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent / "server"
sys.path.insert(0, str(SERVER_DIR))

from services.component_map import (
    _collect_selectors,
    generate_component_names,
    preview_selector_names,
    remove_child_selectors,
    set_selector_at_path,
)


def test_preview_selector_names_matches_globi_convention():
    preview = preview_selector_names(
        ["Region", "Typology"],
        [
            {"name": "Region", "options": ["MA"]},
            {"name": "Typology", "options": ["SFH", "MFH"]},
        ],
        suffix="Main",
    )

    assert preview["count"] == 2
    assert "MA_SFH_Main" in preview["samples"]
    assert "MA_MFH_Main" in preview["samples"]


def test_set_selector_and_collapse_children():
    component_map = {
        "Envelope": {
            "Assemblies": {
                "FacadeAssembly": {
                    "selector": {"source_fields": ["Walls"], "suffix": "Facade"}
                }
            }
        }
    }

    updated = set_selector_at_path(
        component_map,
        "Envelope.Assemblies",
        ["Region", "Age_bracket"],
        "Bundle",
    )
    updated = remove_child_selectors(updated, "Envelope.Assemblies")

    selectors = {
        entry["path"]: entry["source_fields"]
        for entry in _collect_selectors(updated)
    }

    assert selectors["Envelope.Assemblies"] == ["Region", "Age_bracket"]
    assert "Envelope.Assemblies.FacadeAssembly" not in selectors
