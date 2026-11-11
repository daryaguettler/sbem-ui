"""GIS parsing and validation helpers."""

import csv
import io
import json
from typing import Any

MISSING_VALUES = {"", "none", "null", "nan"}


def _is_numeric(value: str) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _infer_column_type(values: list[str]) -> str:
    non_empty = [value for value in values if value not in ("", None)]
    if not non_empty:
        return "string"
    if all(_is_numeric(value) for value in non_empty):
        return "numeric"
    return "categorical"


def _summarize_columns(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []

    column_names = list(rows[0].keys())
    summaries: list[dict[str, Any]] = []

    for column_name in column_names:
        values = [str(row.get(column_name, "")) for row in rows]
        non_null_values = [value for value in values if value not in ("", "None", "null")]
        unique_values = sorted(set(non_null_values))[:25]
        summaries.append(
            {
                "name": column_name,
                "data_type": _infer_column_type(non_null_values),
                "unique_values": unique_values,
                "sample_values": non_null_values[:5],
                "nullable": len(non_null_values) < len(values),
                "null_count": len(values) - len(non_null_values),
            }
        )

    return summaries


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return text.lower() in MISSING_VALUES


def _row_has_complete_columns(row: dict[str, Any], column_names: list[str]) -> bool:
    return all(not _is_missing(row.get(column_name)) for column_name in column_names)


RuleSources = list[tuple[str, dict[str, Any]]]


def rule_sources(column_mappings: dict[str, str | None] | None, roles: list[dict[str, Any]] | None = None) -> RuleSources:
    """(source column, role) for every mapped role that has a GloBI value rule."""
    from services.globi_columns import GLOBI_COLUMN_ROLES

    column_mappings = column_mappings or {}
    return [
        (column_mappings[role["key"]], role)
        for role in roles or GLOBI_COLUMN_ROLES
        if role.get("rule") and column_mappings.get(role["key"])
    ]


def _row_breaks_rules(row: dict[str, Any], sources: RuleSources) -> bool:
    from services.globi_columns import breaks_rule

    # Blanks are not rule breaks: GloBI fills them with its defaults.
    return any(
        not _is_missing(row.get(source)) and breaks_rule(row.get(source), role) for source, role in sources
    )


def apply_value_mappings(
    dataset: dict[str, Any],
    column_mappings: dict[str, str | None],
    value_mappings: dict[str, dict[str, str]],
) -> None:
    """Rewrite mapped source values (e.g. basement "Y") to GloBI values, in rows and features alike."""
    changes = {
        column_mappings[role_key]: mapping
        for role_key, mapping in value_mappings.items()
        if column_mappings.get(role_key) and mapping
    }
    if not changes:
        return
    records = dataset.get("rows", []) + [feature.get("properties") or {} for feature in dataset.get("features", [])]
    for record in records:
        for column, mapping in changes.items():
            value = record.get(column)
            if value is not None and str(value) in mapping:
                record[column] = mapping[str(value)]
    dataset["columns"] = _summarize_columns(dataset.get("rows", []))


def parse_csv_content(content: bytes) -> dict[str, Any]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = [dict(row) for row in reader]
    fieldnames = reader.fieldnames or (list(rows[0].keys()) if rows else [])
    return {
        "rows": rows,
        "columns": _summarize_columns(rows),
        "row_count": len(rows),
        "source_format": "csv",
        "csv_fieldnames": fieldnames,
    }


def parse_geojson_content(content: bytes) -> dict[str, Any]:
    payload = json.loads(content.decode("utf-8"))
    features = payload.get("features", [])
    rows: list[dict[str, Any]] = []

    for feature in features:
        properties = dict(feature.get("properties") or {})
        rows.append(properties)

    return {
        "rows": rows,
        "features": features,
        "geojson": payload,
        "columns": _summarize_columns(rows),
        "row_count": len(rows),
        "source_format": "geojson",
    }


def parse_gis_upload(filename: str, content: bytes) -> dict[str, Any]:
    lower_name = filename.lower()
    if lower_name.endswith(".csv"):
        parsed = parse_csv_content(content)
    elif lower_name.endswith(".geojson") or lower_name.endswith(".json"):
        parsed = parse_geojson_content(content)
    else:
        raise ValueError("Unsupported file type. Upload CSV or GeoJSON.")

    return {
        "filename": filename,
        "validated": False,
        "cleaned": False,
        "dropped_row_count": 0,
        **parsed,
    }


def export_columns(
    column_mappings: dict[str, str | None] | None,
    validate_columns: list[str] | None,
) -> list[str]:
    column_mappings = column_mappings or {}
    validate_columns = validate_columns or []
    mapped_columns = [source for source in column_mappings.values() if source]
    return sorted(set(validate_columns + mapped_columns))


def count_incomplete_rows(dataset: dict[str, Any], validate_columns: list[str]) -> int:
    if not validate_columns:
        return 0
    return sum(
        1
        for row in dataset.get("rows", [])
        if not _row_has_complete_columns(row, validate_columns)
    )


def drop_incomplete_rows(
    dataset: dict[str, Any],
    validate_columns: list[str],
    sources: RuleSources = (),
) -> dict[str, Any]:
    """Drop rows with a blank in any validate column or a value GloBI would reject."""
    rows = dataset.get("rows", [])
    keep_indices = [
        index
        for index, row in enumerate(rows)
        if _row_has_complete_columns(row, validate_columns) and not _row_breaks_rules(row, sources)
    ]
    kept_rows = [rows[index] for index in keep_indices]
    dropped_row_count = len(rows) - len(kept_rows)

    cleaned = {
        **dataset,
        "rows": kept_rows,
        "row_count": len(kept_rows),
        "columns": _summarize_columns(kept_rows),
        "dropped_row_count": dataset.get("dropped_row_count", 0) + dropped_row_count,
        "cleaned": True,
        "output_columns": export_columns(
            dataset.get("column_mappings", {}),
            validate_columns,
        ),
    }

    if dataset.get("source_format") == "geojson":
        features = dataset.get("features", [])
        kept_features = [features[index] for index in keep_indices]
        cleaned["features"] = kept_features
        cleaned["geojson"] = {
            "type": "FeatureCollection",
            "features": kept_features,
        }

    if dataset.get("source_format") == "csv":
        cleaned["csv_fieldnames"] = export_columns(
            dataset.get("column_mappings", {}),
            validate_columns,
        ) or dataset.get("csv_fieldnames", [])

    return cleaned


def build_cleaned_geojson(dataset: dict[str, Any]) -> dict[str, Any]:
    output_columns = dataset.get("output_columns") or export_columns(
        dataset.get("column_mappings", {}),
        dataset.get("validated_columns", []),
    )
    features = []

    for feature in dataset.get("features", []):
        properties = dict(feature.get("properties") or {})
        filtered_properties = (
            {column: properties.get(column) for column in output_columns if column in properties}
            if output_columns
            else properties
        )
        features.append(
            {
                "type": "Feature",
                "geometry": feature.get("geometry"),
                "properties": filtered_properties,
            }
        )

    return {"type": "FeatureCollection", "features": features}


def build_cleaned_csv(dataset: dict[str, Any]) -> str:
    output_columns = dataset.get("output_columns") or export_columns(
        dataset.get("column_mappings", {}),
        dataset.get("validated_columns", []),
    )
    if not output_columns and dataset.get("rows"):
        output_columns = list(dataset["rows"][0].keys())

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=output_columns, extrasaction="ignore")
    writer.writeheader()
    for row in dataset.get("rows", []):
        writer.writerow({column: row.get(column, "") for column in output_columns})

    return buffer.getvalue()


def validate_dataset(
    dataset: dict[str, Any],
    column_mappings: dict[str, str | None] | None = None,
    validate_columns: list[str] | None = None,
    roles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from services.globi_columns import GLOBI_COLUMN_ROLES

    column_mappings = column_mappings or {}
    validate_columns = validate_columns or []
    roles = roles or GLOBI_COLUMN_ROLES

    columns_by_name = {column["name"]: column for column in dataset.get("columns", [])}
    issues: list[str] = []
    missing_columns: list[str] = []

    if dataset.get("row_count", 0) == 0:
        issues.append("Dataset contains no rows.")

    role_by_key = {role["key"]: role for role in roles}

    for role in roles:
        if not role.get("required"):
            continue
        source = column_mappings.get(role["key"])
        if not source:
            issues.append(f"Map required GloBI column: {role['label']}.")

    for role_key, source in column_mappings.items():
        if not source:
            continue
        if source not in columns_by_name:
            missing_columns.append(source)
            label = role_by_key.get(role_key, {}).get("label", role_key)
            issues.append(f"Mapped column '{source}' for {label} was not found in the dataset.")

    height_or_floors_roles = [role for role in roles if role.get("required_group") == "height_or_floors"]
    if height_or_floors_roles:
        has_height_or_floors = any(column_mappings.get(role["key"]) for role in height_or_floors_roles)
        if not has_height_or_floors:
            labels = " or ".join(role["label"] for role in height_or_floors_roles)
            issues.append(f"Map at least one of: {labels}.")

    for column_name in validate_columns:
        column = columns_by_name.get(column_name)
        if column is None:
            missing_columns.append(column_name)
            issues.append(f"Validation column '{column_name}' was not found in the dataset.")
        elif column.get("null_count", 0) > 0:
            issues.append(f"Column '{column_name}' contains missing values.")

    from services.globi_columns import breaks_rule

    sources = rule_sources(column_mappings, roles)
    for source, role in sources:
        if source not in columns_by_name:
            continue
        bad = [
            str(row.get(source))
            for row in dataset.get("rows", [])
            if not _is_missing(row.get(source)) and breaks_rule(row.get(source), role)
        ]
        if bad:
            examples = ", ".join(sorted(set(bad))[:5])
            issues.append(
                f"{role['label']}: {len(bad)} rows have values GloBI will drop ({examples}). {role['rule']}"
            )
    invalid_row_count = sum(1 for row in dataset.get("rows", []) if _row_breaks_rules(row, sources))

    incomplete_row_count = count_incomplete_rows(dataset, validate_columns)

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "missing_columns": sorted(set(missing_columns)),
        "column_mappings": column_mappings,
        "validated_columns": validate_columns,
        "incomplete_row_count": incomplete_row_count,
        "invalid_row_count": invalid_row_count,
    }
