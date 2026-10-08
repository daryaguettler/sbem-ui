"""Field composition: concatenated semantic fields and joint distributions."""

from .compound_key import (
    COMPOUND_PREFIX,
    DEFAULT_SEPARATOR,
    compound_key_name,
    make_compound_key,
)
from .joint import JointDistribution

__all__ = [
    "COMPOUND_PREFIX",
    "DEFAULT_SEPARATOR",
    "JointDistribution",
    "compound_key_name",
    "make_compound_key",
]
