"""Convenience wrappers for sampling and applying scenarios end to end."""

import numpy as np
import pandas as pd

from .engine import Priors
from .scenarios import ScenarioSpec


def new_generator(seed: int | None = None) -> np.random.Generator:
    """Create a numpy ``Generator`` (seeded for reproducible sampling)."""
    return np.random.default_rng(seed)


def sample_priors(
    priors: Priors,
    context: pd.DataFrame,
    n: int,
    *,
    seed: int | None = None,
    generator: np.random.Generator | None = None,
) -> pd.DataFrame:
    """Sample ``priors`` over ``n`` rows built from a single-row ``context``.

    If ``context`` has one row it is broadcast to ``n`` rows; if it already has
    ``n`` rows it is used as-is. Pass either a ``seed`` or a ``generator``.
    """
    if generator is None:
        generator = new_generator(seed)
    if len(context) == 1:
        frame = pd.DataFrame([context.iloc[0]] * n).reset_index(drop=True)
    elif len(context) == n:
        frame = context.reset_index(drop=True)
    else:
        msg = f"context must have 1 or {n} rows, got {len(context)}."
        raise ValueError(msg)
    return priors.sample(frame, n, generator)


def apply_scenarios(
    scenarios: list[ScenarioSpec],
    priors: Priors,
    baseline_df: pd.DataFrame,
    generator: np.random.Generator,
    *,
    include_baseline: bool = True,
) -> pd.DataFrame:
    """Apply each scenario to ``baseline_df`` and concatenate the results.

    Mirrors the MA ``convert_to_retrofit_scenario_features`` fan-out: the
    baseline plus one block per scenario, stacked row-wise.
    """
    blocks = [baseline_df] if include_baseline else []
    blocks.extend(s.apply(baseline_df, priors, generator) for s in scenarios)
    return pd.concat(blocks, axis=0, ignore_index=True)
