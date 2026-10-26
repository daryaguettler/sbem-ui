"""Semantic field validation helpers."""

from typing import Any


def validate_semantic_field(field: dict[str, Any], gis_columns: list[str] | None = None) -> list[str]:
    gis_columns = gis_columns or []
    errors: list[str] = []

    if not field.get("name"):
        errors.append("Field name is required.")

    if not field.get("options"):
        errors.append(f"Field '{field.get('name', 'unknown')}' requires at least one option.")

    if field.get("type") == "deterministic":
        name = field.get("name")
        options = set(field.get("options") or [])
        rule = field.get("transformation_rule") or {}
        source_column = rule.get("source_column")
        if not source_column:
            errors.append(f"'{name}' gets its value from GIS data, so it needs a GIS column.")
        elif gis_columns and source_column not in gis_columns:
            errors.append(f"'{name}' uses GIS column '{source_column}', which isn't in the data.")

        if rule.get("type") == "numeric_range":
            ranges = rule.get("numeric_ranges") or []
            if not ranges:
                errors.append(f"'{name}' needs at least one range.")
            for r in ranges:
                if r["label"] not in options:
                    errors.append(f"'{name}': range label '{r['label']}' is not one of the options.")
                if r["min"] > r["max"]:
                    errors.append(f"'{name}': range '{r['label']}' has min greater than max.")

        if rule.get("type") == "categorical_mapping":
            groups = rule.get("categorical_groups") or []
            if not groups:
                errors.append(f"'{name}' needs at least one value mapping.")
            for group in groups:
                if group["group_label"] not in options:
                    errors.append(
                        f"'{name}': mapping label '{group['group_label']}' is not one of the options."
                    )

    return errors


def validate_semantic_fields_config(
    config: dict[str, Any], gis_columns: list[str] | None = None
) -> dict[str, Any]:
    fields = config.get("fields", [])
    errors: list[str] = []
    names: set[str] = set()

    for field in fields:
        field_errors = validate_semantic_field(field, gis_columns)
        errors.extend(field_errors)

        name = field.get("name")
        if name:
            if name in names:
                errors.append(f"Duplicate field name '{name}'.")
            names.add(name)

    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }


def semantic_fields_to_yaml(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "Name": config.get("name") or config.get("config_name") or "Semantic Fields",
        "Fields": [
            {
                "Name": field.get("name"),
                "Options": field.get("options", []),
                "Description": field.get("description"),
                "Data_Type": field.get("data_type"),
                "Type": field.get("type") if field.get("type") == "stochastic" else None,
                "Requires_Prior": field.get("requires_prior") or None,
                "GIS_Source": (field.get("transformation_rule") or {}).get("source_column"),
                "Transformation": (field.get("transformation_rule") or {}).get("type"),
                "Ranges": (field.get("transformation_rule") or {}).get("numeric_ranges"),
                "Groups": (field.get("transformation_rule") or {}).get("categorical_groups"),
            }
            for field in config.get("fields", [])
        ],
        "Building_ID_col": config.get("building_id_col"),
        "Num_Floors_col": config.get("num_floors_col"),
    }
