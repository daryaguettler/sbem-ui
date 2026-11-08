"""Component priors: optional uncertainty on any number of a component a part picks.

A component (a library record) can mark some of its numbers uncertain, each with a curve.
It then stands for n equally likely variants: variant k takes each curve's quantile
(k - 0.5) / n, so the variants cover the curve evenly and reproducibly. When a component has
several uncertain numbers, `link` sets how they move together: independent (the default),
together (variant 1 has every number at its lowest), or a rank correlation rho, through a
Gaussian copula (Iman-Conover). A construction's U-value counts as a number: its variants
resize the insulation layer.

Saved in component-priors.yaml, keyed by component type and name:

    components:
      ConstructionAssembly:
        TestRegion_Residential_Baseline_Pre_1980_Facade:
          n: 5
          fields:
            U: {shape: triangular, min: 0.6, mode: 0.9, max: 1.1}
      Lighting:
        TestRegion_Office:
          n: 5
          fields:
            PowerDensity: {shape: normal, mean: 4.9, std: 0.8, lower: 0}
"""

from __future__ import annotations

import hashlib
import operator
from typing import Any

import numpy as np
from scipy import stats

from services import component_library as lib

#: A construction's U-value (W/m²K): not a field of the record, but what people think in.
U = "U"
#: Layers at or below this conductivity (W/mK) count as the construction's insulation.
INSULATING = 0.06
#: Grid points for curves given as points, where the inverse CDF is found numerically.
_GRID = 2001

SHAPES = {
    "uniform": ("min", "max"),
    "triangular": ("min", "mode", "max"),
    "normal": ("mean", "std"),
    "lognormal": ("mean", "std"),
    "beta": ("alpha", "beta", "min", "max"),
    "histogram": ("edges", "weights"),
    "points": ("x", "density"),
    "empirical": ("values",),
    "scipy": ("name", "params"),
}


class PriorError(ValueError):
    """A distribution can't be used as written; the message says what to fix."""


def _frozen(spec: dict[str, Any]):
    """The scipy distribution a spec describes, or None for an empirical one."""
    shape = spec.get("shape")
    if shape not in SHAPES:
        raise PriorError(f"Unknown shape {shape!r}; use one of {', '.join(SHAPES)}.")
    missing = [p for p in SHAPES[shape] if spec.get(p) is None]
    if missing:
        raise PriorError(f"A {shape} curve needs {', '.join(missing)}.")
    s = spec
    if shape == "uniform":
        if s["max"] <= s["min"]:
            raise PriorError("max has to be above min.")
        return stats.uniform(s["min"], s["max"] - s["min"])
    if shape == "triangular":
        if not s["min"] <= s["mode"] <= s["max"] or s["max"] <= s["min"]:
            raise PriorError("A triangle needs min ≤ mode ≤ max, with max above min.")
        width = s["max"] - s["min"]
        return stats.triang((s["mode"] - s["min"]) / width, s["min"], width)
    if shape == "normal":
        if s["std"] <= 0:
            raise PriorError("std has to be above 0.")
        return stats.norm(s["mean"], s["std"])
    if shape == "lognormal":
        # parametrised by the value's own mean and std, which is how people know it
        if s["mean"] <= 0 or s["std"] <= 0:
            raise PriorError("A lognormal curve needs a mean and std above 0.")
        sigma2 = np.log1p((s["std"] / s["mean"]) ** 2)
        return stats.lognorm(np.sqrt(sigma2), scale=s["mean"] * np.exp(-sigma2 / 2))
    if shape == "beta":
        if s["alpha"] <= 0 or s["beta"] <= 0 or s["max"] <= s["min"]:
            raise PriorError("A beta curve needs alpha and beta above 0, and max above min.")
        return stats.beta(s["alpha"], s["beta"], s["min"], s["max"] - s["min"])
    if shape == "histogram":
        edges, weights = np.asarray(s["edges"], float), np.asarray(s["weights"], float)
        if len(edges) != len(weights) + 1 or np.any(np.diff(edges) <= 0) or np.any(weights < 0) or weights.sum() <= 0:
            raise PriorError("A histogram needs increasing edges, one more edge than weights, and weights ≥ 0.")
        return stats.rv_histogram((weights, edges), density=False)
    if shape == "points":
        x, density = np.asarray(s["x"], float), np.asarray(s["density"], float)
        if len(x) < 2 or len(x) != len(density) or np.any(np.diff(x) <= 0) or np.any(density < 0) or density.sum() <= 0:
            raise PriorError("A drawn curve needs at least 2 points, increasing x, and heights ≥ 0.")
        return _Piecewise(x, density)
    if shape == "scipy":
        family = getattr(stats, str(s["name"]), None)
        if not isinstance(family, stats.rv_continuous):
            raise PriorError(f"scipy.stats has no continuous distribution {s['name']!r}.")
        try:
            return family(**(s["params"] or {}))
        except TypeError as exc:
            raise PriorError(f"{s['name']}: {exc}") from exc
    return None  # empirical


class _Piecewise:
    """A curve drawn as points, linear between them: just enough of scipy's frozen interface."""

    def __init__(self, x: np.ndarray, density: np.ndarray):
        self.grid = np.linspace(x[0], x[-1], _GRID)
        pdf = np.interp(self.grid, x, density)
        cdf = np.concatenate([[0.0], np.cumsum((pdf[1:] + pdf[:-1]) / 2 * np.diff(self.grid))])
        self.cdf_values = cdf / cdf[-1]
        self.pdf_values = pdf / cdf[-1]

    def pdf(self, value):
        return np.interp(value, self.grid, self.pdf_values, left=0.0, right=0.0)

    def cdf(self, value):
        return np.interp(value, self.grid, self.cdf_values)

    def ppf(self, q):
        return np.interp(q, self.cdf_values, self.grid)


def quantiles(spec: dict[str, Any], n: int) -> list[float]:
    """The n stratified values of a curve, lowest first: quantiles (k - 0.5) / n, k = 1..n, of
    the curve cut to [lower, upper] when those are given."""
    if not isinstance(n, int) or n < 1:
        raise PriorError("n has to be a whole number of at least 1.")
    probabilities = (np.arange(n) + 0.5) / n
    dist = _frozen(spec)
    if dist is None:
        values = np.asarray(spec["values"], float)
        if values.size == 0:
            raise PriorError("An empirical curve needs at least one value.")
        lower, upper = spec.get("lower"), spec.get("upper")
        values = values[(values >= (lower if lower is not None else -np.inf)) & (values <= (upper if upper is not None else np.inf))]
        if values.size == 0:
            raise PriorError("No value lies between lower and upper.")
        return [float(v) for v in np.quantile(values, probabilities)]
    low = float(dist.cdf(spec["lower"])) if spec.get("lower") is not None else 0.0
    high = float(dist.cdf(spec["upper"])) if spec.get("upper") is not None else 1.0
    if high <= low:
        raise PriorError("The curve has no weight between lower and upper.")
    return [float(v) for v in dist.ppf(low + probabilities * (high - low))]


def curve(spec: dict[str, Any], points: int = 120) -> dict[str, list[float]]:
    """The curve to draw: {x, density}, over where it has weight and cut to [lower, upper]."""
    lower, upper = spec.get("lower"), spec.get("upper")
    dist = _frozen(spec)
    if dist is None:  # empirical: a histogram of the values
        values = np.asarray(spec["values"], float)
        values = values[(values >= (lower if lower is not None else -np.inf)) & (values <= (upper if upper is not None else np.inf))]
        if values.size == 0:
            raise PriorError("No value lies between lower and upper.")
        density, edges = np.histogram(values, bins=min(20, max(1, values.size // 2)), density=True)
        return {"x": [float(v) for v in (edges[:-1] + edges[1:]) / 2], "density": [float(v) for v in density]}
    ends = [float(dist.ppf(q)) for q in (0.0, 1.0)]
    lo = ends[0] if np.isfinite(ends[0]) else float(dist.ppf(0.002))
    hi = ends[1] if np.isfinite(ends[1]) else float(dist.ppf(0.998))
    lo, hi = max(lo, lower) if lower is not None else lo, min(hi, upper) if upper is not None else hi
    if hi <= lo:
        raise PriorError("The curve has no weight between lower and upper.")
    x = np.linspace(lo, hi, points)
    density = np.nan_to_num(np.asarray(dist.pdf(x), float), posinf=0.0)
    return {"x": [float(v) for v in x], "density": [float(v) for v in density]}


def preview(component_type: str | None, name: str | None, prior: dict[str, Any], db=None) -> dict[str, Any]:
    """What the editor draws: each field's curve and values, the variants, and every reason the
    variants can't be built from component `name` (when the library is at hand)."""
    errors: list[str] = []
    fields: dict[str, Any] = {}
    for field, spec in (prior.get("fields") or {}).items():
        try:
            fields[field] = {**curve(spec), "values": quantiles(spec, prior.get("n"))}
        except PriorError as exc:
            errors.append(f"{field}: {exc}")
    rows: list[dict[str, float]] = []
    if not errors and fields:
        try:
            rows = variants(name or "preview", prior)
        except PriorError as exc:
            errors.append(str(exc))
    if rows and db is not None and component_type and name:
        record = lib.get_record(db, component_type, name)
        conductivity = (
            {m["Name"]: m["Conductivity"] for m in lib.list_records(db, "ConstructionMaterial")}
            if any(U in row for row in rows) else None
        )
        if record is None:
            errors.append(f"No {component_type} called {name!r}.")
        else:
            for k, row in enumerate(rows, start=1):
                try:
                    variant_record(component_type, record, row, conductivity)
                except PriorError as exc:
                    errors.append(f"Variant {k}: {exc}")
    return {"fields": fields, "variants": rows, "errors": errors}


def _seed(name: str) -> int:
    return int(hashlib.sha1(name.encode()).hexdigest()[:8], 16)


def variants(name: str, prior: dict[str, Any]) -> list[dict[str, float]]:
    """The n variants of component `name`: one value per uncertain field each, in variant order."""
    fields = prior.get("fields") or {}
    if not fields:
        raise PriorError(f"{name}: mark at least one number uncertain.")
    n = prior.get("n")
    columns = {field: quantiles(spec, n) for field, spec in fields.items()}
    if len(columns) == 1:
        (field, values), = columns.items()
        return [{field: v} for v in values]
    link = prior.get("link", "independent")
    if link == "together":
        ranks = np.tile(np.arange(n), (len(columns), 1)).T
    else:
        rho = 0.0 if link == "independent" else float(link)
        if not -1 < rho < 1:
            raise PriorError(f"{name}: link has to be independent, together, or a correlation between -1 and 1.")
        m = len(columns)
        corr = np.full((m, m), rho) + np.eye(m) * (1 - rho)
        try:
            chol = np.linalg.cholesky(corr)
        except np.linalg.LinAlgError as exc:
            raise PriorError(f"{name}: a correlation of {rho} can't hold between {m} numbers at once.") from exc
        z = np.random.default_rng(_seed(name)).standard_normal((n, m)) @ chol.T
        ranks = z.argsort(axis=0).argsort(axis=0)  # Iman-Conover: copula ranks, the curves' own values
    return [{field: columns[field][ranks[k, i]] for i, field in enumerate(columns)} for k in range(n)]


# -- variant records -------------------------------------------------------------------


def u_value(layers: list[dict[str, Any]], conductivity: dict[str, float]) -> float:
    """1/Σ(thickness/conductivity), as epinterface computes it (no surface films)."""
    return 1 / sum(layer["Thickness"] / conductivity[layer["ConstructionMaterial"]] for layer in layers)


def layers_for_u(layers: list[dict[str, Any]], conductivity: dict[str, float], target: float) -> list[dict[str, Any]]:
    """The layers resized to reach U `target`: the thickest-resistance insulating layer is
    thickened or thinned (removed at 0); without one, mineral wool goes in before the inner
    finish."""
    if target <= 0:
        raise PriorError("A U-value has to be above 0.")
    layers = [dict(layer) for layer in layers]
    insulating = [i for i, layer in enumerate(layers) if conductivity[layer["ConstructionMaterial"]] <= INSULATING]
    if insulating:
        index = max(insulating, key=lambda i: layers[i]["Thickness"] / conductivity[layers[i]["ConstructionMaterial"]])
    else:
        if lib.INSULATION not in conductivity:
            raise PriorError(f"The library has no {lib.INSULATION!r} to insulate with.")
        index = max(len(layers) - 1, 0)
        layers.insert(index, {"ConstructionMaterial": lib.INSULATION, "Thickness": 0.0})
    k = conductivity[layers[index]["ConstructionMaterial"]]
    others = sum(l["Thickness"] / conductivity[l["ConstructionMaterial"]] for i, l in enumerate(layers) if i != index)
    thickness = k * (1 / target - others)
    if thickness < 0:
        raise PriorError(f"U {target:.3g} can't be reached: without its insulation this construction is U {1 / others:.3g}.")
    if thickness > lib.MAX_INSULATION:
        raise PriorError(f"U {target:.3g} would need {thickness:.2f} m of insulation.")
    layers[index]["Thickness"] = round(thickness, 4)
    return [layer for layer in layers if layer["Thickness"] > 0]


def variant_record(component_type: str, record: dict[str, Any], values: dict[str, float], conductivity: dict[str, float] | None = None) -> dict[str, Any]:
    """`record` (flat, as get_record gives it) with `values` in place, checked against the
    type's limits."""
    out = dict(record)
    limits = {f["name"]: f for f in lib.get_component_type_schema(component_type)["fields"]}
    for field, value in values.items():
        if field == U:
            if component_type != "ConstructionAssembly":
                raise PriorError("Only constructions have a U-value to vary.")
            out["Layers"] = layers_for_u(record["Layers"], conductivity or {}, value)
            continue
        spec = limits.get(field)
        if spec is None or spec.get("kind") != "number":
            raise PriorError(f"{component_type} has no number called {field!r}.")
        if isinstance(record.get(field), int) and not isinstance(record.get(field), bool):
            value = round(value)
        for bound, holds in (("ge", operator.ge), ("gt", operator.gt), ("le", operator.le), ("lt", operator.lt)):
            if bound in spec and not holds(value, spec[bound]):
                raise PriorError(f"{field} {value:.3g} is outside its limit ({bound} {spec[bound]}); cut the curve with lower/upper.")
        out[field] = value
    return out
