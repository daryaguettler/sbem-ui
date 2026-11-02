"""Trace one building through the model: what its data says, what gets estimated, and
which library records it ends up with.

Estimated characteristics are drawn `n` times with this building as the only context,
so the spread you see is the model's uncertainty about this one building rather than
variation across the stock.
"""

from __future__ import annotations

import random
from collections import Counter
from typing import Any

import pandas as pd
from semantic_priors import new_generator
from semantic_priors.compose.compound_key import COMPOUND_PREFIX
from semantic_priors.engine.samplers import SamplingError

from services.component_map import _collect_selectors
from services.prior_trees import PriorTreeError, _clean, parse_config
from services.semantic_transform import apply_field_to_row


class InspectError(Exception):
    """Raised when a building can't be traced (unknown id, missing context)."""


def _find_row(rows: list[dict[str, Any]], id_column: str, building_id: str | None) -> dict[str, Any]:
    if not rows:
        raise InspectError("There is no GIS data to inspect yet.")
    if building_id is None:
        return random.choice(rows)
    for row in rows:
        if _clean(row.get(id_column)) == str(building_id).strip():
            return row
    raise InspectError(f"No building with {id_column} = '{building_id}' in the GIS data.")


def _rule_explanation(field: dict[str, Any], raw: Any, value: str | None) -> str:
    """Which part of the rule produced the value, in words."""
    rule = field.get("transformation_rule") or {}
    column = rule.get("source_column")
    if _clean(raw) is None:
        return f"{column} is empty"
    if value is None:
        return f"{column} = {raw}, which no range or mapping covers"
    if rule.get("type") == "numeric_range":
        matched = next((r for r in rule.get("numeric_ranges") or [] if str(r.get("label")) == value), None)
        if matched:
            return f"{column} = {raw}, in {matched.get('min')}–{matched.get('max')}"
    return f"{column} = {raw}"


def _known_values(row: dict[str, Any], fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    known = []
    for field in fields:
        if field.get("type") != "deterministic":
            continue
        raw = row.get((field.get("transformation_rule") or {}).get("source_column") or "")
        value = apply_field_to_row(row, field)
        known.append({"name": field["name"], "value": value, "because": _rule_explanation(field, raw, value)})
    return known


def _draws(
    config: dict[str, Any], context: dict[str, Any], n: int, seed: int | None
) -> tuple[list[dict[str, Any]], list[str]]:
    """`n` draws for one building, and the estimated features in them (none without priors)."""
    if not config or not (config.get("priors") or config.get("joints")):
        return [{} for _ in range(n)], []
    try:
        priors = parse_config(config).to_priors()
    except PriorTreeError as exc:
        raise InspectError(str(exc)) from exc
    if not priors.sampled_features:
        return [{} for _ in range(n)], []

    context_fields = sorted(priors.depends_on - set(priors.sampled_features))
    missing = [name for name in context_fields if _clean(context.get(name)) is None]
    if missing:
        raise InspectError(
            "The estimates depend on " + ", ".join(f"'{name}'" for name in missing) + ", which this building has no value for."
        )
    frame = pd.DataFrame([{name: _clean(context.get(name)) for name in context_fields}] * n)
    try:
        sampled = priors.sample(frame, n, new_generator(seed))
    except (SamplingError, ValueError, KeyError) as exc:
        raise InspectError(str(exc)) from exc
    names = [name for name in priors.sampled_features if not name.startswith(f"{COMPOUND_PREFIX}.")]
    return sampled[names].to_dict("records"), names


def _shares(values: list[Any]) -> list[dict[str, Any]]:
    counts = Counter(values)
    total = sum(counts.values()) or 1
    return [{"value": value, "share": count / total} for value, count in counts.most_common()]


def inspect_building(
    rows: list[dict[str, Any]],
    id_column: str,
    building_id: str | None,
    fields: list[dict[str, Any]],
    config: dict[str, Any],
    component_map: dict[str, Any] | None,
    n: int = 500,
    seed: int | None = 0,
) -> dict[str, Any]:
    """Known values, estimated values as shares over `n` draws, and each model part's
    record names as shares over the same draws. Record existence is checked by the caller.
    With no `building_id`, a random building is picked."""
    n = max(1, min(int(n), 5000))
    row = _find_row(rows, id_column, building_id)
    known = _known_values(row, fields)
    context = {**row, **{entry["name"]: entry["value"] for entry in known if entry["value"] is not None}}
    sampled, estimated_names = _draws(config, context, n, seed)
    estimated = [
        {"name": name, "shares": _shares([_clean(draw.get(name)) for draw in sampled])} for name in estimated_names
    ]

    draws = [{**context, **draw} for draw in sampled]
    parts = []
    for selector in _collect_selectors(component_map or {}):
        names = []
        for draw in draws:
            values = [_clean(draw.get(name)) for name in selector["source_fields"]]
            if any(value is None for value in values):
                names.append(None)
                continue
            names.append("_".join([*values, *([selector["suffix"]] if selector.get("suffix") else [])]))
        parts.append(
            {
                "path": selector["path"],
                "sourceFields": selector["source_fields"],
                "records": [
                    {"name": entry["value"], "share": entry["share"]} for entry in _shares(names)
                ],
            }
        )

    return {"buildingId": _clean(row.get(id_column)), "n": n, "known": known, "estimated": estimated, "parts": parts}
