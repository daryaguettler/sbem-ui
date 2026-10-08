"""Samplers: the primitive distribution/derivation types.

A ``Sampler`` turns a random-number generator (and, for derived samplers, an
existing context ``DataFrame``) into an array of ``n`` sampled values. These are
region-agnostic: they know nothing about buildings, counties, or any specific
domain. Everything is Pydantic so a whole prior specification round-trips to
YAML/JSON.

Ported from the MA-stock-analysis engine (``src/b_baseline_queries/samplers.py``
/ ``epengine.models.sampling``) with no behavioral change.
"""

from abc import ABC, abstractmethod
from typing import cast

import numpy as np
import pandas as pd
from pydantic import BaseModel, model_validator


class SamplingError(Exception):
    """A sampling error."""

    pass


class Sampler(ABC):
    """Abstract base: sample ``n`` values, optionally depending on a context."""

    @abstractmethod
    def sample(
        self, context: pd.DataFrame, n: int, generator: np.random.Generator
    ) -> np.ndarray:
        """Sample features from a prior, which may depend on a context."""
        pass

    @property
    @abstractmethod
    def depends_on(self) -> set[str]:
        """The features that this sampler depends on."""
        pass


# ---------------------------------------------------------------------------
# Distribution samplers (draw from a distribution; no context dependency)
# ---------------------------------------------------------------------------


class UniformSampler(BaseModel, Sampler):
    """Uniform between ``min`` and ``max``."""

    min: float
    max: float

    def sample(
        self, context: pd.DataFrame, n: int, generator: np.random.Generator
    ) -> np.ndarray:
        """Sample uniformly between a min and max value."""
        return generator.uniform(self.min, self.max, size=n)

    @property
    def depends_on(self) -> set[str]:
        """The features that this sampler depends on."""
        return set()


class ClippedNormalSampler(BaseModel, Sampler):
    """Normal distribution clipped to ``[clip_min, clip_max]``."""

    mean: float
    std: float
    clip_min: float | None = None
    clip_max: float | None = None

    def sample(
        self, context: pd.DataFrame, n: int, generator: np.random.Generator
    ) -> np.ndarray:
        """Sample from a normal distribution, clipped to a min and max value."""
        clip_min = self.clip_min if self.clip_min is not None else -np.inf
        clip_max = self.clip_max if self.clip_max is not None else np.inf
        samples = generator.normal(self.mean, self.std, size=n).clip(clip_min, clip_max)
        return samples

    @property
    def depends_on(self) -> set[str]:
        """The features that this sampler depends on."""
        return set()


class FixedValueSampler(BaseModel, Sampler):
    """A single fixed value repeated for all samples."""

    value: float | str | int | bool

    def sample(
        self, context: pd.DataFrame, n: int, generator: np.random.Generator
    ) -> np.ndarray:
        """Sample a fixed value."""
        return np.full(n, self.value)

    @property
    def depends_on(self) -> set[str]:
        """The features that this sampler depends on."""
        return set()


class CategoricalSampler(BaseModel, Sampler):
    """Weighted choice over ``values``; weights are auto-normalized."""

    values: list[str] | list[float] | list[int]
    weights: list[float]

    def sample(
        self, context: pd.DataFrame, n: int, generator: np.random.Generator
    ) -> np.ndarray:
        """Sample from a categorical distribution."""
        return generator.choice(self.values, size=n, p=self.weights)

    @property
    def depends_on(self) -> set[str]:
        """The features that this sampler depends on."""
        return set()

    @model_validator(mode="after")
    def check_values_and_weights(self):
        """Check that values and weights are the same length; normalize weights."""
        if len(self.values) != len(self.weights):
            msg = "values and weights must be the same length"
            raise ValueError(msg)
        total = float(sum(self.weights))
        if total <= 0:
            msg = "weights must sum to a positive value"
            raise ValueError(msg)
        # always renormalize so float-rounded ACS/YAML shares stay valid for
        # np.Generator.choice (stricter than np.isclose defaults)
        self.weights = [w / total for w in self.weights]
        return self


# ---------------------------------------------------------------------------
# Derived samplers (deterministic functions of existing context columns)
# ---------------------------------------------------------------------------


class CopySampler(BaseModel, Sampler):
    """Copy an existing feature column."""

    feature_to_copy: str

    def sample(
        self, context: pd.DataFrame, n: int, generator: np.random.Generator
    ) -> np.ndarray:
        """Compute a copy of a feature."""
        if self.feature_to_copy not in context.columns:
            msg = f"Feature to copy {self.feature_to_copy} not found in context dataframe."
            raise SamplingError(msg)
        if len(context) != n:
            msg = (
                f"Context dataframe must have {n} rows, but it has {len(context)} rows."
            )
            raise SamplingError(msg)
        return context[self.feature_to_copy].to_numpy()

    @property
    def depends_on(self) -> set[str]:
        """The features that this sampler depends on."""
        return {self.feature_to_copy}


class AddValueSampler(BaseModel, Sampler):
    """Add a constant to a feature."""

    feature_to_add_to: str
    value_to_add: float

    def sample(
        self, context: pd.DataFrame, n: int, generator: np.random.Generator
    ) -> np.ndarray:
        """Compute a sum of a feature and a value."""
        if self.feature_to_add_to not in context.columns:
            msg = f"Feature to add to {self.feature_to_add_to} not found in context dataframe."
            raise SamplingError(msg)
        return context[self.feature_to_add_to].to_numpy() + self.value_to_add

    @property
    def depends_on(self) -> set[str]:
        """The features that this sampler depends on."""
        return {self.feature_to_add_to}


class SumValuesSampler(BaseModel, Sampler):
    """Row-wise sum of several features."""

    features_to_sum: list[str]

    def sample(
        self, context: pd.DataFrame, n: int, generator: np.random.Generator
    ) -> np.ndarray:
        """Compute a sum of features."""
        if not all(f in context.columns for f in self.features_to_sum):
            msg = f"All features to sum {self.features_to_sum} must be found in context dataframe."
            raise SamplingError(msg)
        if len(context) != n:
            msg = (
                f"Context dataframe must have {n} rows, but it has {len(context)} rows."
            )
            raise SamplingError(msg)
        return np.sum(context[self.features_to_sum].to_numpy(), axis=1)

    @property
    def depends_on(self) -> set[str]:
        """The features that this sampler depends on."""
        return set(self.features_to_sum)


class MultiplyValueSampler(BaseModel, Sampler):
    """Multiply a feature by a constant."""

    feature_to_multiply: str
    value_to_multiply: float

    def sample(
        self, context: pd.DataFrame, n: int, generator: np.random.Generator
    ) -> np.ndarray:
        """Compute a multiply of a feature."""
        if self.feature_to_multiply not in context.columns:
            msg = f"Feature to multiply {self.feature_to_multiply} not found in context dataframe."
            raise SamplingError(msg)
        if len(context) != n:
            msg = (
                f"Context dataframe must have {n} rows, but it has {len(context)} rows."
            )
            raise SamplingError(msg)
        return context[self.feature_to_multiply].to_numpy() * self.value_to_multiply

    @property
    def depends_on(self) -> set[str]:
        """The features that this sampler depends on."""
        return {self.feature_to_multiply}


class ProductValuesSampler(BaseModel, Sampler):
    """Row-wise product of several features."""

    features_to_multiply: list[str]

    def sample(
        self, context: pd.DataFrame, n: int, generator: np.random.Generator
    ) -> np.ndarray:
        """Compute a product of features."""
        if not all(f in context.columns for f in self.features_to_multiply):
            msg = f"All features to multiply {self.features_to_multiply} must be found in context dataframe."
            raise SamplingError(msg)
        if len(context) != n:
            msg = (
                f"Context dataframe must have {n} rows, but it has {len(context)} rows."
            )
            raise SamplingError(msg)
        return np.prod(context[self.features_to_multiply].to_numpy(), axis=1)

    @property
    def depends_on(self) -> set[str]:
        """The features that this sampler depends on."""
        return set(self.features_to_multiply)


class InvertSampler(BaseModel, Sampler):
    """Multiplicative inverse of a feature."""

    feature_to_invert: str

    def sample(
        self, context: pd.DataFrame, n: int, generator: np.random.Generator
    ) -> np.ndarray:
        """Compute an invert of a feature."""
        if self.feature_to_invert not in context.columns:
            msg = f"Feature to invert {self.feature_to_invert} not found in context dataframe."
            raise SamplingError(msg)
        if len(context) != n:
            msg = (
                f"Context dataframe must have {n} rows, but it has {len(context)} rows."
            )
            raise SamplingError(msg)
        return 1 / context[self.feature_to_invert].to_numpy()

    @property
    def depends_on(self) -> set[str]:
        """The features that this sampler depends on."""
        return {self.feature_to_invert}


class PowerSampler(BaseModel, Sampler):
    """Raise a feature to a power."""

    feature_to_power: str
    power: float

    def sample(
        self, context: pd.DataFrame, n: int, generator: np.random.Generator
    ) -> np.ndarray:
        """Compute a power of a feature."""
        return context[self.feature_to_power].to_numpy() ** self.power

    @property
    def depends_on(self) -> set[str]:
        """The features that this sampler depends on."""
        return {self.feature_to_power}


class LogSampler(BaseModel, Sampler):
    """Logarithm of a feature (default natural log)."""

    feature_to_log: str
    base: float = float(np.e)

    def sample(
        self, context: pd.DataFrame, n: int, generator: np.random.Generator
    ) -> np.ndarray:
        """Compute a log of a feature."""
        if self.feature_to_log not in context.columns:
            msg = (
                f"Feature to log {self.feature_to_log} not found in context dataframe."
            )
            raise SamplingError(msg)
        if len(context) != n:
            msg = (
                f"Context dataframe must have {n} rows, but it has {len(context)} rows."
            )
            raise SamplingError(msg)
        return np.log(context[self.feature_to_log].to_numpy()) / np.log(self.base)

    @property
    def depends_on(self) -> set[str]:
        """The features that this sampler depends on."""
        return {self.feature_to_log}


class ConcatenateFeaturesSampler(BaseModel, Sampler):
    """Concatenate several feature columns into one string key.

    This is the mechanism for building a *concatenated semantic field* — e.g.
    combining ``Typology`` and ``Age_bracket`` into ``"SFH.pre_1975"`` so a joint
    distribution can be conditioned on it.
    """

    features_to_concatenate: list[str]
    separator: str = ":"

    def sample(
        self, context: pd.DataFrame, n: int, generator: np.random.Generator
    ) -> np.ndarray:
        """Compute a concatenation of features."""
        if not all(f in context.columns for f in self.features_to_concatenate):
            msg = f"All features to concatenate {self.features_to_concatenate} must be found in context dataframe."
            raise SamplingError(msg)
        if len(context) != n:
            msg = (
                f"Context dataframe must have {n} rows, but it has {len(context)} rows."
            )
            raise SamplingError(msg)
        cols: pd.DataFrame = cast(pd.DataFrame, context[self.features_to_concatenate])
        return cols.astype(str).agg(self.separator.join, axis=1).to_numpy()

    @property
    def depends_on(self) -> set[str]:
        """The features that this sampler depends on."""
        return set(self.features_to_concatenate)


# Discriminated union of all concrete samplers. Order matters only for
# ambiguous coercion; each model has distinct required fields so Pydantic can
# resolve the correct type on deserialization.
PriorSampler = (
    UniformSampler
    | ClippedNormalSampler
    | FixedValueSampler
    | CategoricalSampler
    | CopySampler
    | AddValueSampler
    | SumValuesSampler
    | MultiplyValueSampler
    | ProductValuesSampler
    | InvertSampler
    | LogSampler
    | ConcatenateFeaturesSampler
    | PowerSampler
)
