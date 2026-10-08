"""Programmatic (code-first) prior authoring.

``PriorBuilder`` is the region-agnostic form of the MA ``make_building_priors``
function: instead of hand-writing ``Entry`` lists and ``to_conditions`` calls,
you accumulate priors and compound joints, then ``build()`` a ``Priors`` object.
It emits exactly the same Pydantic objects the config loader produces, so the
code-first and config-first paths converge on one representation.
"""

from ..compose import JointDistribution
from ..compose.joint import Distribution, LookupTable, MarginalEffects
from ..engine import (
    CategoricalSampler,
    ConditionalPrior,
    ConditionalPriorCondition,
    Prior,
    Priors,
    PriorSampler,
    UnconditionalPrior,
)


class PriorBuilder:
    """Accumulate priors in dependency order and build a ``Priors``."""

    def __init__(self) -> None:
        self._priors: dict[str, Prior] = {}

    def add_unconditional(self, feature: str, sampler: PriorSampler) -> "PriorBuilder":
        """Add a prior that always samples from ``sampler``."""
        self._priors[feature] = UnconditionalPrior(sampler=sampler)
        return self

    def add_categorical(
        self, feature: str, distribution: Distribution
    ) -> "PriorBuilder":
        """Add an unconditional categorical prior from a ``{value: weight}`` map."""
        return self.add_unconditional(
            feature,
            CategoricalSampler(
                values=list(distribution.keys()),
                weights=list(distribution.values()),
            ),
        )

    def add_conditional(
        self,
        feature: str,
        *,
        source_feature: str,
        table: LookupTable,
        fallback: Distribution | None = None,
    ) -> "PriorBuilder":
        """Add a prior conditioned directly on a single existing ``source_feature``.

        ``table`` maps each value of ``source_feature`` to a ``{value: weight}``
        distribution over ``feature``.
        """
        conds = [
            ConditionalPriorCondition(
                match_val=match_val,
                sampler=CategoricalSampler(
                    values=list(dist.keys()), weights=list(dist.values())
                ),
            )
            for match_val, dist in table.items()
        ]
        fallback_sampler = (
            CategoricalSampler(
                values=list(fallback.keys()), weights=list(fallback.values())
            )
            if fallback is not None
            else None
        )
        self._priors[feature] = ConditionalPrior(
            source_feature=source_feature,
            conditions=conds,
            fallback_prior=fallback_sampler,
        )
        return self

    def add_joint(
        self,
        feature: str,
        *,
        condition_on: list[str],
        table: LookupTable | None = None,
        marginals: MarginalEffects | None = None,
        fallback: Distribution | None = None,
        separator: str = ".",
    ) -> "PriorBuilder":
        """Condition ``feature`` on a *combination* of fields.

        Adds both the compound-key prior and the conditional target prior. See
        :class:`~semantic_priors.compose.joint.JointDistribution` for the lookup
        vs. derive-from-marginals modes.
        """
        joint = JointDistribution(
            target=feature,
            condition_on=condition_on,
            table=table,
            marginals=marginals,
            fallback=fallback,
            separator=separator,
        )
        self.add_joint_spec(joint)
        return self

    def add_joint_spec(self, joint: JointDistribution) -> "PriorBuilder":
        """Add a pre-built :class:`JointDistribution`."""
        for name, prior in joint.to_priors().items():
            # A shared compound key may be contributed by several joints; the
            # generated prior is identical, so overwrite is safe.
            self._priors[name] = prior
        return self

    def build(self) -> Priors:
        """Return the assembled ``Priors`` (order = insertion order)."""
        return Priors(sampled_features=dict(self._priors))
