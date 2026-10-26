"""Draft a semantic field from a plain-language description, then check it.

The model only proposes; nothing is applied. Every draft goes back through the same
validator and preview the editor uses, plus data checks the editor doesn't run yet
(range overlaps, values that no rule covers, labels that aren't options), so the user
reviews a draft that has already been tested against their GIS data.

Only column names, types and sampled distinct values leave the machine, never whole
rows.
"""

from __future__ import annotations

import json
import os
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Literal

import anthropic
from pydantic import BaseModel, Field

from services.semantic_fields import validate_semantic_field
from services.semantic_transform import (
    _is_missing,
    _parse_numeric,
    apply_field_to_row,
    field_coverage_stats,
)

MODEL = "claude-opus-5-5"
# Route a safety-classifier decline to Anthropic's recommended fallback model instead
# of failing the request.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_VALUES_PER_COLUMN = 80
MAX_UNMAPPED_EXAMPLES = 8


class AssistUnavailable(RuntimeError):
    """No Anthropic credentials are configured on this machine."""


class AssistFailed(RuntimeError):
    """The model call failed or returned something unusable."""


# --------------------------------------------------------------------------- #
# What the model fills in. Deliberately flatter than SemanticField (no ids, no
# nested rule object) so the schema is easy to follow; converted below.
# --------------------------------------------------------------------------- #


class DraftRange(BaseModel):
    label: str = Field(description="One of the field's options.")
    min: float = Field(description="Inclusive lower bound.")
    max: float = Field(description="Inclusive upper bound.")


class DraftGroup(BaseModel):
    group_label: str = Field(description="One of the field's options.")
    source_values: list[str] = Field(
        description="Exact values from the GIS column that map to this option."
    )


class DraftField(BaseModel):
    name: str
    type: Literal["deterministic", "stochastic"]
    options: list[str]
    description: str
    source_column: str | None = Field(
        description="GIS column the rule reads. Null for stochastic fields."
    )
    rule_type: Literal["numeric_range", "categorical_mapping"] | None = Field(
        description="Null for stochastic fields."
    )
    numeric_ranges: list[DraftRange] = Field(
        description="Only for numeric_range rules; otherwise empty."
    )
    categorical_groups: list[DraftGroup] = Field(
        description="Only for categorical_mapping rules; otherwise empty."
    )


class AssistDraft(BaseModel):
    field: DraftField
    assumptions: list[str] = Field(
        description="Each choice you made that the description didn't state outright."
    )
    questions: list[str] = Field(
        description="Ambiguities the user should resolve. Empty if none."
    )


SYSTEM_PROMPT = """\
You help building-energy modelers define a "semantic field": a building category used by \
an urban building-stock energy model (for example construction age band, typology, or \
heating system). You turn the user's plain-language description into one field \
definition, using the GIS data summary you are given.

A field is one of two types:
- "deterministic": computed for every building from one GIS column by a rule.
  - "numeric_range": each option covers an inclusive [min, max] range of the column. \
Ranges are checked in order and the first match wins. Cover the column's full observed \
range without overlaps; for whole-number columns such as years, make bounds meet \
without sharing a value (e.g. 0-1974, 1975-2003, 2004-2100).
  - "categorical_mapping": each option lists the exact column values (case and spacing \
as shown) that map to it. Assign every observed value you can reasonably classify.
- "stochastic": the GIS data does not record it, so it is sampled later from \
probabilities the user sets elsewhere. It has no source column and no rule.

Rules:
- Use only columns and values that appear in the GIS summary. Never invent them.
- Options are short identifiers without spaces (e.g. "pre_1975", "SFH"); follow the \
naming style of the project's existing fields when there are any.
- Every range label and group label must be one of the options.
- If the user's description doesn't match the data (e.g. a column they name doesn't \
exist), choose the closest sensible column and say so in assumptions.
- Record every guess in "assumptions", and put real ambiguities in "questions" instead \
of silently picking one.
- When you are given a previous draft and a requested change, return the full updated \
field, keeping everything the user didn't ask to change."""


def credentials_available() -> bool:
    """Whether the SDK can find credentials (env vars or an `ant auth login` profile)."""
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    if os.environ.get("ANTHROPIC_PROFILE"):
        return True
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return (config_home / "anthropic").is_dir()


# --------------------------------------------------------------------------- #
# Context
# --------------------------------------------------------------------------- #


def summarize_gis(dataset: dict[str, Any]) -> dict[str, Any]:
    """Column-level summary of the GIS data: names, types and capped value lists."""
    rows: list[dict[str, Any]] = dataset.get("rows", [])
    columns = []
    for column in dataset.get("columns", []):
        name = column["name"]
        values = [row.get(name) for row in rows if not _is_missing(row.get(name))]
        entry: dict[str, Any] = {
            "name": name,
            "type": column.get("data_type", "string"),
            "non_empty_rows": len(values),
        }
        numbers = [n for n in (_parse_numeric(v) for v in values) if n is not None]
        if column.get("data_type") == "numeric" and numbers:
            numbers.sort()
            entry["min"] = numbers[0]
            entry["max"] = numbers[-1]
            entry["median"] = numbers[len(numbers) // 2]
            entry["all_whole_numbers"] = all(float(n).is_integer() for n in numbers)
        else:
            counts = Counter(str(v).strip() for v in values)
            entry["distinct_values"] = len(counts)
            entry["values_by_frequency"] = [
                [value, count]
                for value, count in counts.most_common(MAX_VALUES_PER_COLUMN)
            ]
        columns.append(entry)
    return {"row_count": len(rows), "columns": columns}


def _user_message(
    description: str,
    existing_fields: list[dict[str, Any]],
    previous: dict[str, Any] | None,
    field_name: str | None,
) -> str:
    parts = []
    if existing_fields:
        parts.append(
            "Existing fields in this project (for naming style; don't duplicate them):\n"
            + json.dumps(
                [
                    {"name": f.get("name"), "options": f.get("options", [])}
                    for f in existing_fields
                ]
            )
        )
    if field_name:
        parts.append(f"The field should be named: {field_name}")
    if previous:
        parts.append("Previous draft:\n" + json.dumps(previous))
        parts.append(f"Requested change:\n{description}")
    else:
        parts.append(f"Description:\n{description}")
    return "\n\n".join(parts)


def request_draft(
    description: str,
    gis_summary: dict[str, Any],
    existing_fields: list[dict[str, Any]],
    previous: dict[str, Any] | None = None,
    field_name: str | None = None,
    client: anthropic.Anthropic | None = None,
) -> AssistDraft:
    """Ask Claude for a draft. Raises AssistUnavailable / AssistFailed."""
    if client is None:
        if not credentials_available():
            raise AssistUnavailable("Set ANTHROPIC_API_KEY to enable AI drafting.")
        client = anthropic.Anthropic()

    try:
        response = client.beta.messages.parse(
            model=MODEL,
            max_tokens=16000,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            output_config={"effort": "low"},
            # Instructions, then the GIS summary: both stable while a user iterates on
            # one field, so they sit before the cache breakpoint.
            system=[
                {"type": "text", "text": SYSTEM_PROMPT},
                {
                    "type": "text",
                    "text": "GIS data summary:\n" + json.dumps(gis_summary),
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            messages=[
                {
                    "role": "user",
                    "content": _user_message(
                        description, existing_fields, previous, field_name
                    ),
                }
            ],
            output_format=AssistDraft,
        )
    except anthropic.AuthenticationError as err:
        raise AssistUnavailable("The Anthropic API key was rejected.") from err
    except anthropic.RateLimitError as err:
        raise AssistFailed(
            "Rate limited by the Anthropic API. Try again shortly."
        ) from err
    except anthropic.APIStatusError as err:
        raise AssistFailed(
            f"Anthropic API error ({err.status_code}): {err.message}"
        ) from err
    except anthropic.APIConnectionError as err:
        raise AssistFailed(
            "Couldn't reach the Anthropic API. Check your connection."
        ) from err

    if response.stop_reason == "refusal":
        raise AssistFailed(
            "The model declined this request. Try rephrasing the description."
        )
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise AssistFailed(
            "The model's answer was incomplete. Try a shorter description."
        )
    return response.parsed_output


# --------------------------------------------------------------------------- #
# Conversion + checks
# --------------------------------------------------------------------------- #


def draft_to_semantic_field(
    draft: DraftField, field_id: str | None = None
) -> dict[str, Any]:
    """The draft in the API's SemanticField shape (snake_case, as the editor sends it)."""
    deterministic = draft.type == "deterministic"
    rule = None
    if deterministic and draft.rule_type:
        rule = {
            "id": str(uuid.uuid4()),
            "type": draft.rule_type,
            "source_column": draft.source_column or "",
            "target_field": draft.name,
            "numeric_ranges": [r.model_dump() for r in draft.numeric_ranges]
            if draft.rule_type == "numeric_range"
            else None,
            "categorical_groups": [g.model_dump() for g in draft.categorical_groups]
            if draft.rule_type == "categorical_mapping"
            else None,
            "compound_logic": None,
        }
    return {
        "id": field_id or str(uuid.uuid4()),
        "name": draft.name,
        "type": draft.type,
        "data_type": "numeric" if draft.rule_type == "numeric_range" else "categorical",
        "options": list(draft.options),
        "description": draft.description,
        "transformation_rule": rule,
        "requires_prior": not deterministic,
        "prior_id": None,
    }


def check_field(
    field: dict[str, Any], rows: list[dict[str, Any]], gis_columns: list[str]
) -> dict[str, Any]:
    """Validator errors plus data-grounded warnings and coverage for one field."""
    errors = validate_semantic_field(field, gis_columns)
    warnings: list[str] = []
    rule = field.get("transformation_rule") or {}
    source = rule.get("source_column")

    if field.get("type") != "deterministic" or not source:
        return {"errors": errors, "warnings": warnings, "coverage": None}

    values = [row.get(source) for row in rows]

    if rule.get("type") == "numeric_range":
        ranges = rule.get("numeric_ranges") or []
        overlapping: Counter[str] = Counter()
        for value in values:
            number = _parse_numeric(value)
            if number is None:
                continue
            hits = [r["label"] for r in ranges if r["min"] <= number <= r["max"]]
            if len(hits) > 1:
                overlapping[" / ".join(hits)] += 1
        for pair, count in overlapping.most_common(3):
            warnings.append(
                f"{count} buildings fall in more than one range ({pair}); the first one wins."
            )

    if rule.get("type") == "categorical_mapping":
        observed = {str(v).strip() for v in values if not _is_missing(v)}
        for group in rule.get("categorical_groups") or []:
            missing = [v for v in group["source_values"] if v not in observed]
            if missing:
                warnings.append(
                    f"Not found in {source}: {', '.join(missing[:5])}"
                    + (f" (+{len(missing) - 5} more)" if len(missing) > 5 else "")
                )

    unmapped: Counter[str] = Counter(
        str(row.get(source)).strip()
        for row in rows
        if not _is_missing(row.get(source)) and apply_field_to_row(row, field) is None
    )
    stats = field_coverage_stats(rows, field)
    if unmapped:
        examples = ", ".join(
            f"{v} ({n})" for v, n in unmapped.most_common(MAX_UNMAPPED_EXAMPLES)
        )
        warnings.append(
            f"{sum(unmapped.values())} buildings with a value aren't covered: {examples}"
        )

    return {
        "errors": errors,
        "warnings": warnings,
        "coverage": {
            "mapped_percent": stats["coverage_percent"],
            "unmapped_count": stats["unmapped_count"],
            "total_count": stats["total_count"],
        },
    }
