"""Canonical GloBI GIS column roles for mapping and validation."""

from typing import Any

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
    },
    {
        "key": "height",
        "label": "Building height (m)",
        "yaml_key": "Height_col",
        "required_group": "height_or_floors",
        "recommended": False,
        "description": "Building height in meters. Required if number of floors is not mapped.",
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
        "description": "Optional. Imputed by GloBI if omitted.",
    },
    {
        "key": "basement",
        "label": "Basement status",
        "yaml_key": "Basement_col",
        "required": False,
        "recommended": False,
        "description": "Optional. Imputed by GloBI if omitted.",
    },
    {
        "key": "attic",
        "label": "Attic status",
        "yaml_key": "Attic_col",
        "required": False,
        "recommended": False,
        "description": "Optional. Imputed by GloBI if omitted.",
    },
]

ROLE_MATCH_HINTS: dict[str, list[str]] = {
    "building_id": ["building_id", "id", "objectid", "oid", "bldg_id", "parcel_id"],
    "num_floors": ["num_floors", "num_storeys", "story", "stories", "floors"],
    "height": ["height", "bldg_height", "building_height"],
    "footprint_area": ["sqft_assessor", "sqftstrc", "bl_encsqft", "footprint_area", "gfa", "area"],
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
