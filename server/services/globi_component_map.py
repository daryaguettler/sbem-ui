"""The component map globi reads (`component-map.yaml`), produced from the editor's selectors.

The editor already works in globi's shape -- nested component nodes, each optionally
carrying ``selector: {source_fields: [...], suffix: ...}`` -- but its working tree also
holds every node of epinterface's component graph, most of them empty. `to_globi` prunes
that to the nodes that carry a selector (or have a descendant that does), which is the
file globi / epinterface load. `structural_errors` validates it with epinterface's own
composer model, and `check_against_library` resolves the combinations the project's buildings
actually have against its component database, so a map that would fail inside a simulation
fails here first.
"""

from __future__ import annotations

import functools
import itertools
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

SELECTOR_KEYS = ("source_fields", "prefix", "suffix")


def _prune(node: Any) -> dict[str, Any] | None:
    if not isinstance(node, dict):
        return None
    out: dict[str, Any] = {}
    selector = node.get("selector")
    if isinstance(selector, dict) and (selector.get("source_fields") or selector.get("prefix")):
        out["selector"] = {k: selector[k] for k in SELECTOR_KEYS if selector.get(k)}
    for key, value in node.items():
        if key == "selector":
            continue
        child = _prune(value)
        if child:
            out[key] = child
    return out or None


def to_globi(selectors: dict[str, Any]) -> dict[str, Any]:
    """The editor's selector tree with empty nodes removed (globi's component map)."""
    return _prune(selectors) or {}


@functools.cache
def _selector_model() -> Any:
    from epinterface.sbem.components.composer import construct_composer_model, construct_graph
    from epinterface.sbem.components.zones import ZoneComponent

    return construct_composer_model(construct_graph(ZoneComponent), ZoneComponent, use_children=False)


def structural_errors(component_map: dict[str, Any]) -> list[str]:
    """epinterface's validation of the map's structure (unknown nodes, bad selectors)."""
    from pydantic import ValidationError

    try:
        _selector_model().model_validate(component_map)
    except ValidationError as exc:
        return [
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        ]
    return []


#: globi overwrites this column from the manifest's scenario, so every option has to resolve.
SCENARIO = "Scenario"
#: Combinations a check (or a part-rules compile) works through before it gives up.
MAX_CONTEXTS = 20_000


def api_fields(semantic_fields: dict[str, Any]) -> list[dict[str, Any]]:
    """Saved semantic-fields.yaml entries in the shape the GIS transforms take."""
    fields = []
    for field in semantic_fields.get("Fields") or []:
        source = field.get("GIS_Source")
        fields.append({
            "name": field["Name"],
            "options": [str(option) for option in field.get("Options") or []],
            "type": "deterministic" if source else "stochastic",
            "transformation_rule": {
                "source_column": source,
                "type": field.get("Transformation"),
                "numeric_ranges": field.get("Ranges"),
                "categorical_groups": field.get("Groups"),
            } if source else None,
        })
    return fields


def _building_rows(workspace: Any, fields: list[dict[str, Any]]) -> tuple[list[dict[str, Any]] | None, str]:
    """The buildings globi will run (sampled, else saved), else the validated GIS; None without buildings."""
    from services.gis_session import get_dataset
    from services.globi_run_files import saved_gis
    from services.semantic_transform import apply_semantic_fields_to_rows

    gis = saved_gis(workspace)
    if gis is not None:
        features = json.loads(gis.read_text()).get("features") or []
        return [feature.get("properties") or {} for feature in features], gis.name
    dataset = get_dataset(workspace)
    if dataset and dataset.get("validated"):
        return apply_semantic_fields_to_rows(dataset.get("rows", []), fields), "your GIS data"
    return None, "every combination of values"


def building_contexts(workspace: Any, semantic_fields: dict[str, Any] | None = None) -> dict[str, Any]:
    """The semantic-field combinations the project's buildings need, each once.

    A value a building lacks is expanded over the field's options when it is drawn (estimated)
    or set per run (Scenario); a from-data value that is missing or not an option is unmapped,
    because globi refuses the building. -> {contexts, buildings: [count per context], unmapped,
    total, source, truncated}
    """
    fields = api_fields(semantic_fields if semantic_fields is not None else workspace.read_semantic_fields())
    rows, source = _building_rows(workspace, fields)
    # without buildings, every field is expanded over its options
    fixed_fields = [f for f in fields if rows is not None and f["type"] == "deterministic" and f["name"] != SCENARIO]
    expanded = [f for f in fields if f not in fixed_fields]
    bases: Counter[tuple] = Counter()
    unmapped: Counter[tuple[str, str]] = Counter()
    for row in rows if rows is not None else [{}]:
        if rows is None:
            bases[()] += 1
            continue
        values = []
        for field in fixed_fields:
            value = row.get(field["name"])
            if value in (None, "") or str(value) not in field["options"]:
                unmapped[(field["name"], "" if value is None else str(value))] += 1
                break
            values.append(str(value))
        else:
            # a sampled file already carries drawn values; use them rather than every option
            bases[tuple(values) + tuple(_drawn(row, f) for f in expanded)] += 1

    contexts, counts, groups, truncated = [], [], [], False
    names = [f["name"] for f in fixed_fields + expanded]
    for group, (base, count) in enumerate(bases.items()):
        fixed = list(base[: len(fixed_fields)])
        drawn = base[len(fixed_fields):] if rows is not None else (None,) * len(expanded)
        choices = [[value] if value is not None else field["options"] for field, value in zip(expanded, drawn)]
        for combo in itertools.product(*choices):
            if len(contexts) >= MAX_CONTEXTS:
                truncated = True
                break
            contexts.append(dict(zip(names, fixed + list(combo))))
            counts.append(count)
            groups.append(group)
    return {
        "contexts": contexts,
        "buildings": counts,
        # which buildings each context came from, so expanded options count a building once
        "groups": groups,
        "unmapped": [
            {"field": name, "value": value, "buildings": n} for (name, value), n in unmapped.most_common()
        ],
        "total": sum(bases.values()) + sum(unmapped.values()) if rows is not None else 0,
        "source": source,
        "truncated": truncated,
    }


def _drawn(row: dict[str, Any], field: dict[str, Any]) -> str | None:
    value = row.get(field["name"])
    if field["name"] == SCENARIO or value in (None, "") or str(value) not in field["options"]:
        return None
    return str(value)


def _selectors(node: Any, path: str = "") -> list[tuple[str, dict[str, Any]]]:
    out = []
    if isinstance(node, dict):
        if isinstance(node.get("selector"), dict):
            out.append((path, node["selector"]))
        for key, value in node.items():
            if key != "selector":
                out.extend(_selectors(value, f"{path}.{key}" if path else key))
    return out


def check_against_library(
    component_map: dict[str, Any],
    db_path: Path,
    found: dict[str, Any],
    *,
    n_resolve: int = 40,
    seed: int = 0,
) -> dict[str, Any]:
    """Check the map and library against the buildings' combinations (`building_contexts`).

    Every record name a selector builds for those combinations must exist; then a sample of
    them is resolved end to end with epinterface's composer, which also catches records that
    exist but can't build a zone. -> {ok, tested, failed, errors, missing, unmapped, buildings, source}
    """
    from epinterface.sbem.components.composer import ComponentNameConstructor

    from services import component_library as lib
    from services.component_tree import get_component_tree

    base = {"unmapped": found["unmapped"], "buildings": found["total"], "source": found["source"], "missing": []}
    errors = [
        f"{u['buildings']} building(s) have {u['field']} = {u['value']!r}, which isn't one of its values."
        for u in found["unmapped"]
    ]
    structural = structural_errors(component_map)
    if structural:
        return {**base, "ok": False, "tested": 0, "failed": 0, "errors": structural[:10]}
    if not db_path.exists():
        return {**base, "ok": False, "tested": 0, "failed": 0, "errors": [f"{db_path.name} not found"]}
    selector = _selector_model().model_validate(component_map)
    complete, gaps = selector.validate_successful_resolution(raise_on_failure=False)
    if not complete:
        parts = sorted({gap.replace(":NoSelectorSpecified", "").replace(":", ".") for gap in gaps})
        return {**base, "ok": False, "tested": 0, "failed": 0,
                "errors": errors + [f"Nothing decides {', '.join(parts)}."]}

    contexts, counts = found["contexts"], found["buildings"]
    groups = found.get("groups") or list(range(len(contexts)))
    types = {node["path"]: node["componentType"] for node in get_component_tree()["nodes"]}
    db = _open_db(db_path)
    bad: set[int] = set()
    missing = []
    with db:
        for path, sel in _selectors(component_map):
            namer = ComponentNameConstructor.model_validate(sel)
            needed: dict[str, list[int]] = {}
            for i, context in enumerate(contexts):
                try:
                    needed.setdefault(namer.construct_name(context), []).append(i)
                except ValueError as exc:
                    return {**base, "ok": False, "tested": 0, "failed": 0, "errors": [f"{path}: {exc}"]}
            exists = lib.check_existence(db, types[path], list(needed))
            for name, ids in needed.items():
                if not exists[name]:
                    bad.update(ids)
                    by_group = {groups[i]: counts[i] for i in ids}
                    missing.append({"path": path, "type": types[path], "name": name, "buildings": sum(by_group.values())})
        missing.sort(key=lambda m: -m["buildings"])
        errors += [f"No {m['type']} record {m['name']!r} for {m['path']} ({m['buildings']} building(s))." for m in missing[:10]]

        used = {f for _, sel in _selectors(component_map) for f in sel.get("source_fields", [])}
        distinct = {tuple(sorted((k, v) for k, v in context.items() if k in used)): i
                    for i, context in enumerate(contexts) if i not in bad}
        sample = random.Random(seed).sample(sorted(distinct), min(n_resolve, len(distinct)))
        failures: Counter[str] = Counter()
        for key in sample:
            try:
                selector.get_component(context=dict(key), db=db)
            except Exception as exc:  # any failure here would fail a simulation
                failures[str(exc).splitlines()[0][:200]] += 1
                bad.add(distinct[key])
    errors += [message for message, _ in failures.most_common(10)]
    return {
        **base,
        "ok": not errors,
        "tested": len(contexts),
        "failed": len(bad) + sum(u["buildings"] for u in found["unmapped"]),
        "errors": errors,
        "missing": missing[:50],
    }


def _open_db(db_path: Path):
    from epinterface.sbem.prisma.client import PrismaSettings

    return PrismaSettings.New(database_path=db_path, if_exists="ignore", auto_register=False).db
