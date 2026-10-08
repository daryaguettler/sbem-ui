"""Pydantic models for semantic fields."""

from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict, Any


class GISColumn(BaseModel):
    """Represents a column in GIS data."""
    name: str
    data_type: Literal["numeric", "categorical", "string"]
    unique_values: List[str] = Field(default_factory=list)
    sample_values: List[str] = Field(default_factory=list)
    nullable: bool = False


class RangeMapping(BaseModel):
    """Numeric range mapping for transformation."""
    min: float
    max: float
    label: str


class CategoricalGroup(BaseModel):
    """Categorical grouping for transformation."""
    group_label: str
    source_values: List[str]


class CompoundFieldLogic(BaseModel):
    """Logic for compound field creation."""
    fields: List[str]
    logic: Literal["and", "or"]
    separator: str = "_"


class TransformationRule(BaseModel):
    """Transformation rule for deterministic semantic fields."""
    id: str
    type: Literal["numeric_range", "categorical_mapping", "compound"]
    source_column: str
    target_field: str
    numeric_ranges: Optional[List[RangeMapping]] = None
    categorical_groups: Optional[List[CategoricalGroup]] = None
    compound_logic: Optional[CompoundFieldLogic] = None


class SemanticField(BaseModel):
    """Represents a semantic field."""
    id: str
    name: str
    type: Literal["deterministic", "stochastic"]
    data_type: Literal["numeric", "categorical", "string"]
    options: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    # Deterministic fields
    transformation_rule: Optional[TransformationRule] = None
    # Stochastic fields
    requires_prior: bool = False
    prior_id: Optional[str] = None


class SemanticFieldsConfig(BaseModel):
    """Configuration for semantic fields."""
    name: str
    fields: List[SemanticField] = Field(default_factory=list)
