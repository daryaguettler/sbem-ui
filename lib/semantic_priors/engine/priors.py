"""Priors: conditional / unconditional distributions and their container.

A ``Prior`` assigns a distribution to a single feature. An ``UnconditionalPrior``
wraps one sampler; a ``ConditionalPrior`` dispatches to a different sampler
depending on the value of a ``source_feature`` (typically a concatenated
semantic key). ``Priors`` is the ordered collection that samples a whole
feature ``DataFrame`` in dependency order.

Ported from the MA-stock-analysis engine / ``epengine.models.sampling``. Two
behavioral fixes relative to the older local copy:

* ``ConditionalPrior.sample`` now uses ``np.isnan(final).any()`` for the
  unmatched-value guard (the old ``(final == np.nan).any()`` is always False).
* ``select_prior_tree_for_changed_features`` carries the epengine
  ``resample_changed_features`` parameter and iterates over all sampled features
  (not only roots).
"""

from abc import ABC, abstractmethod

import networkx as nx
import numpy as np
import pandas as pd
from pydantic import BaseModel

from .samplers import PriorSampler, SamplingError


class ConditionalPriorCondition(BaseModel):
    """One branch of a conditional prior: match a value, sample from a sampler."""

    match_val: str | float | int | bool
    sampler: PriorSampler

    def sample(
        self, context: pd.DataFrame, n: int, generator: np.random.Generator
    ) -> np.ndarray:
        """Sample from a conditional prior condition."""
        return self.sampler.sample(context, n, generator)

    @property
    def depends_on(self) -> set[str]:
        """The features that this condition's sampler depends on."""
        return self.sampler.depends_on


class PriorABC(ABC):
    """Abstract prior over a single feature."""

    @abstractmethod
    def sample(
        self, context: pd.DataFrame, n: int, generator: np.random.Generator
    ) -> np.ndarray:
        """Sample from a prior."""
        pass

    @property
    @abstractmethod
    def depends_on(self) -> set[str]:
        """The features that this prior depends on."""
        pass


class ConditionalPrior(BaseModel, PriorABC):
    """Dispatch to a sampler based on the value of ``source_feature``.

    Rows whose ``source_feature`` value matches no condition fall back to
    ``fallback_prior`` (if provided); if there is no fallback and a value is
    unmatched, sampling raises.
    """

    source_feature: str
    conditions: list[ConditionalPriorCondition]
    fallback_prior: PriorSampler | None

    def sample(self, context: pd.DataFrame, n: int, generator: np.random.Generator):
        """Sample from a conditional prior.

        Matched rows are tracked with an explicit boolean mask (not a NaN
        sentinel), so string-valued distributions work correctly and unmatched
        values without a fallback are detected reliably.
        """
        conditional_samples = {
            c.match_val: c.sampler.sample(context, n, generator)
            for c in self.conditions
        }
        test_feature = context[self.source_feature].to_numpy()

        final = np.full(n, np.nan)

        any_matched_mask = np.full(n, False)
        for match_val, samples_for_match_val in conditional_samples.items():
            mask = test_feature == match_val
            any_matched_mask = any_matched_mask | mask
            final = np.where(mask, samples_for_match_val, final)

        if self.fallback_prior is not None:
            mask = ~any_matched_mask
            final = np.where(
                mask, self.fallback_prior.sample(context, n, generator), final
            )
            any_matched_mask = np.full(n, True)

        if not any_matched_mask.all():
            msg = (
                "Some rows were unmatched with no fallback prior for "
                f"feature {self.source_feature!r}."
            )
            raise SamplingError(msg)

        return final

    @property
    def depends_on(self) -> set[str]:
        """The features that this prior depends on."""
        return {self.source_feature} | {
            dependency for c in self.conditions for dependency in c.depends_on
        }


class UnconditionalPrior(BaseModel, PriorABC):
    """A prior that always samples from a single sampler."""

    sampler: PriorSampler

    def sample(self, context: pd.DataFrame, n: int, generator: np.random.Generator):
        """Sample from an unconditional prior."""
        return self.sampler.sample(context, n, generator)

    @property
    def depends_on(self) -> set[str]:
        """The features that this prior depends on."""
        return self.sampler.depends_on


Prior = UnconditionalPrior | ConditionalPrior


class Priors(BaseModel):
    """An ordered collection of priors, sampled into a feature DataFrame.

    ``sampled_features`` maps a feature name to its prior. ``sample`` walks the
    dict in insertion order, writing each feature as a new column so that later
    (derived / conditional) priors can read earlier ones. Author priors in
    dependency order.
    """

    sampled_features: dict[str, Prior]

    def _sampling_order(self) -> list[str]:
        """Feature order respecting intra-prior dependencies.

        Topologically sorts the sampled features so a prior is always sampled
        after any other sampled feature it depends on, using insertion order as
        a stable tie-break. When the priors are already authored in a valid
        order this equals insertion order; when a round-trip (e.g. a
        key-sorting YAML dump) reorders them it repairs the order. Falls back to
        insertion order if a dependency cycle is present.
        """
        order = list(self.sampled_features.keys())
        index = {f: i for i, f in enumerate(order)}
        g = nx.DiGraph()
        g.add_nodes_from(order)
        for feature, prior in self.sampled_features.items():
            for dep in prior.depends_on:
                if dep in self.sampled_features:
                    g.add_edge(dep, feature)
        try:
            return list(
                nx.lexicographical_topological_sort(g, key=lambda f: index[f])
            )
        except nx.NetworkXUnfeasible:
            return order

    def sample(self, context: pd.DataFrame, n: int, generator: np.random.Generator):
        """Sample every prior into a copy of ``context`` (in dependency order)."""
        working_df = context.copy(deep=True)
        for feature in self._sampling_order():
            prior = self.sampled_features[feature]
            working_df[feature] = prior.sample(working_df, n, generator)
        if working_df.isna().any().any():  # pyright: ignore [reportAttributeAccessIssue]
            msg = "Working dataframe contains NaN values; possibly due to an unmatched value."
            raise SamplingError(msg)
        return working_df

    @property
    def depends_on(self) -> set[str]:
        """The union of features every contained prior depends on."""
        return {
            dependency
            for prior in self.sampled_features.values()
            for dependency in prior.depends_on
        }

    @property
    def dependency_graph(self) -> nx.DiGraph:
        """Directed graph with edges from each dependency to its dependent feature.

        Every sampled feature is a node, including unconditional priors with no
        dependencies, so scenario overrides of leaf features resolve cleanly.
        """
        g = nx.DiGraph()
        for feature, prior in self.sampled_features.items():
            g.add_node(feature)
            for dependency in prior.depends_on:
                g.add_edge(dependency, feature)
        return g

    @property
    def root_features(self) -> set[str]:
        """Features (graph nodes) with no incoming dependency edges."""
        return {
            node
            for node in self.dependency_graph.nodes
            if self.dependency_graph.in_degree(node) == 0
        }

    def select_prior_tree_for_changed_features(
        self, changed_features: set[str], resample_changed_features: bool = True
    ) -> "Priors":
        """Return only the priors downstream of a set of changed features.

        Used when a scenario overrides some features with fixed values and we
        want to resample only the affected subtree.

        Args:
            changed_features: The features whose values have been changed.
            resample_changed_features: Whether the changed features themselves
                are resampled. Their dependencies are always resampled. You
                usually want ``False`` (keep the override); ``True`` is the
                backwards-compatible default.

        Returns:
            A new ``Priors`` containing only the downstream (and optionally the
            changed) priors, preserving original order.
        """
        g = self.dependency_graph
        all_changing_priors: set[str] = set()
        for any_feature in self.root_features.union(set(self.sampled_features.keys())):
            if any(f == any_feature for f in changed_features):
                descendants = nx.descendants(g, any_feature)
                if any_feature in self.sampled_features and resample_changed_features:
                    all_changing_priors.add(any_feature)
                for dep in descendants:
                    if dep not in self.sampled_features:
                        continue
                    # keep explicit overrides when not resampling changed features
                    if not resample_changed_features and dep in changed_features:
                        continue
                    all_changing_priors.add(dep)

        return Priors(
            sampled_features={
                f: p
                for f, p in self.sampled_features.items()
                if f in all_changing_priors
            }
        )
