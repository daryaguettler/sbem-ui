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
        rule = field.get("transformation_rule") or {}
        source_column = rule.get("source_column")
        if not source_column:
            errors.append(
                f"Deterministic field '{field.get('name')}' requires a GIS source column."
            )
        elif gis_columns and source_column not in gis_columns:
            errors.append(
                f"Deterministic field '{field.get('name')}' references unknown GIS column '{source_column}'."
            )

        if rule.get("type") == "numeric_range" and not rule.get("numeric_ranges"):
            errors.append(
                f"Deterministic field '{field.get('name')}' requires numeric ranges."
            )

        if rule.get("type") == "categorical_mapping":
            groups = rule.get("categorical_groups") or []
            if not groups:
                errors.append(
                    f"Deterministic field '{field.get('name')}' requires categorical mapping rules."
                )

    if field.get("type") == "stochastic" and field.get("requires_prior") and not field.get("name"):
        errors.append("Stochastic field requires a name for prior linkage.")

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
