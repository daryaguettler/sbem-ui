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

A construction's layers are the one list-of-objects field: the frontend sees
`[{ConstructionMaterial: <name>, Thickness: <m>}, ...]`, outside layer first, and
they are written as nested layer rows (LayerOrder = position).

Fields that aren't Prisma columns (the metadata/cost fields epinterface keeps in
separate tables) are left out of forms and writes.
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


def _layer_material_type(annotation: Any, type_map: dict[str, type]) -> str | None:
    """'ConstructionMaterial' for a list of layer models (ConstructionAssembly.Layers), else None."""
    if get_origin(annotation) is not list:
        return None
    (item,) = get_args(annotation) or (None,)
    fields = getattr(item, "model_fields", {})
    if "ConstructionMaterial" not in fields or "Thickness" not in fields:
        return None
    return _relation_type_name(_strip_optional(fields["ConstructionMaterial"].annotation), type_map)


def _layers_field(component_type: str) -> str | None:
    """The name of the type's layers field, if it has one."""
    type_map = _component_type_map()
    for name, info in type_map[component_type].model_fields.items():
        if _layer_material_type(_strip_optional(info.annotation), type_map):
            return name
    return None


def _prisma_fields(component_type: str) -> set[str]:
    """Columns and relations the Prisma model actually has."""
    import prisma.models

    return set(getattr(prisma.models, component_type).model_fields)


def _field_descriptor(name: str, info: Any, type_map: dict[str, type]) -> dict[str, Any]:
    annotation = _strip_optional(info.annotation)
    required = info.is_required()
    base = {"name": name, "title": name, "required": required}

    relation_type = _relation_type_name(annotation, type_map)
    if relation_type is not None:
        return {**base, "kind": "relation", "relationType": relation_type}

    material_type = _layer_material_type(annotation, type_map)
    if material_type is not None:
        return {**base, "kind": "layers", "relationType": material_type}

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

    columns = _prisma_fields(component_type)
    fields = [
        _field_descriptor(name, info, type_map)
        for name, info in cls.model_fields.items()
        if name != "id" and name in columns
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
        annotation = _strip_optional(cls.model_fields[key].annotation)
        relation_type = _relation_type_name(annotation, type_map)
        if relation_type is not None and isinstance(value, dict):
            filtered[key] = _pydantic_fields_only(relation_type, value)
        elif _layer_material_type(annotation, type_map) and isinstance(value, list):
            filtered[key] = [
                {"ConstructionMaterial": (layer.get("ConstructionMaterial") or {}).get("Name"), "Thickness": layer["Thickness"]}
                for layer in sorted(value, key=lambda layer: layer["LayerOrder"])
            ]
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
    if deep:
        # epinterface's own deep read: only declared fields, at every level (incl. layers)
        return _component_type_map()[component_type].model_validate(record, from_attributes=True).model_dump()
    return _flatten_relations_to_names(_pydantic_fields_only(component_type, record.model_dump(exclude={"id"})))


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
        material_type = _layer_material_type(annotation, type_map)
        if material_type is not None and isinstance(payload.get(name), list):
            hydrated[name] = [
                _hydrate_layer(layer, index, material_type, client) for index, layer in enumerate(payload[name])
            ]
            continue
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


def _hydrate_layer(layer: Any, index: int, material_type: str, client: Prisma) -> dict[str, Any]:
    """`{ConstructionMaterial: name, Thickness}` -> the nested layer epinterface validates."""
    if not isinstance(layer, dict) or not layer.get("ConstructionMaterial"):
        raise ValueError(f"Layer {index + 1}: choose a material.")
    material = get_record(client, material_type, layer["ConstructionMaterial"], deep=True)
    if material is None:
        raise LookupError(f"Layer {index + 1}: material {layer['ConstructionMaterial']!r} does not exist.")
    return {"LayerOrder": index, "Thickness": layer.get("Thickness"), "ConstructionMaterial": material}


#: Links epinterface types as optional but globi can't build a zone without.
REQUIRED_LINKS = {"ConditioningSystems": ("Heating", "Cooling"), "Envelope": ("Window",)}


def _validate_payload(component_type: str, payload: dict[str, Any], client: Prisma) -> Any:
    type_map = _component_type_map()
    cls = type_map.get(component_type)
    if cls is None:
        raise ValueError(f"Unknown component type: {component_type!r}")
    for link in REQUIRED_LINKS.get(component_type, ()):
        if not payload.get(link):
            raise ValueError(
                f"{link}: choose a record. globi can't build a zone with an empty {link}; "
                f"for no {link.lower()}, pick a record that is switched off."
            )
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
    data = _to_prisma_write_data(component_type, validated, client)
    existing = _client_accessor(client, component_type).find_unique(where={"Name": name})
    if existing is None:
        raise LookupError(f"{component_type} record {name!r} not found.")
    with client.tx() as tx:
        if _layers_field(component_type):
            # layer rows are unique per (assembly, LayerOrder): replace them, don't merge
            tx.constructionassemblylayer.delete_many(where={"ConstructionAssemblyId": existing.id})
        record = _client_accessor(tx, component_type).update(where={"Name": name}, data=data)
    return get_record(client, component_type, record.Name) or {}


def delete_record(client: Prisma, component_type: str, name: str) -> None:
    accessor = _client_accessor(client, component_type)
    existing = accessor.find_unique(where={"Name": name})
    if existing is None:
        raise LookupError(f"{component_type} record {name!r} not found.")
    with client.tx() as tx:
        if _layers_field(component_type):
            tx.constructionassemblylayer.delete_many(where={"ConstructionAssemblyId": existing.id})
        _client_accessor(tx, component_type).delete(where={"Name": name})


def _to_prisma_write_data(component_type: str, validated: Any, client: Prisma) -> dict[str, Any]:
    """Flatten a validated component model into Prisma create/update kwargs:
    scalars pass straight through, a relation field is written as its foreign
    key column (e.g. Schedule -> ScheduleId) pointing at the existing related
    record (which must already exist -- the frontend's relation picker only
    ever offers existing records or a "create new" detour that creates one
    first)."""
    type_map = _component_type_map()
    cls = type_map[component_type]
    columns = _prisma_fields(component_type)
    data: dict[str, Any] = {}
    for name, info in cls.model_fields.items():
        if name not in validated.__class__.model_fields or name not in columns:
            continue
        value = getattr(validated, name)
        annotation = _strip_optional(info.annotation)
        if _layer_material_type(annotation, type_map):
            data[name] = {
                "create": [
                    {
                        "LayerOrder": layer.LayerOrder,
                        "Thickness": layer.Thickness,
                        "ConstructionMaterial": {"connect": {"Name": layer.ConstructionMaterial.Name}},
                    }
                    for layer in value
                ]
            }
            continue
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


# -- a construction for a target U-value ---------------------------------------------

INSULATION = "Mineral Wool"
#: Layers (outside first) a target-U construction is built around; None is the insulation,
#: sized so the construction reaches the U-value.
CONSTRUCTION_BASES: dict[str, list[tuple[str, float] | None]] = {
    "Facade": [("Brick", 0.1), None, ("Gypsum Board", 0.013)],
    "FlatRoof": [("Concrete", 0.15), None, ("Gypsum Board", 0.013)],
    "AtticRoof": [("Concrete", 0.15), None, ("Gypsum Board", 0.013)],
    "GroundSlab": [("Concrete", 0.15), None],
    "GroundWall": [("Concrete", 0.2), None],
    "Partition": [("Gypsum Board", 0.013), None, ("Gypsum Board", 0.013)],
}
DEFAULT_BASE: list[tuple[str, float] | None] = [("Concrete", 0.1), None, ("Gypsum Board", 0.013)]
MAX_INSULATION = 1.0


def construction_for_u(client: Prisma, name: str, construction_type: str, u_value: float) -> dict[str, Any]:
    """Create a construction of `construction_type` whose U-value is `u_value` (W/m²K), by sizing
    an insulation layer in a typical stack. U is 1/Σ(thickness/conductivity) over the layers, as
    epinterface computes it. -> {record, u_value} with the U-value the layers actually reach."""
    if u_value <= 0:
        raise ValueError("The U-value has to be above 0.")
    base = CONSTRUCTION_BASES.get(construction_type, DEFAULT_BASE)
    conductivity = {}
    for material in {layer[0] for layer in base if layer} | {INSULATION}:
        record = get_record(client, "ConstructionMaterial", material)
        if record is None:
            raise LookupError(f"The library has no {material!r} material to build the construction from.")
        conductivity[material] = record["Conductivity"]
    fixed = sum(thickness / conductivity[material] for material, thickness in (layer for layer in base if layer))
    insulation = round(min(max(conductivity[INSULATION] * (1 / u_value - fixed), 0.0), MAX_INSULATION), 3)
    layers = [
        {"ConstructionMaterial": INSULATION, "Thickness": insulation} if layer is None else {"ConstructionMaterial": layer[0], "Thickness": layer[1]}
        for layer in base
        if layer is not None or insulation > 0
    ]
    record = create_record(client, "ConstructionAssembly", {"Name": name, "Type": construction_type, "Layers": layers})
    reached = 1 / (fixed + insulation / conductivity[INSULATION])
    return {"record": record, "u_value": round(reached, 3)}


# -- a schedule as one component ---------------------------------------------------
# A Year links 12 Weeks, each Week 7 Days. The editor works on one draft:
#   {Name, Type, Limit, profiles: {profile: [24 values]}, weeks: {week: {weekday: profile}},
#    months: {month: week}}
# and saves its Days/Weeks as "{Year}__{profile}" / "{Year}__{week}", so editing one schedule
# never changes another that shared the old Day/Week records.

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
SEP = "__"


def get_schedule(client: Prisma, name: str) -> dict[str, Any] | None:
    year = get_record(client, "Year", name, deep=True)
    if year is None:
        return None

    def labeller():
        """Record name -> editor label: "{Year}__x" -> "x"; others keep their name, made unique and __-free."""
        labels: dict[str, str] = {}

        def label(record_name: str) -> str:
            if record_name not in labels:
                short = record_name.removeprefix(f"{name}{SEP}").replace(SEP, "_")
                while short in labels.values():
                    short += "'"
                labels[record_name] = short
            return labels[record_name]

        return label

    day_label, week_label = labeller(), labeller()
    profiles: dict[str, list[float]] = {}
    weeks: dict[str, dict[str, str]] = {}
    for month in MONTHS:
        week = year[month]
        for day_name in DAYS:
            day = week[day_name]
            profiles.setdefault(day_label(day["Name"]), [day[f"Hour_{h:02d}"] for h in range(24)])
        weeks.setdefault(week_label(week["Name"]), {d: day_label(week[d]["Name"]) for d in DAYS})
    return {
        "Name": name,
        "Type": year["Type"],
        "Limit": year["January"]["Monday"]["Type"],
        "profiles": profiles,
        "weeks": weeks,
        "months": {m: week_label(year[m]["Name"]) for m in MONTHS},
    }


def _schedule_components(draft: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], Any]:
    """Validate the draft through epinterface's own models -> (days, weeks, year)."""
    from epinterface.sbem.components.schedules import DayComponent, WeekComponent, YearComponent

    name = (draft.get("Name") or "").strip()
    if not name:
        raise ValueError("Give the schedule a name.")
    for label in [*draft["profiles"], *draft["weeks"]]:
        if not label.strip() or SEP in label:
            raise ValueError(f"{label!r}: profile and week names can't be empty or contain {SEP!r}.")
    days = {}
    for label, values in draft["profiles"].items():
        if len(values) != 24:
            raise ValueError(f"Profile {label!r} needs 24 hourly values, not {len(values)}.")
        try:
            days[label] = DayComponent(
                Name=f"{name}{SEP}{label}", Type=draft["Limit"], **{f"Hour_{h:02d}": v for h, v in enumerate(values)}
            )
        except ValueError as exc:
            raise ValueError(f"Profile {label!r}: {exc}") from exc
    weeks = {}
    for label, pattern in draft["weeks"].items():
        missing = [d for d in DAYS if pattern.get(d) not in days]
        if missing:
            raise ValueError(f"Week {label!r}: choose a profile for {', '.join(missing)}.")
        weeks[label] = WeekComponent(Name=f"{name}{SEP}{label}", **{d: days[pattern[d]] for d in DAYS})
    missing = [m for m in MONTHS if draft["months"].get(m) not in weeks]
    if missing:
        raise ValueError(f"Choose a week for {', '.join(missing)}.")
    year = YearComponent(Name=name, Type=draft["Type"], **{m: weeks[draft["months"][m]] for m in MONTHS})
    return days, weeks, year


def save_schedule(client: Prisma, draft: dict[str, Any], old_name: str | None = None) -> dict[str, Any]:
    """Create (old_name None) or replace the schedule `old_name`, renaming it to draft["Name"]."""
    days, weeks, year = _schedule_components(draft)
    clash = client.year.find_unique(where={"Name": year.Name})
    if clash is not None and year.Name != old_name:
        raise ValueError(f"A schedule named {year.Name!r} already exists.")
    existing = client.year.find_unique(where={"Name": old_name}) if old_name else None
    if old_name and existing is None:
        raise LookupError(f"Schedule {old_name!r} not found.")

    with client.tx() as tx:
        for component_type, components in (("Day", days), ("Week", weeks)):
            for component in components.values():
                data = _to_prisma_write_data(component_type, component, tx)
                _client_accessor(tx, component_type).upsert(
                    where={"Name": component.Name}, data={"create": data, "update": data}
                )
        data = _to_prisma_write_data("Year", year, tx)
        if existing is None:
            tx.year.create(data=data)
        else:
            tx.year.update(where={"id": existing.id}, data=data)
        # drop this schedule's own Days/Weeks the draft no longer uses (incl. those of its old name)
        for component_type, keep in (("Week", weeks.values()), ("Day", days.values())):
            kept = {c.Name for c in keep}
            for prefix in {f"{n}{SEP}" for n in (year.Name, old_name) if n}:
                stale = [
                    r.Name
                    for r in _client_accessor(tx, component_type).find_many(where={"Name": {"startswith": prefix}})
                    if r.Name not in kept and SEP not in r.Name.removeprefix(prefix)
                ]
                if stale:
                    _client_accessor(tx, component_type).delete_many(where={"Name": {"in": stale}})
    return get_schedule(client, year.Name) or {}
