"""Sampling: which buildings to simulate, and how many draws of the estimated characteristics each gets.

globi simulates every GIS row as given and has no priors, so estimated characteristics have to
be drawn before a batch run. `write_sample` writes `gis/buildings-sampled.geojson`: the chosen
buildings, each repeated once per draw, with the from-data characteristics applied (as "Save to
project" does) and every estimated characteristic drawn from its estimate with the vendored
semantic_priors engine (as the estimate previews do). Model Execution's artifacts.yml points at it.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import yaml
from semantic_priors import new_generator
from semantic_priors.compose.compound_key import COMPOUND_PREFIX
from semantic_priors.engine.samplers import SamplingError

from services.gis_parser import export_columns
from services.gis_session import get_dataset
from services.prior_trees import PriorTreeError, enriched_rows, parse_config
from services.semantic_transform import build_enriched_properties
from services.workspace import ProjectWorkspace

SAMPLED_GIS = "buildings-sampled.geojson"
MAX_SIMULATIONS = 200_000
DEFAULTS: dict[str, Any] = {
    "draws": 1,
    "seed": 0,
    "buildings": {"mode": "all", "n": 100, "per_stratum": 5, "strata": []},
}


class SamplingRequestError(Exception):
    """The project can't be sampled as asked."""


def read_settings(workspace: ProjectWorkspace) -> dict[str, Any]:
    path = workspace.path("sampling")
    saved = (yaml.safe_load(path.read_text()) or {}) if path.exists() else {}
    return {**DEFAULTS, **saved, "buildings": {**DEFAULTS["buildings"], **(saved.get("buildings") or {})}}


def _priors(config: dict[str, Any]):
    """The compiled estimates, or None when there are none yet."""
    if not (config or {}).get("registry", {}).get("fields"):
        return None
    try:
        priors = parse_config(config).to_priors()
    except PriorTreeError as exc:
        raise SamplingRequestError(f"The estimates aren't valid yet: {exc}") from exc
    return priors if priors.sampled_features else None


def _estimated(priors) -> list[str]:
    if priors is None:
        return []
    return [name for name in priors.sampled_features if not name.startswith(f"{COMPOUND_PREFIX}.")]


def _plan(
    workspace: ProjectWorkspace, fields: list[dict[str, Any]], config: dict[str, Any], settings: dict[str, Any]
) -> dict[str, Any]:
    """Pick the buildings (seeded) and everything the counts and the writer need."""
    dataset = get_dataset(workspace)
    if not dataset or not dataset.get("validated"):
        raise SamplingRequestError("Validate GIS data first (GIS Cleaning).")
    missing = [
        f["name"] for f in fields if f.get("type") == "stochastic" and f["name"] not in _estimated(_priors(config))
    ]
    if missing:
        raise SamplingRequestError(f"No estimate yet for {', '.join(missing)} (Building Characteristics).")

    priors = _priors(config)
    rows = enriched_rows(dataset, fields)
    context_fields = sorted(priors.depends_on - set(priors.sampled_features)) if priors else []
    usable = [i for i, row in enumerate(rows) if all(row.get(f) not in (None, "") for f in context_fields)]

    buildings = settings["buildings"]
    rng = new_generator(int(settings.get("seed") or 0))
    mode = buildings.get("mode", "all")
    if mode == "random":
        n = max(1, min(int(buildings.get("n") or 1), len(usable)))
        chosen = sorted(int(i) for i in rng.choice(usable, size=n, replace=False)) if usable else []
        groups = None
    elif mode == "stratified":
        strata = [s for s in buildings.get("strata") or [] if s]
        if not strata:
            raise SamplingRequestError("Pick at least one characteristic to stratify by.")
        by_group: dict[tuple, list[int]] = defaultdict(list)
        for i in usable:
            key = tuple(rows[i].get(s) for s in strata)
            if all(v not in (None, "") for v in key):
                by_group[key].append(i)
        per = max(1, int(buildings.get("per_stratum") or 1))
        chosen = sorted(
            int(i) for members in by_group.values() for i in rng.permutation(members)[:per]
        )
        groups = len(by_group)
    else:
        chosen, groups = usable, None

    from services.part_rules import variant_fields

    variants = variant_fields(workspace.read_semantic_fields())
    estimated = _estimated(priors) + list(variants)
    draws = max(1, int(settings.get("draws") or 1)) if estimated else 1
    return {
        "dataset": dataset,
        "rows": rows,
        "priors": priors,
        "variants": variants,
        "context_fields": context_fields,
        "chosen": chosen,
        "summary": {
            "totalBuildings": len(rows),
            "skipped": len(rows) - len(usable),
            "buildings": len(chosen),
            "strata": groups,
            "draws": draws,
            "simulations": len(chosen) * draws,
            "estimated": estimated,
        },
    }


def preview_sample(
    workspace: ProjectWorkspace, fields: list[dict[str, Any]], config: dict[str, Any], settings: dict[str, Any]
) -> dict[str, Any]:
    """How many buildings, draws and simulations the settings produce."""
    return _plan(workspace, fields, config, settings)["summary"]


def write_sample(
    workspace: ProjectWorkspace, fields: list[dict[str, Any]], config: dict[str, Any], settings: dict[str, Any]
) -> dict[str, Any]:
    """Write gis/buildings-sampled.geojson (one feature per building × draw) and sampling.yaml."""
    plan = _plan(workspace, fields, config, settings)
    summary, dataset = plan["summary"], plan["dataset"]
    features = dataset.get("features") or []
    if dataset.get("source_format") != "geojson" or not features:
        raise SamplingRequestError("Sampling needs building geometry: upload the GIS data as GeoJSON.")
    if summary["simulations"] > MAX_SIMULATIONS:
        raise SamplingRequestError(f"{summary['simulations']:,} simulations is over the {MAX_SIMULATIONS:,} limit.")
    if not plan["chosen"]:
        raise SamplingRequestError("No buildings selected.")

    draws, priors, rows = summary["draws"], plan["priors"], plan["rows"]
    repeated = [i for i in plan["chosen"] for _ in range(draws)]
    sampled: list[dict[str, Any]] = [{} for _ in repeated]
    if priors is not None:
        import pandas as pd

        frame = pd.DataFrame([{f: rows[i].get(f) for f in plan["context_fields"]} for i in repeated])
        try:
            drawn = priors.sample(frame, len(repeated), new_generator(int(settings.get("seed") or 0)))
        except (SamplingError, ValueError, KeyError) as exc:
            raise SamplingRequestError(f"Drawing the estimates failed: {exc}") from exc
        sampled = [{name: _plain(drawn[name].iloc[k]) for name in _estimated(priors)} for k in range(len(repeated))]
    # which variant of each uncertain component: every index equally likely, correlated ones jointly
    for name, indices in _variant_indices(workspace, plan["variants"], len(repeated), int(settings.get("seed") or 0) + 1).items():
        for k, index in enumerate(indices):
            sampled[k][name] = str(index)

    id_col = (dataset.get("column_mappings") or {}).get("building_id")
    core = export_columns(dataset.get("column_mappings", {}), dataset.get("validated_columns", []))
    raw_rows = dataset.get("rows", [])
    out = []
    for k, i in enumerate(repeated):
        draw = k % draws
        properties = {**build_enriched_properties(raw_rows[i], fields, core), **sampled[k], "draw": draw}
        if id_col and draws > 1:
            properties["source_building_id"] = properties.get(id_col)
            properties[id_col] = f"{properties.get(id_col)}__{draw}"
        out.append({"type": "Feature", "geometry": features[i].get("geometry"), "properties": properties})

    target = workspace.path("gis_dir") / SAMPLED_GIS
    target.write_text(json.dumps({"type": "FeatureCollection", "features": out}))
    workspace.path("sampling").write_text(yaml.safe_dump(settings, sort_keys=False))
    from services.part_rules import compile_project  # large rules only build the combinations these buildings have

    return {
        **summary,
        "path": target.relative_to(workspace.root).as_posix(),
        "rows": len(out),
        "compile": compile_project(workspace),
    }


def _variant_indices(workspace: ProjectWorkspace, levels: dict[str, int], n: int, seed: int) -> dict[str, list[int]]:
    """n draws of each variant index, uniform on 1..L. Linked fields share Gaussian-copula
    uniforms, so a correlation keeps their ranks together whatever each L is."""
    import numpy as np
    from scipy.stats import norm

    from services.part_rules import correlated

    path = workspace.path("component_priors")
    priors = (yaml.safe_load(path.read_text()) or {}) if path.exists() else {}
    rng = new_generator(seed)
    uniforms: dict[str, np.ndarray] = {}
    for fields, rho in correlated(priors, levels):
        m = len(fields)
        chol = np.linalg.cholesky(np.full((m, m), rho) + np.eye(m) * (1 - rho))
        u = norm.cdf(rng.standard_normal((n, m)) @ chol.T)
        uniforms.update({field: u[:, i] for i, field in enumerate(fields)})
    for field in levels:
        uniforms.setdefault(field, rng.random(n))
    return {field: [int(i) for i in np.minimum((u * levels[field]).astype(int) + 1, levels[field])] for field, u in uniforms.items()}


def _plain(value: Any) -> Any:
    """numpy scalars to plain JSON values."""
    return value.item() if hasattr(value, "item") else value
