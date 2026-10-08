"""Compose a *concatenated semantic field* from a list of fields.

Picking ``["Typology", "Age_bracket"]`` yields a compound key feature
``"compound.Typology.Age_bracket"`` whose value on each row is the
separator-joined string of those fields (e.g. ``"SFH.pre_1975"``). That key is
what a joint distribution conditions on.

This generalizes the bespoke per-combination blocks in the MA
``make_building_priors`` (which hand-wrote one ``ConcatenateFeaturesSampler``
for each of Typology.Age_bracket, ...county, ...census_tract, etc.).
"""

from ..engine import ConcatenateFeaturesSampler, UnconditionalPrior

DEFAULT_SEPARATOR = "."
COMPOUND_PREFIX = "compound"


def compound_key_name(
    fields: list[str], *, prefix: str = COMPOUND_PREFIX, separator: str = DEFAULT_SEPARATOR
) -> str:
    """Return the canonical feature name for a compound key over ``fields``.

    Example: ``["Typology", "Age_bracket"]`` -> ``"compound.Typology.Age_bracket"``.
    The field names are joined by ``separator`` after the ``prefix``.
    """
    if len(fields) < 1:
        msg = "A compound key needs at least one field."
        raise ValueError(msg)
    return separator.join([prefix, *fields])


def make_compound_key(
    fields: list[str],
    *,
    prefix: str = COMPOUND_PREFIX,
    separator: str = DEFAULT_SEPARATOR,
) -> tuple[str, UnconditionalPrior]:
    """Build the (feature_name, prior) pair for a concatenated semantic field.

    Args:
        fields: Ordered field names to concatenate.
        prefix: Namespace prefix for the generated feature name.
        separator: Separator used both in the generated name and in the
            concatenated value string.

    Returns:
        A tuple ``(feature_name, prior)`` where ``prior`` is an
        ``UnconditionalPrior`` wrapping a ``ConcatenateFeaturesSampler``. Add it
        to a ``Priors`` before the joint distribution that conditions on it.
    """
    name = compound_key_name(fields, prefix=prefix, separator=separator)
    prior = UnconditionalPrior(
        sampler=ConcatenateFeaturesSampler(
            features_to_concatenate=list(fields),
            separator=separator,
        )
    )
    return name, prior
