"""Data-driven scenario transformations.

The MA repo had 13 near-identical ``convert_to_*_scenario_features`` methods.
Each one: (a) overrides some feature columns with fixed or conditional values,
(b) collects the set of changed features, (c) selects the downstream prior
subtree, and (d) resamples it. ``ScenarioSpec`` captures that as data so a single
``apply`` replaces all of them, and scenarios live in config.

Overrides come in two shapes:

* **Fixed** — set a feature to a constant, e.g. ``Heating: {set: ASHPHeating}``
  (the scalar shorthand ``Heating: ASHPHeating`` also works).
* **Conditional** — a vectorized ``np.where`` keyed on another feature's value,
  e.g. keep steam distribution but switch everything else to ducts:

  ```yaml
  Distribution:
    based_on: Distribution     # test this feature (may be the target itself)
    equals: Steam
    then: $keep                # $keep -> keep target's current value
    otherwise: AirDuctsInsulated
  ```

  A value of ``$keep`` reuses the target's current value; ``$<feature>`` reuses
  another feature's current value; anything else is a literal.
"""

from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, model_validator

from ..engine import Priors

KEEP = "$keep"


def _resolve_value(spec: Any, df: pd.DataFrame, target: str):
    """Resolve an override value spec against the current frame.

    ``$keep`` -> target's current column; ``$<feature>`` -> another column;
    otherwise the literal (broadcast by ``np.where`` / assignment).
    """
    if isinstance(spec, str):
        if spec == KEEP:
            return df[target].to_numpy()
        if spec.startswith("$"):
            return df[spec[1:]].to_numpy()
    return spec


class FixedOverride(BaseModel):
    """Set a feature to a constant value."""

    set: Any

    def apply(self, df: pd.DataFrame, target: str) -> None:
        """Assign the constant to ``target`` in place."""
        df[target] = self.set


class ConditionalOverride(BaseModel):
    """Vectorized ``np.where`` override keyed on another feature's value."""

    based_on: str
    equals: Any
    then: Any
    otherwise: Any

    def apply(self, df: pd.DataFrame, target: str) -> None:
        """Apply the conditional assignment to ``target`` in place."""
        mask = df[self.based_on].to_numpy() == self.equals
        then_v = _resolve_value(self.then, df, target)
        else_v = _resolve_value(self.otherwise, df, target)
        df[target] = np.where(mask, then_v, else_v)


Override = FixedOverride | ConditionalOverride


class ScenarioSpec(BaseModel):
    """A named set of feature overrides plus downstream resampling."""

    name: str
    overrides: dict[str, Override] = {}
    label_column: str | None = "scenario"
    resample_changed_features: bool = False

    @model_validator(mode="before")
    @classmethod
    def _normalize_overrides(cls, data: Any) -> Any:
        """Allow scalar and shorthand override forms in config."""
        if not isinstance(data, dict):
            return data
        overrides = data.get("overrides")
        if not isinstance(overrides, dict):
            return data
        normalized: dict[str, Any] = {}
        for feature, spec in overrides.items():
            if isinstance(spec, (FixedOverride, ConditionalOverride)):
                # Already a constructed override (Python-side authoring).
                normalized[feature] = spec
            elif isinstance(spec, dict):
                # Distinguish a conditional dict from a fixed {set: ...} dict.
                if "based_on" in spec:
                    normalized[feature] = spec
                elif "set" in spec:
                    normalized[feature] = spec
                else:
                    msg = (
                        f"Override for {feature!r} must be a scalar, a {{set: ...}} "
                        "map, or a conditional {based_on, equals, then, otherwise} map."
                    )
                    raise ValueError(msg)
            else:
                # Scalar shorthand -> fixed override.
                normalized[feature] = {"set": spec}
        data = {**data, "overrides": normalized}
        return data

    @property
    def changed_features(self) -> set[str]:
        """The features this scenario overrides (drives subtree selection)."""
        return set(self.overrides.keys())

    def apply(
        self,
        features_df: pd.DataFrame,
        priors: Priors,
        generator: np.random.Generator,
    ) -> pd.DataFrame:
        """Return a new frame with overrides applied and the subtree resampled.

        Steps mirror the MA ``convert_to_*`` methods: copy, label, apply each
        override, then resample only the priors downstream of the changed
        features (changed features themselves kept unless
        ``resample_changed_features``).
        """
        df = features_df.copy(deep=True)
        if self.label_column is not None:
            df[self.label_column] = self.name
        for target, override in self.overrides.items():
            override.apply(df, target)
        subtree = priors.select_prior_tree_for_changed_features(
            self.changed_features,
            resample_changed_features=self.resample_changed_features,
        )
        return subtree.sample(df, len(df), generator)
