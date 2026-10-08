"""semantic-priors: region-agnostic authoring, composition, and sampling of
prior distributions over semantic fields.

Typical use:

    from semantic_priors import PriorBuilder, sample_priors, new_generator

    priors = (
        PriorBuilder()
        .add_joint(
            "Walls",
            condition_on=["Typology", "Age_bracket"],
            table={"SFH.pre_1975": {"Uninsulated": 0.55, "Insulated": 0.45}},
            fallback={"Uninsulated": 0.5, "Insulated": 0.5},
        )
        .build()
    )
    df = sample_priors(priors, context_row, n=1000, seed=0)

Or load a whole region declaratively:

    from semantic_priors import RegionConfig
    config = RegionConfig.load("configs/example_region.yaml")
    priors = config.to_priors()
"""

from .authoring import PriorBuilder, RegionConfig, load_priors_yaml, merge_priors
from .catalog import FieldRegistry, SemanticField
from .compose import JointDistribution, compound_key_name, make_compound_key
from .engine import (
    CategoricalSampler,
    ClippedNormalSampler,
    ConcatenateFeaturesSampler,
    ConditionalPrior,
    Prior,
    Priors,
    UnconditionalPrior,
    UniformSampler,
)
from .sampling import apply_scenarios, new_generator, sample_priors
from .scenarios import ScenarioSpec

__all__ = [
    "CategoricalSampler",
    "ClippedNormalSampler",
    "ConcatenateFeaturesSampler",
    "ConditionalPrior",
    "FieldRegistry",
    "JointDistribution",
    "Prior",
    "PriorBuilder",
    "Priors",
    "RegionConfig",
    "ScenarioSpec",
    "SemanticField",
    "UnconditionalPrior",
    "UniformSampler",
    "apply_scenarios",
    "compound_key_name",
    "load_priors_yaml",
    "make_compound_key",
    "merge_priors",
    "new_generator",
    "sample_priors",
]
