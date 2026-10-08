"""The component map globi reads (`component-map.yaml`), produced from the editor's selectors.

The editor already works in globi's shape -- nested component nodes, each optionally
carrying ``selector: {source_fields: [...], suffix: ...}`` -- but its working tree also
holds every node of epinterface's component graph, most of them empty. `to_globi` prunes
that to the nodes that carry a selector (or have a descendant that does), which is the
file globi / epinterface load. `structural_errors` validates it with epinterface's own
composer model, and `check_against_library` resolves sampled semantic-field combinations
against the project's component database, so a map that would fail inside a simulation
fails here first.
"""

from __future__ import annotations

import functools
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
    if isinstance(selector, dict) and selector.get("source_fields"):
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


def _random_contexts(
    semantic_fields: dict[str, Any], n: int, seed: int
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    fields = semantic_fields.get("Fields") or []
    contexts = []
    for _ in range(n):
        context: dict[str, Any] = {}
        for field in fields:
            options = field.get("Options") or []
            if options:
                context[field["Name"]] = rng.choice(options)
            elif field.get("Min") is not None and field.get("Max") is not None:
                context[field["Name"]] = rng.uniform(field["Min"], field["Max"])
        contexts.append(context)
    return contexts


def check_against_library(
    component_map: dict[str, Any],
    semantic_fields: dict[str, Any],
    db_path: Path,
    *,
    n_tests: int = 200,
    seed: int = 0,
) -> dict[str, Any]:
    """Resolve `n_tests` random semantic-field combinations against the component db.

    Returns ``{ok, tested, failed, errors}``: `errors` are the distinct failure messages
    (most frequent first), e.g. a component name the map builds that the db lacks.
    """
    structural = structural_errors(component_map)
    if structural:
        return {"ok": False, "tested": 0, "failed": 0, "errors": structural[:10]}
    if not db_path.exists():
        return {"ok": False, "tested": 0, "failed": 0, "errors": [f"{db_path.name} not found"]}

    from epinterface.sbem.prisma.client import PrismaSettings

    selector = _selector_model().model_validate(component_map)
    db = PrismaSettings.New(database_path=db_path, if_exists="ignore", auto_register=False).db
    contexts = _random_contexts(semantic_fields, n_tests, seed)
    failures: Counter[str] = Counter()
    with db:
        for context in contexts:
            try:
                selector.get_component(context=context, db=db)
            except Exception as exc:  # any failure here would fail a simulation
                failures[str(exc).splitlines()[0][:200]] += 1
    return {
        "ok": not failures,
        "tested": len(contexts),
        "failed": sum(failures.values()),
        "errors": [message for message, _ in failures.most_common(10)],
    }
