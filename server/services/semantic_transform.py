"""Apply deterministic semantic field transformations to GIS rows."""

from typing import Any


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return text.lower() in {"", "none", "null", "nan"}


def _parse_numeric(value: Any) -> float | None:
    if _is_missing(value):
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def apply_numeric_range(value: Any, ranges: list[dict[str, Any]] | None) -> str | None:
    numeric_value = _parse_numeric(value)
    if numeric_value is None:
        return None

    for range_mapping in ranges or []:
        minimum = float(range_mapping.get("min", float("-inf")))
        maximum = float(range_mapping.get("max", float("inf")))
        if minimum <= numeric_value <= maximum:
            return str(range_mapping.get("label"))

    return None


def apply_categorical_mapping(
    value: Any,
    options: list[str],
    groups: list[dict[str, Any]] | None = None,
) -> str | None:
    if _is_missing(value):
        return None

    text = str(value).strip()
    for group in groups or []:
        source_values = [str(source).strip() for source in group.get("source_values", [])]
        if text in source_values:
            label = group.get("group_label")
            return str(label) if label is not None else None

    if text in options:
        return text

    return None


def apply_field_to_row(row: dict[str, Any], field: dict[str, Any]) -> str | None:
    if field.get("type") != "deterministic":
        return None

    rule = field.get("transformation_rule") or {}
    source_column = rule.get("source_column")
    if not source_column:
        return None

    source_value = row.get(source_column)
    rule_type = rule.get("type")
    options = field.get("options") or []

    if rule_type == "numeric_range":
        return apply_numeric_range(source_value, rule.get("numeric_ranges"))
    if rule_type == "categorical_mapping":
        return apply_categorical_mapping(
            source_value,
            options,
            rule.get("categorical_groups"),
        )

    return None


def apply_semantic_fields_to_rows(
    rows: list[dict[str, Any]], fields: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    enriched_rows: list[dict[str, Any]] = []

    for row in rows:
        enriched = dict(row)
        for field in fields:
            if field.get("type") != "deterministic":
                continue
            enriched[field["name"]] = apply_field_to_row(row, field)
        enriched_rows.append(enriched)

    return enriched_rows


def field_coverage_stats(rows: list[dict[str, Any]], field: dict[str, Any]) -> dict[str, Any]:
    total_count = len(rows)
    mapped_count = sum(1 for row in rows if apply_field_to_row(row, field) is not None)
    unmapped_count = total_count - mapped_count
    coverage_percent = round((mapped_count / total_count) * 100, 1) if total_count else 0.0

    return {
        "mapped_count": mapped_count,
        "unmapped_count": unmapped_count,
        "total_count": total_count,
        "coverage_percent": coverage_percent,
    }


def preview_semantic_fields(
    rows: list[dict[str, Any]], fields: list[dict[str, Any]], sample_limit: int = 25
) -> dict[str, Any]:
    sample_rows = rows[:sample_limit]
    field_previews: list[dict[str, Any]] = []

    for field in fields:
        if field.get("type") != "deterministic":
            continue

        rule = field.get("transformation_rule") or {}
        source_column = rule.get("source_column", "")
        samples = [
            {
                "source_value": row.get(source_column),
                "semantic_value": apply_field_to_row(row, field),
            }
            for row in sample_rows
        ]
        field_previews.append(
            {
                "field_name": field.get("name"),
                "source_column": source_column,
                "rule_type": rule.get("type"),
                "samples": samples,
                "stats": field_coverage_stats(rows, field),
            }
        )

    return {
        "field_previews": field_previews,
        "sample_rows": apply_semantic_fields_to_rows(sample_rows, fields),
    }


def build_enriched_properties(
    row: dict[str, Any],
    fields: list[dict[str, Any]],
    core_columns: list[str],
) -> dict[str, Any]:
    enriched = apply_semantic_fields_to_rows([row], fields)[0]
    properties: dict[str, Any] = {}

    for column in core_columns:
        if column in enriched:
            properties[column] = enriched[column]

    for field in fields:
        if field.get("type") == "deterministic":
            properties[field["name"]] = enriched.get(field["name"])

    return properties
