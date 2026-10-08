"""Joint (conditional) distributions over a concatenated semantic field.

A ``JointDistribution`` assigns a distribution to a *target* feature conditioned
on a *combination* of other semantic fields. Choosing to condition ``Walls`` on
``["Typology", "Age_bracket"]`` produces:

1. a compound-key prior that concatenates those fields into ``"SFH.pre_1975"`` etc., and
2. a ``ConditionalPrior`` for ``Walls`` that dispatches on that key.

Two authoring modes (both supported per design):

* **Lookup** — give the full table ``{combined_key: {target_value: weight}}``.
  This is exactly the MA ``Entry`` tables / ``heating_priors.yaml`` shape.
* **Derive** — give per-field *marginal effects*
  ``{field: {field_value: {target_value: weight}}}``; the library forms the
  cross-product of the chosen fields and multiplies the per-field weights
  (independence assumption), renormalizing, to synthesize the full table.

When both are present the explicit lookup table wins and derived combinations
fill any gaps.
"""

import itertools

from pydantic import BaseModel, model_validator

from ..engine import (
    CategoricalSampler,
    ConditionalPrior,
    ConditionalPriorCondition,
    Prior,
)
from .compound_key import (
    COMPOUND_PREFIX,
    DEFAULT_SEPARATOR,
    compound_key_name,
    make_compound_key,
)

# value -> weight
Distribution = dict[str, float]
# combined key string -> distribution over target values
LookupTable = dict[str, Distribution]
# field -> field value -> distribution over target values
MarginalEffects = dict[str, dict[str, Distribution]]


def _to_conditions(table: LookupTable) -> list[ConditionalPriorCondition]:
    """Compile a lookup table into conditional-prior conditions.

    Generalizes the MA ``to_conditions`` helper: each combined key becomes a
    ``CategoricalSampler`` over the target values with their weights.
    """
    conds: list[ConditionalPriorCondition] = []
    for match_val, dist in table.items():
        values = list(dist.keys())
        weights = list(dist.values())
        conds.append(
            ConditionalPriorCondition(
                match_val=match_val,
                sampler=CategoricalSampler(values=values, weights=weights),
            )
        )
    return conds


def _derive_table(
    condition_on: list[str],
    marginals: MarginalEffects,
    *,
    separator: str,
) -> LookupTable:
    """Synthesize a full lookup table from per-field marginal effects.

    For each combination of field values, the weight of a target value is the
    product of that target value's weight across every conditioning field
    (independence), then renormalized to sum to 1.
    """
    for f in condition_on:
        if f not in marginals:
            msg = f"Derive mode: no marginal effects provided for field {f!r}."
            raise ValueError(msg)

    # The set of target values is the union across all field-value entries.
    target_values: list[str] = []
    for field in condition_on:
        for dist in marginals[field].values():
            for v in dist:
                if v not in target_values:
                    target_values.append(v)

    # Cross-product of each field's declared values (order follows condition_on).
    per_field_values = [list(marginals[field].keys()) for field in condition_on]
    table: LookupTable = {}
    for combo in itertools.product(*per_field_values):
        key = separator.join(combo)
        weights: Distribution = {}
        for tv in target_values:
            w = 1.0
            for field, field_value in zip(condition_on, combo, strict=True):
                w *= marginals[field][field_value].get(tv, 0.0)
            weights[tv] = w
        total = sum(weights.values())
        if total <= 0:
            msg = (
                f"Derived combination {key!r} has zero total weight across target "
                f"values; check the marginal effects for {condition_on}."
            )
            raise ValueError(msg)
        table[key] = {tv: w / total for tv, w in weights.items()}
    return table


class JointDistribution(BaseModel):
    """A target feature's distribution conditioned on a combination of fields."""

    target: str
    condition_on: list[str]
    table: LookupTable | None = None
    marginals: MarginalEffects | None = None
    fallback: Distribution | None = None
    separator: str = DEFAULT_SEPARATOR
    compound_prefix: str = COMPOUND_PREFIX

    @model_validator(mode="after")
    def _check_modes(self):
        if not self.condition_on:
            msg = "JointDistribution requires at least one field in condition_on."
            raise ValueError(msg)
        if self.table is None and self.marginals is None:
            msg = (
                f"JointDistribution for {self.target!r} needs either a lookup "
                "'table' or 'marginals' to derive from."
            )
            raise ValueError(msg)
        return self

    @property
    def compound_key(self) -> str:
        """The name of the concatenated semantic field this conditions on."""
        return compound_key_name(
            self.condition_on, prefix=self.compound_prefix, separator=self.separator
        )

    def resolved_table(self) -> LookupTable:
        """The effective lookup table (explicit entries override derived ones)."""
        derived: LookupTable = {}
        if self.marginals is not None:
            derived = _derive_table(
                self.condition_on, self.marginals, separator=self.separator
            )
        if self.table is not None:
            # Explicit lookup entries take precedence; derived entries fill gaps.
            merged = dict(derived)
            merged.update(self.table)
            return merged
        return derived

    def to_priors(self) -> dict[str, Prior]:
        """Compile to an ordered ``{feature: Prior}`` fragment.

        Returns two entries in dependency order: the compound key, then the
        target's conditional prior. Merge this into a ``Priors.sampled_features``
        dict (the compound key must precede the target).
        """
        key_name, key_prior = make_compound_key(
            self.condition_on,
            prefix=self.compound_prefix,
            separator=self.separator,
        )
        fallback_sampler = None
        if self.fallback is not None:
            fallback_sampler = CategoricalSampler(
                values=list(self.fallback.keys()),
                weights=list(self.fallback.values()),
            )
        target_prior = ConditionalPrior(
            source_feature=key_name,
            conditions=_to_conditions(self.resolved_table()),
            fallback_prior=fallback_sampler,
        )
        return {key_name: key_prior, self.target: target_prior}
