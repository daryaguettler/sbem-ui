"""Prior tree generation, validation, and sampling.

The document this produces is a `semantic_priors.RegionConfig` -- the same
`registry:`/`priors:`/`joints:`/`scenarios:` YAML the sampling engine loads -- so
everything here validates against the real Pydantic models rather than a
hand-rolled schema check.

The generator's job is to turn "condition `Heating` on `Typology` and
`Age_bracket`" into the full `JointDistribution` those models expect: a compound
lookup table with one row per combination of conditioning values. Which
combinations exist, and (in `empirical` mode) what the weights are, come from the
project's own GIS rows with deterministic semantic fields already applied.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

import networkx as nx
import numpy as np
import pandas as pd
from pydantic import ValidationError
from semantic_priors import RegionConfig, new_generator
from semantic_priors.compose.compound_key import COMPOUND_PREFIX, compound_key_name
from semantic_priors.engine import ConditionalPrior
from semantic_priors.engine.samplers import SamplingError
from semantic_priors.scenarios.scenario import KEEP as KEEP_TOKEN, FixedOverride

from services.semantic_transform import apply_semantic_fields_to_rows

DEFAULT_SEPARATOR = "."
# A conditioning field with more distinct values than this makes a lookup table
# nobody can author by hand; the UI warns rather than refuses.
MAX_CONDITION_CARDINALITY = 40
# Below this many observations a compound key's empirical weights are noise, so
# the key inherits the overall marginal instead.
DEFAULT_MIN_COUNT = 5


class PriorTreeError(Exception):
    """Raised when a prior tree can't be generated or sampled as requested."""


# -- shared helpers ----------------------------------------------------------


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip().lower() in {"", "none", "null", "nan"}


def _clean(value: Any) -> str | None:
    return None if _is_missing(value) else str(value).strip()


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    total = float(sum(weights.values()))
    if total <= 0:
        return {}
    return {value: weight / total for value, weight in weights.items()}


def enriched_rows(dataset: dict[str, Any] | None, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """GIS rows with every deterministic semantic field applied as a new column."""
    if not dataset:
        return []
    return apply_semantic_fields_to_rows(dataset.get("rows", []), fields)


# -- what the user can condition on ------------------------------------------


def conditioning_candidates(
    dataset: dict[str, Any] | None, fields: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Every field a prior may condition on, with its observed distribution.

    Three sources, all usable in the same compound key:

    * `semantic` -- a deterministic semantic field, observed per building once
      its transformation rule has been applied to the GIS rows.
    * `gis` -- a raw categorical GIS column the user never turned into a
      semantic field (region, county, tract, a code they already trust).
    * `sampled` -- a stochastic semantic field, which has no observed values but
      can still be conditioned on because its own prior runs first.

    Numeric columns are reported but not offered as conditions: a compound key is
    a string join, so a continuous column has to become buckets (a deterministic
    numeric-range semantic field) before it can index a lookup table.
    """
    rows = enriched_rows(dataset, fields)
    columns = {column["name"]: column for column in (dataset or {}).get("columns", [])}
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    for field in fields:
        name = field.get("name")
        if not name or name in seen:
            continue
        seen.add(name)
        stochastic = field.get("type") == "stochastic"
        source_column = (field.get("transformation_rule") or {}).get("source_column")
        options = list(field.get("options") or [])
        # A semantic field's dtype describes the values it *produces*, not the GIS
        # column it reads: an age-bracket field runs a numeric rule over a year and
        # produces era labels, so it indexes a lookup table like any other
        # categorical. Declaring discrete options is what makes a field
        # conditionable; a field without them is continuous and cannot key a table.
        candidates.append(
            {
                **_observed_summary(rows, name),
                "name": name,
                "source": "sampled" if stochastic else "semantic",
                "dtype": "categorical" if options else "numeric",
                "declaredValues": options,
                "description": field.get("description"),
                "sourceColumn": source_column,
                "conditionable": bool(options),
                "highCardinality": False,
            }
        )
        candidates[-1]["highCardinality"] = candidates[-1]["cardinality"] > MAX_CONDITION_CARDINALITY

    for name, column in columns.items():
        if name in seen:
            continue
        seen.add(name)
        dtype = "numeric" if column.get("data_type") == "numeric" else "categorical"
        summary = _observed_summary(rows, name)
        candidates.append(
            {
                **summary,
                "name": name,
                "source": "gis",
                "dtype": dtype,
                "declaredValues": summary["observedValues"] if dtype == "categorical" else [],
                "description": None,
                "sourceColumn": name,
                # A raw numeric column has to be bucketed into a semantic field first.
                "conditionable": dtype == "categorical",
                "highCardinality": summary["cardinality"] > MAX_CONDITION_CARDINALITY,
            }
        )

    return candidates


def _observed_summary(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
    """Value counts for one column across the enriched GIS rows."""
    total = len(rows)
    values = [_clean(row.get(name)) for row in rows]
    present = [value for value in values if value is not None]
    counts = Counter(present)
    numeric = [float(value) for value in present if _as_float(value) is not None]

    summary: dict[str, Any] = {
        "observedValues": [value for value, _ in counts.most_common()],
        "counts": dict(counts.most_common()),
        "rowCount": total,
        "presentCount": len(present),
        "coverage": round(len(present) / total, 4) if total else 0.0,
        "cardinality": len(counts),
        "numericSummary": None,
    }
    if numeric and len(numeric) == len(present):
        array = np.asarray(numeric, dtype=float)
        summary["numericSummary"] = {
            "mean": float(array.mean()),
            "std": float(array.std(ddof=1)) if len(array) > 1 else 0.0,
            "min": float(array.min()),
            "max": float(array.max()),
        }
    return summary


def _as_float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


# -- generating a prior ------------------------------------------------------


def generate_prior(
    *,
    target: str,
    target_values: list[str],
    condition_on: list[str],
    rows: list[dict[str, Any]],
    method: str = "uniform",
    observed_column: str | None = None,
    dtype: str = "categorical",
    min_count: int = DEFAULT_MIN_COUNT,
    separator: str = DEFAULT_SEPARATOR,
) -> dict[str, Any]:
    """Build one feature's prior, plus the evidence behind every weight.

    `method` is either `uniform` (an even starting point the user then edits) or
    `empirical` (weights counted from `observed_column`, which is whichever GIS
    column or semantic field already records the target for at least some
    buildings). A combination seen fewer than `min_count` times falls back to the
    overall marginal, and is flagged so the UI can say which rows are guesses.

    Returns the prior in the shape it takes inside a `RegionConfig`: either a
    `priors[target]` entry (no conditions) or a `joints[]` entry (conditioned),
    alongside the per-key counts used to draw it.
    """
    if not target:
        raise PriorTreeError("A prior needs a target field.")
    if method not in {"uniform", "empirical"}:
        raise PriorTreeError(f"Unknown generation method {method!r}; expected 'uniform' or 'empirical'.")
    if method == "empirical" and not observed_column:
        raise PriorTreeError(
            f"Estimating '{target}' from data needs an observed column holding its values."
        )

    warnings: list[str] = []

    if dtype == "numeric":
        return _generate_numeric_prior(
            target=target,
            condition_on=condition_on,
            rows=rows,
            method=method,
            observed_column=observed_column,
            min_count=min_count,
            separator=separator,
            warnings=warnings,
        )

    if not target_values:
        raise PriorTreeError(f"Prior '{target}' needs at least one possible value.")

    marginal = _marginal_distribution(rows, observed_column, target_values, method, warnings)

    if not condition_on:
        return {
            "target": target,
            "mode": "unconditional",
            "prior": {
                "sampler": {
                    "values": list(marginal.keys()),
                    "weights": [round(weight, 4) for weight in marginal.values()],
                }
            },
            "priors": {
                target: {
                    "sampler": {
                        "values": list(marginal.keys()),
                        "weights": [round(weight, 4) for weight in marginal.values()],
                    }
                }
            },
            "joint": None,
            "keys": [
                {
                    "key": "__all__",
                    "count": _observed_count(rows, observed_column),
                    "estimated": method == "empirical",
                    "weights": {value: round(weight, 4) for value, weight in marginal.items()},
                }
            ],
            "fallback": None,
            "warnings": warnings,
        }

    return _generate_joint(
        target=target,
        target_values=target_values,
        condition_on=condition_on,
        rows=rows,
        method=method,
        observed_column=observed_column,
        marginal=marginal,
        min_count=min_count,
        separator=separator,
        warnings=warnings,
    )


def _marginal_distribution(
    rows: list[dict[str, Any]],
    observed_column: str | None,
    target_values: list[str],
    method: str,
    warnings: list[str],
) -> dict[str, float]:
    """The unconditional distribution: counted from data, or flat."""
    if method == "empirical" and observed_column:
        counts = Counter(
            value
            for value in (_clean(row.get(observed_column)) for row in rows)
            if value is not None
        )
        unexpected = sorted(set(counts) - set(target_values))
        if unexpected:
            warnings.append(
                f"Column '{observed_column}' contains values outside the field's "
                f"declared options: {', '.join(unexpected)}. They were dropped."
            )
        observed = {value: float(counts.get(value, 0)) for value in target_values}
        if sum(observed.values()) > 0:
            return _normalize(observed)
        warnings.append(
            f"No usable values found in '{observed_column}'; falling back to a uniform prior."
        )

    share = 1.0 / len(target_values)
    return {value: share for value in target_values}


def _observed_count(rows: list[dict[str, Any]], observed_column: str | None) -> int:
    if not observed_column:
        return 0
    return sum(1 for row in rows if _clean(row.get(observed_column)) is not None)


def _generate_joint(
    *,
    target: str,
    target_values: list[str],
    condition_on: list[str],
    rows: list[dict[str, Any]],
    method: str,
    observed_column: str | None,
    marginal: dict[str, float],
    min_count: int,
    separator: str,
    warnings: list[str],
) -> dict[str, Any]:
    """Build the compound lookup table, one row per observed combination."""
    observed_keys = _observed_compound_keys(rows, condition_on, separator)
    if not observed_keys:
        warnings.append(
            "None of the conditioning fields are populated in the GIS data, so the "
            "table has no rows yet. The fallback distribution covers every building."
        )

    per_key_counts: dict[str, Counter] = {}
    if method == "empirical" and observed_column:
        for row in rows:
            key = _compound_key_for_row(row, condition_on, separator)
            value = _clean(row.get(observed_column))
            if key is None or value is None or value not in target_values:
                continue
            per_key_counts.setdefault(key, Counter())[value] += 1

    table: dict[str, dict[str, float]] = {}
    keys: list[dict[str, Any]] = []
    thin_keys: list[str] = []

    for key, key_count in observed_keys.items():
        counts = per_key_counts.get(key, Counter())
        supporting = int(sum(counts.values()))
        estimated = method == "empirical" and supporting >= min_count
        if estimated:
            weights = _normalize({value: float(counts.get(value, 0)) for value in target_values})
        else:
            weights = dict(marginal)
            if method == "empirical":
                thin_keys.append(key)

        table[key] = {value: round(weight, 4) for value, weight in weights.items()}
        keys.append(
            {
                "key": key,
                "conditionValues": key.split(separator),
                "count": key_count,
                "supportingCount": supporting,
                "estimated": estimated,
                "weights": table[key],
            }
        )

    if thin_keys:
        warnings.append(
            f"{len(thin_keys)} of {len(observed_keys)} combinations had fewer than "
            f"{min_count} observations and use the overall distribution instead."
        )

    return {
        "target": target,
        "mode": "joint",
        "prior": None,
        "priors": {},
        "joint": {
            "target": target,
            "condition_on": list(condition_on),
            "table": table,
            "fallback": {value: round(weight, 4) for value, weight in marginal.items()},
            "separator": separator,
        },
        "keys": keys,
        "fallback": {value: round(weight, 4) for value, weight in marginal.items()},
        "compoundKey": compound_key_name(list(condition_on), separator=separator),
        "warnings": warnings,
    }


def _fit_normal(values: list[float]) -> dict[str, Any]:
    """A clipped normal fitted to observed values, clipped to the observed range.

    A zero standard deviation (every observation identical) would make the sampler
    emit one constant, so it is floored to something tiny but positive.
    """
    array = np.asarray(values, dtype=float)
    std = float(array.std(ddof=1)) if len(array) > 1 else 0.0
    return {
        "mean": round(float(array.mean()), 4),
        "std": round(max(std, 1e-6), 4),
        "clip_min": round(float(array.min()), 4),
        "clip_max": round(float(array.max()), 4),
    }


PLACEHOLDER_NORMAL = {"mean": 0.0, "std": 1.0, "clip_min": None, "clip_max": None}


def _numeric_values(rows: list[dict[str, Any]], column: str | None) -> list[float]:
    if not column:
        return []
    values = (_as_float(row.get(column)) for row in rows if _clean(row.get(column)) is not None)
    return [value for value in values if value is not None]


def _generate_numeric_prior(
    *,
    target: str,
    condition_on: list[str],
    rows: list[dict[str, Any]],
    method: str,
    observed_column: str | None,
    min_count: int,
    separator: str,
    warnings: list[str],
) -> dict[str, Any]:
    """A numeric target gets a clipped normal, fitted to the column when asked.

    Conditioning a numeric field means a separate normal per combination, which
    can't go in `joints` -- that model compiles to categorical samplers. It is
    emitted as two `priors` entries instead: the compound key, and a
    `ConditionalPrior` dispatching on it. The sampling engine treats that exactly
    like a joint, and the dependency graph comes out the same shape.
    """
    overall = _numeric_values(rows, observed_column)
    fitted = method == "empirical" and len(overall) > 1
    if method == "empirical" and not fitted:
        warnings.append(
            f"Not enough numeric observations in '{observed_column}' to fit a "
            "distribution; using a placeholder you can edit."
        )
    baseline = _fit_normal(overall) if fitted else dict(PLACEHOLDER_NORMAL)

    if not condition_on:
        return {
            "target": target,
            "mode": "unconditional",
            "prior": {"sampler": baseline},
            "priors": {target: {"sampler": baseline}},
            "joint": None,
            "keys": [],
            "fallback": None,
            "warnings": warnings,
        }

    key_name = compound_key_name(list(condition_on), separator=separator)
    observed_keys = _observed_compound_keys(rows, condition_on, separator)
    if not observed_keys:
        warnings.append(
            "None of the conditioning fields are populated in the GIS data, so there "
            "are no combinations to fit. The fallback distribution covers every building."
        )

    # Group the observed values by combination, so each one can be fitted on its own.
    per_key: dict[str, list[float]] = {}
    if fitted:
        for row in rows:
            key = _compound_key_for_row(row, condition_on, separator)
            value = _as_float(row.get(observed_column))
            if key is None or value is None or _clean(row.get(observed_column)) is None:
                continue
            per_key.setdefault(key, []).append(value)

    conditions: list[dict[str, Any]] = []
    keys: list[dict[str, Any]] = []
    thin_keys: list[str] = []

    for key, key_count in observed_keys.items():
        values = per_key.get(key, [])
        estimated = fitted and len(values) >= max(min_count, 2)
        sampler = _fit_normal(values) if estimated else dict(baseline)
        if fitted and not estimated:
            thin_keys.append(key)

        conditions.append({"match_val": key, "sampler": sampler})
        keys.append(
            {
                "key": key,
                "conditionValues": key.split(separator),
                "count": key_count,
                "supportingCount": len(values),
                "estimated": estimated,
                "weights": {},
                "numeric": sampler,
            }
        )

    if thin_keys:
        warnings.append(
            f"{len(thin_keys)} of {len(observed_keys)} combinations had fewer than "
            f"{max(min_count, 2)} observations and use the overall distribution instead."
        )

    return {
        "target": target,
        "mode": "conditional",
        "prior": None,
        # Both entries are needed: the target's prior dispatches on the compound key,
        # so the key has to be sampled first.
        "priors": {
            key_name: {
                "sampler": {
                    "features_to_concatenate": list(condition_on),
                    "separator": separator,
                }
            },
            target: {
                "source_feature": key_name,
                "conditions": conditions,
                "fallback_prior": baseline,
            },
        },
        "joint": None,
        "keys": keys,
        "fallback": None,
        "fallbackNumeric": baseline,
        "compoundKey": key_name,
        "warnings": warnings,
    }


def _compound_key_for_row(
    row: dict[str, Any], condition_on: list[str], separator: str
) -> str | None:
    parts = [_clean(row.get(field)) for field in condition_on]
    if any(part is None for part in parts):
        return None
    return separator.join(parts)  # type: ignore[arg-type]


def _observed_compound_keys(
    rows: list[dict[str, Any]], condition_on: list[str], separator: str
) -> dict[str, int]:
    """Combinations that actually occur in the stock, most common first.

    Only observed combinations become table rows: the cross-product of every
    declared value would produce thousands of keys the user's buildings never
    hit, and the joint's fallback already covers anything unseen.
    """
    counts: Counter = Counter()
    for row in rows:
        key = _compound_key_for_row(row, condition_on, separator)
        if key is not None:
            counts[key] += 1
    return dict(counts.most_common())


def condition_preview(
    rows: list[dict[str, Any]], condition_on: list[str], separator: str = DEFAULT_SEPARATOR
) -> dict[str, Any]:
    """How many table rows a choice of conditioning fields would produce."""
    keys = _observed_compound_keys(rows, condition_on, separator)
    covered = sum(keys.values())
    return {
        "compoundKey": compound_key_name(list(condition_on), separator=separator) if condition_on else None,
        "keys": [{"key": key, "count": count} for key, count in keys.items()],
        "keyCount": len(keys),
        "coveredRows": covered,
        "rowCount": len(rows),
        "coverage": round(covered / len(rows), 4) if rows else 0.0,
    }


# -- assembling and validating the config ------------------------------------


def parse_config(config: dict[str, Any]) -> RegionConfig:
    """Parse a config through the real models, re-raising errors readably."""
    try:
        return RegionConfig.from_dict(config or {})
    except ValidationError as exc:
        raise PriorTreeError(_format_validation_error(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise PriorTreeError(str(exc)) from exc


def _format_validation_error(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors()[:8]:
        location = ".".join(str(item) for item in error["loc"]) or "config"
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts)


def validate_prior_tree(
    config: dict[str, Any], required_targets: list[str] | None = None
) -> dict[str, Any]:
    """Validate a config against the sampling engine plus the project's own needs.

    Structural errors come from the Pydantic models themselves, so anything that
    validates here is something `RegionConfig.load` will accept at run time. On
    top of that: every stochastic semantic field needs a prior, and every field a
    prior conditions on has to be declared in the registry.
    """
    required_targets = required_targets or []
    errors: list[str] = []
    warnings: list[str] = []

    try:
        parsed = parse_config(config)
    except PriorTreeError as exc:
        return {
            "valid": False,
            "errors": [str(exc)],
            "warnings": [],
            "registryFields": [],
            "priorTargets": [],
            "sampledFeatures": [],
            "dependencies": {"nodes": [], "edges": []},
        }

    try:
        priors = parsed.to_priors()
    except (ValidationError, ValueError) as exc:
        return {
            "valid": False,
            "errors": [str(exc)],
            "warnings": [],
            "registryFields": parsed.registry.names,
            "priorTargets": sorted(parsed.priors),
            "sampledFeatures": [],
            "dependencies": {"nodes": [], "edges": []},
        }

    registry_fields = set(parsed.registry.names)
    declared = parsed.registry.by_name
    sampled = set(priors.sampled_features)
    # Compound keys live in `priors` too (a conditioned numeric prior needs one),
    # but they're generated machinery rather than fields the user authored.
    targets = {
        name for name in parsed.priors if not name.startswith(f"{COMPOUND_PREFIX}.")
    } | {joint.target for joint in parsed.joints}

    for target in required_targets:
        if target not in targets:
            errors.append(f"Stochastic field '{target}' has no prior yet.")

    for target in sorted(targets):
        if target not in registry_fields:
            warnings.append(f"Prior target '{target}' is not declared in the registry.")

    for joint in parsed.joints:
        for field_name in joint.condition_on:
            if field_name not in registry_fields:
                errors.append(
                    f"'{joint.target}' is conditioned on '{field_name}', which is not "
                    "declared in the registry."
                )
        field = declared.get(joint.target)
        if field is not None and field.dtype == "categorical":
            allowed = set(field.values)
            used = {
                value
                for distribution in joint.resolved_table().values()
                for value in distribution
            } | set(joint.fallback or {})
            unknown = sorted(used - allowed)
            if unknown:
                errors.append(
                    f"Prior '{joint.target}' assigns weight to undeclared values: "
                    f"{', '.join(unknown)}."
                )
        if not joint.fallback:
            warnings.append(
                f"'{joint.target}' has no fallback distribution, so a building whose "
                "combination is missing from the table will fail to sample."
            )

    # A dependency that is neither sampled nor observable has nowhere to come from.
    context_fields = sorted(priors.depends_on - sampled)
    for field_name in context_fields:
        if field_name not in registry_fields:
            errors.append(
                f"Priors depend on '{field_name}', which is neither sampled nor "
                "declared in the registry."
            )

    for field_name in sorted(registry_fields - sampled - set(context_fields)):
        warnings.append(f"Registry field '{field_name}' is unused by any prior.")

    scenario_errors, scenario_warnings = _validate_scenarios(parsed, priors)
    errors.extend(scenario_errors)
    warnings.extend(scenario_warnings)

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "scenarios": [scenario.name for scenario in parsed.scenarios],
        "registryFields": parsed.registry.names,
        "priorTargets": sorted(targets),
        "sampledFeatures": list(priors.sampled_features),
        "contextFields": context_fields,
        "dependencies": dependency_payload(config),
    }


def dependency_payload(config: dict[str, Any]) -> dict[str, Any]:
    """The prior tree itself: which feature is sampled from which.

    Nodes are laid out in sampling order and tagged by kind so the UI can draw
    context (comes from GIS), compound keys (the joins), and sampled features
    differently.
    """
    try:
        parsed = parse_config(config)
        priors = parsed.to_priors()
    except (PriorTreeError, ValidationError, ValueError):
        return {"nodes": [], "edges": []}

    sampled = priors.sampled_features
    joint_targets = {joint.target for joint in parsed.joints}
    graph = priors.dependency_graph
    nodes: list[dict[str, Any]] = []

    for name in graph.nodes:
        prior = sampled.get(name)
        if prior is None:
            kind = "context"
        elif name.startswith(f"{COMPOUND_PREFIX}."):
            kind = "compound"
        elif name in joint_targets or isinstance(prior, ConditionalPrior):
            kind = "conditional"
        else:
            kind = "unconditional"
        nodes.append(
            {
                "name": name,
                "kind": kind,
                "dependsOn": sorted(prior.depends_on) if prior is not None else [],
                "depth": _depth(graph, name),
            }
        )

    nodes.sort(key=lambda node: (node["depth"], node["name"]))
    return {
        "nodes": nodes,
        "edges": [{"from": source, "to": target} for source, target in graph.edges],
    }


def _depth(graph: Any, node: str) -> int:
    """Longest path from any root, so layered layouts don't cross backwards."""
    predecessors = list(graph.predecessors(node))
    if not predecessors:
        return 0
    seen: set[str] = set()

    def walk(current: str) -> int:
        if current in seen:
            return 0
        seen.add(current)
        parents = list(graph.predecessors(current))
        return 0 if not parents else 1 + max(walk(parent) for parent in parents)

    return walk(node)


# -- sampling ----------------------------------------------------------------


def sample_prior_tree(
    config: dict[str, Any],
    rows: list[dict[str, Any]],
    n: int = 1000,
    seed: int | None = 0,
) -> dict[str, Any]:
    """Draw `n` buildings from the config and summarize what came out.

    The context is drawn from the project's own GIS rows, so the preview answers
    "what does this prior produce over *my* stock" rather than over an imaginary
    uniform one. With no GIS data (or no observed conditioning fields), a single
    empty context row is broadcast instead, which works for unconditional priors.
    """
    parsed = parse_config(config)
    priors = parsed.to_priors()
    if not priors.sampled_features:
        raise PriorTreeError("There are no priors to sample yet.")

    n = max(1, min(int(n), 20000))
    generator = new_generator(seed)
    context_fields = sorted(priors.depends_on - set(priors.sampled_features))
    frame, usable_rows = _build_context_frame(rows, context_fields, n, generator)

    try:
        sampled = priors.sample(frame, n, generator)
    except (SamplingError, ValueError, KeyError) as exc:
        raise PriorTreeError(str(exc)) from exc

    features = [
        name
        for name in priors.sampled_features
        if not name.startswith(f"{COMPOUND_PREFIX}.")
    ]
    return {
        "n": n,
        "seed": seed,
        "contextFields": context_fields,
        "contextRowCount": usable_rows,
        "contextSource": "gis" if usable_rows else "synthetic",
        "distributions": [
            _summarize_feature(sampled, name, priors.sampled_features[name], context_fields)
            for name in features
        ],
        "sampleRows": _sample_rows(sampled, limit=25),
    }


def _build_context_frame(
    rows: list[dict[str, Any]],
    context_fields: list[str],
    n: int,
    generator: np.random.Generator,
) -> tuple[pd.DataFrame, int]:
    """`n` context rows drawn with replacement from buildings that have every field."""
    if not context_fields:
        return pd.DataFrame([{}] * n), 0

    usable = [
        {field: _clean(row.get(field)) for field in context_fields}
        for row in rows
        if all(_clean(row.get(field)) is not None for field in context_fields)
    ]
    if not usable:
        raise PriorTreeError(
            "Sampling needs values for "
            + ", ".join(f"'{field}'" for field in context_fields)
            + ", but no GIS row has all of them. Upload GIS data and define the "
            "deterministic semantic fields these priors condition on."
        )

    indices = generator.integers(0, len(usable), size=n)
    return pd.DataFrame([usable[int(index)] for index in indices]), len(usable)


def _summarize_feature(
    sampled: pd.DataFrame, name: str, prior: Any, context_fields: list[str]
) -> dict[str, Any]:
    """One feature's sampled marginal, plus its breakdown by conditioning field."""
    series = sampled[name]
    numeric = pd.to_numeric(series, errors="coerce")
    is_numeric = numeric.notna().all() and series.nunique() > 12

    summary: dict[str, Any] = {
        "feature": name,
        "kind": "conditional" if isinstance(prior, ConditionalPrior) else "unconditional",
        "dtype": "numeric" if is_numeric else "categorical",
        "dependsOn": sorted(prior.depends_on),
        "marginal": [],
        "histogram": None,
        "breakdown": None,
        "numericBreakdown": None,
    }

    if is_numeric:
        counts, edges = np.histogram(numeric.to_numpy(), bins=20)
        summary["histogram"] = {
            "bins": [
                {"start": float(edges[i]), "end": float(edges[i + 1]), "count": int(counts[i])}
                for i in range(len(counts))
            ],
            "mean": float(numeric.mean()),
            "std": float(numeric.std(ddof=1)) if len(numeric) > 1 else 0.0,
            "min": float(numeric.min()),
            "max": float(numeric.max()),
        }
        # A conditioned numeric prior's whole point is that the mean moves between
        # combinations, which a single histogram of everything hides.
        condition_field = _breakdown_field(prior, sampled, context_fields)
        if condition_field is not None:
            grouped = numeric.groupby(sampled[condition_field])
            summary["numericBreakdown"] = {
                "field": condition_field,
                "rows": [
                    {
                        "key": str(key),
                        "count": int(group.count()),
                        "mean": float(group.mean()),
                        "std": float(group.std(ddof=1)) if len(group) > 1 else 0.0,
                        "min": float(group.min()),
                        "max": float(group.max()),
                    }
                    for key, group in grouped
                ],
            }
        return summary

    shares = series.value_counts(normalize=True)
    summary["marginal"] = [
        {"value": str(value), "share": round(float(share), 6)}
        for value, share in shares.items()
    ]

    # Break the result down by whichever observed field(s) this prior conditions on,
    # which is what makes a joint's effect visible rather than just its average.
    condition_field = _breakdown_field(prior, sampled, context_fields)
    if condition_field is not None:
        crosstab = pd.crosstab(sampled[condition_field], series, normalize="index")
        summary["breakdown"] = {
            "field": condition_field,
            "values": [str(column) for column in crosstab.columns],
            "rows": [
                {
                    "key": str(index),
                    "count": int((sampled[condition_field] == index).sum()),
                    "shares": [round(float(value), 6) for value in row],
                }
                for index, row in zip(crosstab.index, crosstab.to_numpy(), strict=True)
            ],
        }
    return summary


def _breakdown_field(prior: Any, sampled: pd.DataFrame, context_fields: list[str]) -> str | None:
    """The column to cross-tab a conditional feature against."""
    if not isinstance(prior, ConditionalPrior):
        return None
    source = prior.source_feature
    if source in sampled.columns and sampled[source].nunique() <= MAX_CONDITION_CARDINALITY:
        return source
    return None


def _sample_rows(sampled: pd.DataFrame, limit: int = 25) -> list[dict[str, Any]]:
    head = sampled.head(limit)
    return [
        {
            column: (
                round(float(value), 4)
                if isinstance(value, (int, float, np.floating)) and not isinstance(value, bool)
                else str(value)
            )
            for column, value in record.items()
        }
        for record in head.to_dict("records")
    ]


# -- registry upkeep ---------------------------------------------------------


def suggest_registry(
    config: dict[str, Any], candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Registry entries for every field the config references but hasn't declared.

    The registry is what the sampler validates against, so it has to list each
    prior target and each conditioning field. Rather than make the user restate
    what the semantic fields and GIS columns already say, fill it from those.
    """
    by_name = {candidate["name"]: candidate for candidate in candidates}
    declared = {
        field.get("name")
        for field in (config.get("registry") or {}).get("fields", [])
        if isinstance(field, dict)
    }

    referenced: list[str] = []
    for name, prior in (config.get("priors") or {}).items():
        if not isinstance(prior, dict):
            continue
        if name.startswith(f"{COMPOUND_PREFIX}."):
            # The key itself is generated, but the fields it joins are real and
            # have to be declared for the sampler to validate against them.
            referenced.extend((prior.get("sampler") or {}).get("features_to_concatenate") or [])
            continue
        referenced.append(name)
        source = prior.get("source_feature")
        if source and not source.startswith(f"{COMPOUND_PREFIX}."):
            referenced.append(source)

    for joint in config.get("joints") or []:
        if not isinstance(joint, dict):
            continue
        referenced.append(joint.get("target"))
        referenced.extend(joint.get("condition_on") or [])

    additions: list[dict[str, Any]] = []
    for name in referenced:
        if not name or name in declared:
            continue
        declared.add(name)
        additions.append(registry_entry(by_name.get(name), name))
    return additions


def registry_entry(candidate: dict[str, Any] | None, name: str) -> dict[str, Any]:
    """One `registry.fields[]` entry, preferring declared options over observed ones."""
    if candidate is None:
        return {"name": name, "values": [], "dtype": "categorical"}
    if candidate.get("dtype") == "numeric":
        return {
            "name": name,
            "values": [],
            "dtype": "numeric",
            "description": candidate.get("description"),
        }
    values = list(candidate.get("declaredValues") or []) or list(
        candidate.get("observedValues") or []
    )
    return {
        "name": name,
        "values": values,
        "dtype": "categorical",
        "description": candidate.get("description"),
    }


# -- scenarios ---------------------------------------------------------------
#
# A scenario overrides some features with fixed or conditional values and
# resamples whatever depends on them ("electrify everything built after 2003",
# "insulate the pre-1975 stock"). The engine applies one to a sampled frame; the
# job here is to run the baseline and every scenario off the same draw so the
# comparison isolates the scenario rather than sampling noise.


def scenario_targets(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Features a scenario can override, with the values each one may take.

    Only sampled features can be overridden -- a context field read from the GIS
    data is a fact about the building, not something a scenario changes.
    """
    try:
        parsed = parse_config(config)
        priors = parsed.to_priors()
    except (PriorTreeError, ValidationError, ValueError):
        return []

    declared = parsed.registry.by_name
    targets: list[dict[str, Any]] = []
    for name, prior in priors.sampled_features.items():
        if name.startswith(f"{COMPOUND_PREFIX}."):
            continue
        field = declared.get(name)
        targets.append(
            {
                "name": name,
                "dtype": field.dtype if field is not None else "categorical",
                "values": list(field.values) if field is not None else [],
                "dependsOn": sorted(prior.depends_on),
            }
        )

    # A scenario may also branch on a context field (e.g. only post-2003 stock),
    # so those are offered for `based_on` even though they can't be overridden.
    context = sorted(priors.depends_on - set(priors.sampled_features))
    conditions = [
        {
            "name": name,
            "dtype": declared[name].dtype if name in declared else "categorical",
            "values": list(declared[name].values) if name in declared else [],
        }
        for name in context
    ]
    return targets + [{**entry, "contextOnly": True, "dependsOn": []} for entry in conditions]


def _validate_scenarios(parsed: RegionConfig, priors: Any) -> tuple[list[str], list[str]]:
    """Check each scenario against the features it claims to change."""
    errors: list[str] = []
    warnings: list[str] = []

    sampled = set(priors.sampled_features)
    available = sampled | (priors.depends_on - sampled) | set(parsed.registry.names)
    declared = parsed.registry.by_name
    seen: set[str] = set()

    for scenario in parsed.scenarios:
        if scenario.name in seen:
            errors.append(f"Two scenarios are both named '{scenario.name}'.")
        seen.add(scenario.name)

        if not scenario.overrides:
            warnings.append(f"Scenario '{scenario.name}' changes nothing.")

        for target, override in scenario.overrides.items():
            if target not in sampled:
                errors.append(
                    f"Scenario '{scenario.name}' overrides '{target}', which no prior samples."
                )
            field = declared.get(target)

            if isinstance(override, FixedOverride):
                _check_literal(scenario.name, target, override.set, field, available, errors)
                continue

            if override.based_on not in available:
                errors.append(
                    f"Scenario '{scenario.name}' branches on '{override.based_on}', "
                    "which is not a field in this tree."
                )
            source = declared.get(override.based_on)
            if (
                source is not None
                and source.dtype == "categorical"
                and source.values
                and str(override.equals) not in source.values
            ):
                warnings.append(
                    f"Scenario '{scenario.name}' tests {override.based_on} == "
                    f"'{override.equals}', which is not one of its declared values."
                )
            for branch in (override.then, override.otherwise):
                _check_literal(scenario.name, target, branch, field, available, errors)

    return errors, warnings


def _check_literal(
    scenario: str,
    target: str,
    value: Any,
    field: Any,
    available: set[str],
    errors: list[str],
) -> None:
    """A branch value is `$keep`, `$another_feature`, or a literal in the domain."""
    if isinstance(value, str) and value.startswith("$"):
        if value == KEEP_TOKEN:
            return
        referenced = value[1:]
        if referenced not in available:
            errors.append(
                f"Scenario '{scenario}' sets '{target}' from '{value}', but "
                f"'{referenced}' is not a field in this tree."
            )
        return
    if field is not None and field.dtype == "categorical" and field.values:
        if str(value) not in field.values:
            errors.append(
                f"Scenario '{scenario}' sets '{target}' to '{value}', which is not "
                f"one of its declared values."
            )


def preview_scenarios(
    config: dict[str, Any],
    rows: list[dict[str, Any]],
    n: int = 1000,
    seed: int | None = 0,
) -> dict[str, Any]:
    """Sample a baseline, then apply each scenario to that same baseline.

    Sharing one baseline draw is the point: any difference reported is the
    scenario's doing, not two independent samples disagreeing.
    """
    parsed = parse_config(config)
    priors = parsed.to_priors()
    if not parsed.scenarios:
        raise PriorTreeError("There are no scenarios to preview yet.")
    if not priors.sampled_features:
        raise PriorTreeError("There are no priors to sample yet.")

    n = max(1, min(int(n), 20000))
    generator = new_generator(seed)
    context_fields = sorted(priors.depends_on - set(priors.sampled_features))
    frame, usable_rows = _build_context_frame(rows, context_fields, n, generator)

    try:
        baseline = priors.sample(frame, n, generator)
    except (SamplingError, ValueError, KeyError) as exc:
        raise PriorTreeError(str(exc)) from exc

    graph = priors.dependency_graph
    reported = [
        name
        for name in priors.sampled_features
        if not name.startswith(f"{COMPOUND_PREFIX}.")
    ]

    scenarios: list[dict[str, Any]] = []
    for scenario in parsed.scenarios:
        try:
            applied = scenario.apply(baseline, priors, generator)
        except (SamplingError, ValueError, KeyError) as exc:
            raise PriorTreeError(f"Scenario '{scenario.name}' failed to apply: {exc}") from exc

        changed = sorted(scenario.changed_features)
        downstream = sorted(
            {
                node
                for feature in scenario.changed_features
                if feature in graph
                for node in nx.descendants(graph, feature)
            }
            & set(reported)
            - scenario.changed_features
        )
        affected = [name for name in reported if name in set(changed) | set(downstream)]

        scenarios.append(
            {
                "name": scenario.name,
                "changed": changed,
                "downstream": downstream,
                "resampleChangedFeatures": scenario.resample_changed_features,
                "labelColumn": scenario.label_column,
                "features": [
                    _compare_feature(baseline, applied, name) for name in affected
                ],
            }
        )

    return {
        "n": n,
        "seed": seed,
        "contextFields": context_fields,
        "contextRowCount": usable_rows,
        "contextSource": "gis" if usable_rows else "synthetic",
        "scenarios": scenarios,
    }


def _compare_feature(baseline: pd.DataFrame, applied: pd.DataFrame, name: str) -> dict[str, Any]:
    """Baseline vs scenario for one feature, in whichever terms suit its type."""
    before = baseline[name]
    after = applied[name]
    numeric_before = pd.to_numeric(before, errors="coerce")
    is_numeric = numeric_before.notna().all() and before.nunique() > 12

    if is_numeric:
        numeric_after = pd.to_numeric(after, errors="coerce")
        return {
            "feature": name,
            "dtype": "numeric",
            "values": [],
            "numeric": {
                "baselineMean": float(numeric_before.mean()),
                "scenarioMean": float(numeric_after.mean()),
                "baselineStd": float(numeric_before.std(ddof=1)) if len(numeric_before) > 1 else 0.0,
                "scenarioStd": float(numeric_after.std(ddof=1)) if len(numeric_after) > 1 else 0.0,
            },
            "shares": [],
        }

    values = sorted(set(before.astype(str)) | set(after.astype(str)))
    before_shares = before.astype(str).value_counts(normalize=True)
    after_shares = after.astype(str).value_counts(normalize=True)
    return {
        "feature": name,
        "dtype": "categorical",
        "values": values,
        "numeric": None,
        "shares": [
            {
                "value": value,
                "baseline": round(float(before_shares.get(value, 0.0)), 6),
                "scenario": round(float(after_shares.get(value, 0.0)), 6),
            }
            for value in values
        ],
    }
