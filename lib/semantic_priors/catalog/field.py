"""Semantic field definitions.

A ``SemanticField`` declares one dimension of the domain (e.g. ``Typology``,
``Age_bracket``, ``Windows``) together with the discrete set of values it may
take. This is the region-agnostic replacement for the hard-coded ``Literal``
enumerations that were baked into the MA ``BuildingInferenceInput`` model.
"""

from typing import Literal

from pydantic import BaseModel, model_validator

FieldDType = Literal["categorical", "numeric"]


class SemanticField(BaseModel):
    """One semantic dimension the user can sample and compose on.

    Attributes:
        name: The feature name, used verbatim as the DataFrame column and in
            compound keys (e.g. ``"Typology"`` or ``"feature.semantic.Windows"``).
        values: The allowed discrete values (required for categorical fields;
            empty for numeric fields whose domain is continuous).
        dtype: ``"categorical"`` or ``"numeric"``.
        description: Optional human-readable note.
    """

    name: str
    values: list[str] = []
    dtype: FieldDType = "categorical"
    description: str | None = None

    @model_validator(mode="after")
    def _check_values(self):
        if self.dtype == "categorical" and not self.values:
            msg = f"Categorical field {self.name!r} must declare at least one value."
            raise ValueError(msg)
        return self

    def validate_value(self, value) -> bool:
        """Return True if ``value`` is within this field's declared domain.

        Numeric fields accept any value (their domain is enforced by the
        sampler, e.g. a clipped normal), categorical fields must match a
        declared value.
        """
        if self.dtype == "numeric":
            return True
        return value in self.values
