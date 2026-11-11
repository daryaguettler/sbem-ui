"""Canonical GloBI GIS column roles for mapping and validation.

Value rules (kind, bounds, allowed values) come from globi itself, so they match what
globi's GIS preprocessor keeps; buildings breaking them are dropped there silently.
"""

from typing import Any, get_args

from globi.models.configs import DeterministicGISPreprocessorConfig
from globi.type_utils.literals import BasementAtticOccupationConditioningStatus

_GIS_DEFAULTS = {name: f.default for name, f in DeterministicGISPreprocessorConfig.model_fields.items()}
_STATUSES = list(get_args(BasementAtticOccupationConditioningStatus))

GLOBI_COLUMN_ROLES: list[dict[str, Any]] = [
    {
        "key": "building_id",
        "label": "Building ID",
        "yaml_key": "Building_ID_col",
        "required": True,
        "recommended": True,
        "description": "Unique identifier for each building row.",
    },
    {
        "key": "num_floors",
        "label": "Number of floors",
        "yaml_key": "Num_Floors_col",
        "required_group": "height_or_floors",
        "recommended": True,
        "description": "Floor count. Required if building height is not mapped.",
        "kind": "int",
        "min": _GIS_DEFAULTS["min_num_floors"],
        "max": _GIS_DEFAULTS["max_num_floors"],
    },
    {
        "key": "height",
        "label": "Building height (m)",
        "yaml_key": "Height_col",
        "required_group": "height_or_floors",
        "recommended": False,
        "description": "Building height in meters. Required if number of floors is not mapped.",
        "kind": "float",
        "min": _GIS_DEFAULTS["min_building_height"],
        "max": _GIS_DEFAULTS["max_building_height"],
    },
    {
        "key": "footprint_area",
        "label": "Structure / assessor area",
        "yaml_key": None,
        "required": False,
        "recommended": True,
        "description": "Assessor or structure area such as sqft_assessor or SQFTSTRC.",
    },
    {
        "key": "wwr",
        "label": "Window-to-wall ratio",
        "yaml_key": "WWR_col",
        "required": False,
        "recommended": False,
        "description": "Optional. Blanks are filled with GloBI's default.",
        "kind": "float",
        "min": 0,
        "max": 1,
    },
    {
        "key": "basement",
        "label": "Basement status",
        "yaml_key": "Basement_col",
        "required": False,
        "recommended": False,
        "description": "Optional. Blanks are filled with GloBI's default.",
        "kind": "category",
        "allowed_values": _STATUSES,
    },
    {
        "key": "attic",
        "label": "Attic status",
        "yaml_key": "Attic_col",
        "required": False,
        "recommended": False,
        "description": "Optional. Blanks are filled with GloBI's default.",
        "kind": "category",
        "allowed_values": _STATUSES,
    },
]


def _rule_text(role: dict[str, Any]) -> str | None:
    if role.get("allowed_values"):
        return "One of: " + ", ".join(role["allowed_values"]) + "."
    if role.get("kind") in ("int", "float"):
        noun = "Whole number" if role["kind"] == "int" else "Number"
        return f"{noun} from {role['min']} to {role['max']}."
    return None


for _role in GLOBI_COLUMN_ROLES:
    _role["rule"] = _rule_text(_role)


def breaks_rule(value: Any, role: dict[str, Any]) -> bool:
    """True if GloBI would drop a building with this (non-blank) value for the role."""
    if role.get("allowed_values"):
        return str(value) not in role["allowed_values"]
    if role.get("kind") not in ("int", "float"):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return True
    if role["kind"] == "int" and not number.is_integer():
        return True
    return not role["min"] <= number <= role["max"]


ROLE_MATCH_HINTS: dict[str, list[str]] = {
    "building_id": ["building_id", "id", "objectid", "oid", "bldg_id", "parcel_id"],
    "num_floors": ["num_floors", "num_storeys", "story", "stories", "floors"],
    "height": ["height", "bldg_height", "building_height"],
    "footprint_area": ["sqft_assessor", "sqftstrc", "bl_encsqft", "footprint_area", "gfa", "area"],
    "wwr": ["wwr", "window_to_wall"],
    "basement": ["basement", "bsmt"],
    "attic": ["attic"],
}


def suggest_column_mappings(column_names: list[str]) -> dict[str, str]:
    """Suggest source columns for each GloBI role based on column name similarity."""
    normalized = {name: name.lower().replace(" ", "_") for name in column_names}
    suggestions: dict[str, str] = {}

    for role in GLOBI_COLUMN_ROLES:
        hints = ROLE_MATCH_HINTS.get(role["key"], [])
        for source_name, source_norm in normalized.items():
            if source_norm in hints or any(hint in source_norm for hint in hints):
                suggestions[role["key"]] = source_name
                break

    return suggestions


def mappings_to_semantic_field_cols(column_mappings: dict[str, str | None]) -> dict[str, str]:
    """Convert role mappings to semantic-fields.yml *_col keys."""
    cols: dict[str, str] = {}
    for role in GLOBI_COLUMN_ROLES:
        yaml_key = role.get("yaml_key")
        source = column_mappings.get(role["key"])
        if yaml_key and source:
            cols[yaml_key] = source
    return cols
