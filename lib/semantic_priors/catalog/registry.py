"""Field registry: the set of semantic fields a user has declared.

The registry is the catalog a user picks from when composing concatenated
semantic fields. It is fully declarative and serializes to / from config.
"""

import pandas as pd
from pydantic import BaseModel

from .field import SemanticField


class FieldRegistry(BaseModel):
    """A named collection of semantic fields.

    Backed by a list (preserves authoring order) but indexed by name for
    lookup. Region-agnostic: the same code serves any domain's fields.
    """

    fields: list[SemanticField] = []

    @property
    def by_name(self) -> dict[str, SemanticField]:
        """Fields indexed by name."""
        return {f.name: f for f in self.fields}

    @property
    def names(self) -> list[str]:
        """The declared field names, in order."""
        return [f.name for f in self.fields]

    def get(self, name: str) -> SemanticField:
        """Return the field named ``name`` or raise ``KeyError``."""
        by_name = self.by_name
        if name not in by_name:
            msg = f"Field {name!r} is not declared in the registry. Known fields: {self.names}"
            raise KeyError(msg)
        return by_name[name]

    def require(self, names: list[str]) -> list[SemanticField]:
        """Return the fields for ``names``, raising if any are undeclared."""
        return [self.get(n) for n in names]

    def validate_frame(self, df: pd.DataFrame, *, columns: list[str] | None = None):
        """Validate that sampled columns only contain declared values.

        Args:
            df: A sampled feature frame.
            columns: Which columns to check; defaults to the intersection of the
                frame's columns and the registry's categorical fields.

        Raises:
            ValueError: If a categorical column contains an out-of-domain value.
        """
        by_name = self.by_name
        cols = columns if columns is not None else [c for c in df.columns if c in by_name]
        for col in cols:
            field = by_name.get(col)
            if field is None or field.dtype != "categorical":
                continue
            observed = set(pd.unique(df[col].dropna()))
            allowed = set(field.values)
            bad = observed - allowed
            if bad:
                msg = (
                    f"Column {col!r} contains values outside its declared domain: "
                    f"{sorted(bad)} (allowed: {sorted(allowed)})"
                )
                raise ValueError(msg)
