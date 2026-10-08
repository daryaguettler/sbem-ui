"""Component library: CRUD over the real epinterface component types, persisted
into the workspace's Prisma-backed components-lib.db.

Forms are generated field-by-field from the real epinterface Pydantic models
(get_component_type_schema) rather than hand-coded per type, so every component
type epinterface defines -- today and in the future -- is automatically
editable with zero sbem-ui code changes.

Relations (e.g. Lighting.Schedule -> a named Year record) are represented to
the frontend as a plain string: the related record's Name. On write, that name
is resolved and deep-hydrated into the full nested object epinterface's
pydantic model expects before validation, then flattened back down to just the
foreign-key id for the Prisma write (see _hydrate_relations/_to_prisma_data).
"""

import enum
import types
import typing
from typing import Any, get_args, get_origin

_UNION_ORIGINS = (typing.Union, types.UnionType)

from prisma import Prisma


def _component_type_map() -> dict[str, type]:
    """{"Lighting": LightingComponent, "Year": YearComponent, ...} -- every
    dict-valued field on ComponentLibrary except the four shared metadata
    fields (Category/Comment/DataSource/Version)."""
    from epinterface.sbem.interface import ComponentLibrary

    mapping: dict[str, type] = {}
    for name, info in ComponentLibrary.model_fields.items():
        args = get_args(info.annotation)
        if len(args) == 2 and args[0] is str and isinstance(args[1], type):
            mapping[name] = args[1]
    return mapping


def _include_map() -> dict[str, Any]:
    """{"Lighting": LIGHTING_INCLUDE, ...} -- epinterface's own pre-built deep
    `include` dicts, so a fetched record comes back with all of its relations
    (recursively) already populated, matching what its pydantic model expects."""
    from epinterface.sbem.prisma import client as prisma_client_module

    return {
        "Operations": prisma_client_module.OPERATIONS_INCLUDE,
        "SpaceUse": prisma_client_module.SPACE_USE_INCLUDE,
        "Occupancy": prisma_client_module.OCCUPANCY_INCLUDE,
        "Lighting": prisma_client_module.LIGHTING_INCLUDE,
        "Equipment": prisma_client_module.EQUIPMENT_INCLUDE,
        "Thermostat": prisma_client_module.THERMOSTAT_INCLUDE,
        "WaterUse": prisma_client_module.WATER_USE_INCLUDE,
        "HVAC": prisma_client_module.HVAC_INCLUDE,
        "ConditioningSystems": prisma_client_module.CONDITIONING_SYSTEMS_INCLUDE,
        "ThermalSystem": prisma_client_module.THERMAL_SYSTEM_INCLUDE,
        "Ventilation": prisma_client_module.VENTILATION_INCLUDE,
        "DHW": prisma_client_module.DHW_INCLUDE,
        "Envelope": prisma_client_module.ENVELOPE_INCLUDE,
        "GlazingConstructionSimple": prisma_client_module.GLAZING_CONSTRUCTION_SIMPLE_INCLUDE,
        "Infiltration": prisma_client_module.INFILTRATION_INCLUDE,
        "EnvelopeAssembly": prisma_client_module.ENVELOPE_ASSEMBLY_INCLUDE,
        "ConstructionAssembly": prisma_client_module.CONSTRUCTION_ASSEMBLY_INCLUDE,
        "Year": prisma_client_module.YEAR_INCLUDE,
        "Week": prisma_client_module.WEEK_INCLUDE,
    }


def _include_for(component_type: str) -> Any:
    include = _include_map().get(component_type)
    return include or None


def list_component_types() -> list[str]:
    return sorted(_component_type_map().keys())


def _strip_optional(annotation: Any) -> Any:
    """Unwrap Optional[...]/Annotated[...] down to the "real" underlying type.

    `X | None` (PEP 604) and `Optional[X]`/`Union[X, None]` produce different
    get_origin() results (types.UnionType vs typing.Union) -- both need
    handling, since epinterface's models mix both styles."""
    origin = get_origin(annotation)
    if origin in _UNION_ORIGINS:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return _strip_optional(args[0])
        return annotation
    if hasattr(annotation, "__metadata__"):  # typing.Annotated
        return _strip_optional(get_args(annotation)[0])
    return annotation


def _relation_type_name(annotation: Any, type_map: dict[str, type]) -> str | None:
    for type_name, cls in type_map.items():
        if annotation is cls:
            return type_name
    return None


def _field_descriptor(name: str, info: Any, type_map: dict[str, type]) -> dict[str, Any]:
    annotation = _strip_optional(info.annotation)
    required = info.is_required()
    base = {"name": name, "title": name, "required": required}

    relation_type = _relation_type_name(annotation, type_map)
    if relation_type is not None:
        return {**base, "kind": "relation", "relationType": relation_type}

    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return {**base, "kind": "enum", "options": [member.value for member in annotation]}

    origin = get_origin(annotation)
    if origin is typing.Literal:
        return {**base, "kind": "enum", "options": list(get_args(annotation))}

    if annotation is bool:
        return {**base, "kind": "boolean"}

    if annotation in (int, float):
        descriptor = {**base, "kind": "number"}
        for meta in getattr(info, "metadata", []):
            for attr in ("ge", "gt", "le", "lt"):
                value = getattr(meta, attr, None)
                if value is not None:
                    descriptor[attr] = value
        return descriptor

    if annotation is str:
        return {**base, "kind": "string"}

    # Unknown/complex type (e.g. a raw dict, a not-yet-handled nested model) --
    # fall back to a raw JSON text field rather than crashing the schema call.
    return {**base, "kind": "raw"}


def get_component_type_schema(component_type: str) -> dict[str, Any]:
    type_map = _component_type_map()
    cls = type_map.get(component_type)
    if cls is None:
        raise ValueError(f"Unknown component type: {component_type!r}")

    fields = [
        _field_descriptor(name, info, type_map)
        for name, info in cls.model_fields.items()
        if name != "id"
    ]
    return {"type": component_type, "fields": fields}


def _client_accessor(client: Prisma, component_type: str):
    return getattr(client, component_type.lower())


def _pydantic_fields_only(component_type: str, data: dict[str, Any]) -> dict[str, Any]:
    """Prisma's own record model_dump() includes reverse-relation fields (e.g.
    Infiltration.MainInfiltrations -- "which envelopes use this row") that
    aren't part of epinterface's InfiltrationComponent pydantic model at all.
    The component models use `extra="forbid"`, so these MUST be stripped
    (recursively, into every nested relation) before model_validate(), not
    just at the top level -- otherwise validating a hydrated Lighting payload
    whose nested Year carries Prisma's own back-references raises."""
    type_map = _component_type_map()
    cls = type_map[component_type]
    known = set(cls.model_fields.keys())
    filtered: dict[str, Any] = {}
    for key, value in data.items():
        if key not in known:
            continue
        relation_type = _relation_type_name(_strip_optional(cls.model_fields[key].annotation), type_map)
        if relation_type is not None and isinstance(value, dict):
            filtered[key] = _pydantic_fields_only(relation_type, value)
        else:
            filtered[key] = value
    return filtered


def _record_to_summary(component_type: str, record: Any) -> dict[str, Any]:
    """A shallow {Name, ...scalars} view for list screens -- relation fields
    are surfaced as just the related record's Name, not the full nested tree."""
    data = _pydantic_fields_only(component_type, record.model_dump(exclude={"id"}))
    return _flatten_relations_to_names(data)


def _flatten_relations_to_names(data: dict[str, Any]) -> dict[str, Any]:
    """Shallow view for list/detail responses: a relation field's full nested
    object collapses to just the related record's Name (the frontend re-fetches
    that record's own detail on demand rather than receiving it inline)."""
    flattened: dict[str, Any] = {}
    for key, value in data.items():
        flattened[key] = value["Name"] if isinstance(value, dict) and "Name" in value else value
    return flattened


def list_records(client: Prisma, component_type: str) -> list[dict[str, Any]]:
    accessor = _client_accessor(client, component_type)
    records = accessor.find_many(include=_include_for(component_type))
    return [_record_to_summary(component_type, record) for record in records]


def get_record(client: Prisma, component_type: str, name: str, deep: bool = False) -> dict[str, Any] | None:
    accessor = _client_accessor(client, component_type)
    record = accessor.find_unique(where={"Name": name}, include=_include_for(component_type))
    if record is None:
        return None
    data = _pydantic_fields_only(component_type, record.model_dump(exclude={"id"}))
    return data if deep else _flatten_relations_to_names(data)


def check_existence(client: Prisma, component_type: str, names: list[str]) -> dict[str, bool]:
    accessor = _client_accessor(client, component_type)
    if not names:
        return {}
    existing = accessor.find_many(where={"Name": {"in": names}})
    existing_names = {record.Name for record in existing}
    return {name: name in existing_names for name in names}


def _hydrate_relations(component_type: str, payload: dict[str, Any], client: Prisma) -> dict[str, Any]:
    """Replace each relation field's plain Name string with the full nested
    object its related record resolves to, so the payload validates against
    epinterface's pydantic model (which expects real nested objects, not FK
    names -- that's a Prisma-level detail, not a pydantic one)."""
    type_map = _component_type_map()
    cls = type_map[component_type]
    hydrated = dict(payload)
    for name, info in cls.model_fields.items():
        annotation = _strip_optional(info.annotation)
        relation_type = _relation_type_name(annotation, type_map)
        if relation_type is None or name not in payload:
            continue
        value = payload[name]
        if not isinstance(value, str):
            continue  # already a full object (e.g. round-tripped from get_record(deep=True))
        related = get_record(client, relation_type, value, deep=True)
        if related is None:
            msg = f"Related {relation_type} record {value!r} does not exist."
            raise LookupError(msg)
        hydrated[name] = related
    return hydrated


def _validate_payload(component_type: str, payload: dict[str, Any], client: Prisma) -> Any:
    type_map = _component_type_map()
    cls = type_map.get(component_type)
    if cls is None:
        raise ValueError(f"Unknown component type: {component_type!r}")
    hydrated = _hydrate_relations(component_type, payload, client)
    return cls.model_validate(hydrated)


def create_record(client: Prisma, component_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    validated = _validate_payload(component_type, payload, client)
    accessor = _client_accessor(client, component_type)
    record = accessor.create(data=_to_prisma_write_data(component_type, validated, client))
    return get_record(client, component_type, record.Name) or {}


def update_record(
    client: Prisma, component_type: str, name: str, payload: dict[str, Any]
) -> dict[str, Any]:
    validated = _validate_payload(component_type, payload, client)
    accessor = _client_accessor(client, component_type)
    record = accessor.update(
        where={"Name": name}, data=_to_prisma_write_data(component_type, validated, client)
    )
    if record is None:
        raise LookupError(f"{component_type} record {name!r} not found.")
    return get_record(client, component_type, record.Name) or {}


def delete_record(client: Prisma, component_type: str, name: str) -> None:
    accessor = _client_accessor(client, component_type)
    accessor.delete(where={"Name": name})


def _to_prisma_write_data(component_type: str, validated: Any, client: Prisma) -> dict[str, Any]:
    """Flatten a validated component model into Prisma create/update kwargs:
    scalars pass straight through, a relation field is written as its foreign
    key column (e.g. Schedule -> ScheduleId) pointing at the existing related
    record (which must already exist -- the frontend's relation picker only
    ever offers existing records or a "create new" detour that creates one
    first)."""
    type_map = _component_type_map()
    cls = type_map[component_type]
    data: dict[str, Any] = {}
    for name, info in cls.model_fields.items():
        if name not in validated.__class__.model_fields:
            continue
        value = getattr(validated, name)
        annotation = _strip_optional(info.annotation)
        relation_type = _relation_type_name(annotation, type_map)
        if relation_type is not None:
            if value is None:
                continue
            related_accessor = _client_accessor(client, relation_type)
            related_record = related_accessor.find_unique(where={"Name": value.Name})
            if related_record is None:
                msg = f"Related {relation_type} record {value.Name!r} does not exist."
                raise LookupError(msg)
            data[f"{name}Id"] = related_record.id
            continue
        if value is not None:
            data[name] = value
    return data
