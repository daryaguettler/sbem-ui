"""ResStock's own odds for its characteristics (templates/resstock-odds, scripts/fetch_resstock_odds.py).

A table row is one combination of the characteristic's dependencies (other ResStock
characteristics, e.g. Vintage), with the share of homes taking each option, and
`sampling_probability`: how common that combination is among ResStock's homes. The odds for a
group of buildings are the rows matching it, averaged with sampling_probability as the weight.

Each dependency is set by a `DependencySpec`: `any` (every value, in ResStock's mix), `fixed`
(one value), `state` (a geographic dependency's values found in one US state), or `field` (one of the project's characteristics, with the ResStock values each of
its values stands for), which gives one row of odds per value of that characteristic.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from typing import Any

import numpy as np
import yaml

from services.template_loader import TEMPLATES_DIR

TAG = "v3.4.0"
ODDS_DIR = TEMPLATES_DIR / "resstock-odds" / TAG


class ResStockOddsError(Exception):
    """The odds can't be built (the message says why)."""


@dataclass(frozen=True)
class Table:
    dependencies: list[str]
    options: list[str]
    #: one tuple of dependency values per row
    keys: list[tuple[str, ...]]
    #: rows × options: the share of homes taking each option
    shares: np.ndarray
    #: per row: how common the combination is among ResStock's homes
    weights: np.ndarray


def has_odds(characteristic: str) -> bool:
    return (ODDS_DIR / f"{characteristic}.tsv").exists()


@cache
def load_table(characteristic: str) -> Table:
    path = ODDS_DIR / f"{characteristic}.tsv"
    if not path.exists():
        raise ResStockOddsError(f"ResStock has no odds table for {characteristic!r}.")
    lines = [line for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")]
    header = lines[0].split("\t")
    dep_cols = [i for i, h in enumerate(header) if h.startswith("Dependency=")]
    opt_cols = [i for i, h in enumerate(header) if h.startswith("Option=")]
    weight_col = header.index("sampling_probability")
    keys, shares, weights = [], [], []
    for line in lines[1:]:
        cells = line.split("\t")
        keys.append(tuple(cells[i] for i in dep_cols))
        shares.append([float(cells[i]) for i in opt_cols])
        weights.append(float(cells[weight_col]))
    return Table(
        dependencies=[header[i].removeprefix("Dependency=") for i in dep_cols],
        options=[header[i].removeprefix("Option=") for i in opt_cols],
        keys=keys,
        shares=np.array(shares, dtype=float),
        weights=np.array(weights, dtype=float),
    )


def dependencies(characteristic: str) -> list[dict[str, Any]]:
    """Each dependency with its values and their share of ResStock's homes, commonest first.

    A geographic dependency (Location Region, climate zone, ...) also lists, per value, the
    states with homes in it, so "CR09" reads as the states it covers.
    """
    table = load_table(characteristic)
    out = []
    for d, name in enumerate(table.dependencies):
        totals: dict[str, float] = {}
        for key, weight in zip(table.keys, table.weights, strict=True):
            totals[key[d]] = totals.get(key[d], 0.0) + weight
        total = sum(totals.values()) or 1.0
        states = _states_by_value(name)
        out.append({
            "name": name,
            "geographic": bool(states),
            "values": [
                {"value": v, "share": round(float(w / total), 4), **({"states": states.get(v, [])} if states else {})}
                for v, w in sorted(totals.items(), key=lambda kv: -kv[1])
            ],
        })
    return out


def _states_by_value(dependency: str) -> dict[str, list[str]]:
    """For a geographic dependency: each of its values -> the states with homes there. {} otherwise."""
    out: dict[str, list[str]] = {}
    for state, regions in sorted(state_regions().items()):
        for value in regions.get(dependency, []):
            out.setdefault(value, []).append(state)
    return out


def mapped_fields(spec: dict[str, dict[str, Any]]) -> list[str]:
    """The project characteristics the spec maps onto ResStock's dependencies, in order."""
    return list(dict.fromkeys(s["field"] for s in spec.values() if s.get("mode") == "field" and s.get("field")))


def _allowed(table: Table, spec: dict[str, dict[str, Any]], context: dict[str, str] | None) -> list[set[str] | None]:
    """Per dependency: the values a row may have (None: any). Without `context`, mapped ones are any."""
    unknown = sorted(set(spec) - set(table.dependencies))
    if unknown:
        raise ResStockOddsError(f"Not a dependency of this ResStock table: {', '.join(unknown)}.")
    allowed: list[set[str] | None] = []
    for name in table.dependencies:
        s = spec.get(name) or {"mode": "any"}
        if s.get("mode") == "fixed":
            allowed.append({str(s.get("value"))})
        elif s.get("mode") == "state":
            values = state_regions().get(str(s.get("state")), {}).get(name)
            if not values:
                raise ResStockOddsError(f"No {name} data for state {s.get('state')!r}.")
            allowed.append(set(values))
        elif s.get("mode") == "field" and context is not None and s.get("field") in context:
            allowed.append({str(v) for v in (s.get("mapping") or {}).get(context[s["field"]], [])})
        else:
            allowed.append(None)
    return allowed


def odds(
    characteristic: str, options: list[str], spec: dict[str, dict[str, Any]], context: dict[str, str] | None = None
) -> tuple[dict[str, float], float, int]:
    """The odds of `options` for buildings matching `spec` (and `context`, the buildings' values
    of the mapped characteristics). An option ResStock's table never assigns (see unused_options)
    gets 0. -> (odds summing to 1, share of the matched homes those options cover before
    rescaling, matched rows). No matching rows: ({}, 0, 0); options covering none: even odds."""
    table = load_table(characteristic)
    allowed = _allowed(table, spec, context)
    mask = np.array([all(a is None or key[d] in a for d, a in enumerate(allowed)) for key in table.keys])
    weights = table.weights[mask]
    if not mask.any() or weights.sum() <= 0:
        return {}, 0.0, 0
    mix = (table.shares[mask] * weights[:, None]).sum(axis=0) / weights.sum()
    picked = np.array([mix[table.options.index(o)] if o in table.options else 0.0 for o in options])
    covered = float(picked.sum())
    if covered <= 0:
        return {o: 1 / len(options) for o in options}, 0.0, int(mask.sum())
    return {o: float(p / covered) for o, p in zip(options, picked, strict=True)}, covered, int(mask.sum())


def unused_options(characteristic: str, options: list[str]) -> list[str]:
    """Options from ResStock's catalogue that its national sample never gives a home."""
    table = load_table(characteristic)
    return [o for o in options if o not in table.options]


@cache
def state_regions() -> dict[str, dict[str, list[str]]]:
    """Per state, the values of ResStock's geographic dependencies (scripts/fetch_resstock_odds.py)."""
    path = ODDS_DIR / "state-regions.yml"
    return yaml.safe_load(path.read_text()) if path.exists() else {}


def options_in_state(characteristic: str, state: str) -> dict[str, float] | None:
    """Share of `state`'s homes taking each option they take at all (commonest first), or None
    when the table has no geographic dependency.

    shortcut: a state spanning several climate zones keeps options used anywhere in those zones
    (including other states' homes); exact per-state odds would need ResStock's County tables.
    """
    regions = state_regions().get(state)
    if regions is None:
        raise ResStockOddsError(f"No ResStock region data for state {state!r}.")
    table = load_table(characteristic)
    geo = {d: set(regions[name]) for d, name in enumerate(table.dependencies) if name in regions}
    if not geo:
        return None
    mask = np.array([all(key[d] in values for d, values in geo.items()) for key in table.keys])
    weights = table.weights[mask]
    mix = (table.shares[mask] * weights[:, None]).sum(axis=0) / (weights.sum() or 1.0)
    ranked = sorted(zip(table.options, mix, strict=True), key=lambda pair: -pair[1])
    return {option: round(float(share), 4) for option, share in ranked if share > 0}
