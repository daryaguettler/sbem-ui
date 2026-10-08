"""Declarative (config-first) authoring: YAML/JSON <-> a full region config.

A ``RegionConfig`` bundles everything needed to describe a region's priors as
data: the field catalog, raw priors, compound joints, and scenarios. It
round-trips to YAML/JSON (the ``Priors`` half already round-trips in the MA repo
via ``Priors(**yaml.safe_load(f))`` — this extends that to the whole config).

``merge_priors`` is the region-agnostic form of the MA ``update_priors``: overlay
a base ``Priors`` with data-derived priors (e.g. census-estimated distributions).
"""

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from ..catalog import FieldRegistry
from ..compose import JointDistribution
from ..engine import Prior, Priors
from ..scenarios import ScenarioSpec


class RegionConfig(BaseModel):
    """A complete, serializable description of a region's priors.

    Attributes:
        registry: The declared semantic fields.
        priors: Raw priors keyed by feature (unconditional or single-source
            conditional). Authored in dependency order.
        joints: Compound (multi-field) conditional distributions.
        scenarios: Named override/resample transformations.
    """

    registry: FieldRegistry = FieldRegistry()
    priors: dict[str, Prior] = {}
    joints: list[JointDistribution] = []
    scenarios: list[ScenarioSpec] = []

    def to_priors(self) -> Priors:
        """Assemble a single ``Priors`` from raw priors and joints.

        Raw priors come first in their authored order, then each joint's
        compound key and target. Shared compound keys are emitted once.
        """
        sampled: dict[str, Prior] = dict(self.priors)
        for joint in self.joints:
            for name, prior in joint.to_priors().items():
                sampled[name] = prior
        return Priors(sampled_features=sampled)

    @property
    def scenarios_by_name(self) -> dict[str, ScenarioSpec]:
        """Scenarios indexed by name."""
        return {s.name: s for s in self.scenarios}

    # -- serialization ------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegionConfig":
        """Build a config from a plain dict (e.g. parsed YAML)."""
        return cls(**data)

    @classmethod
    def load(cls, path: str | Path) -> "RegionConfig":
        """Load a config from a YAML or JSON file."""
        path = Path(path)
        text = path.read_text()
        if path.suffix in {".yaml", ".yml"}:
            data = yaml.safe_load(text)
        elif path.suffix == ".json":
            data = json.loads(text)
        else:
            msg = f"Unsupported config extension {path.suffix!r}; use .yaml/.yml/.json."
            raise ValueError(msg)
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON/YAML-safe dict (round-trips back through ``from_dict``)."""
        return self.model_dump(mode="json", exclude_defaults=False)

    def save(self, path: str | Path) -> None:
        """Write the config to a YAML or JSON file."""
        path = Path(path)
        data = self.to_dict()
        if path.suffix in {".yaml", ".yml"}:
            path.write_text(yaml.safe_dump(data, sort_keys=False))
        elif path.suffix == ".json":
            path.write_text(json.dumps(data, indent=2))
        else:
            msg = f"Unsupported config extension {path.suffix!r}; use .yaml/.yml/.json."
            raise ValueError(msg)


def load_priors_yaml(path: str | Path) -> Priors:
    """Load a serialized ``Priors`` blob (the ``heating_priors.yaml`` shape)."""
    data = yaml.safe_load(Path(path).read_text())
    return Priors(**data)


def merge_priors(base: Priors, override: Priors) -> Priors:
    """Overlay ``override`` onto ``base`` (the ``update_priors`` equivalent).

    Features present in both are replaced by the override's version; new
    features are appended. Base order is preserved; new overrides follow.
    """
    merged: dict[str, Prior] = dict(base.sampled_features)
    merged.update(override.sampled_features)
    return Priors(sampled_features=merged)
