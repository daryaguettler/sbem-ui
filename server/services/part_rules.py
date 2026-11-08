"""Part rules: what the user decides for each part of the energy model, compiled into the
files globi reads.

Each leaf part (walls, lighting, heating, ...) has a rule: the characteristics it depends
on, a default option, and the option for each combination of their values that differs. An
option is an existing library record of the part's type, so Office and Hospital can share one
lighting record without a copy. Rules are saved in part-rules.yaml; the component map and the
records globi looks up by name are build outputs, rewritten by every compile:

- one selector per group (Envelope, SpaceUse, HVAC, DHW) over the union of its parts'
  characteristics, with a prefix so generated names never meet the user's records;
- per combination, a group record pointing at the chosen options by foreign key, plus the
  EnvelopeAssembly / ConditioningSystems under it (identical ones are shared);
- DHW sits directly under Operations, so it gets a key-named copy of its option.

Retrofit packages compile into a generated Scenario characteristic: a group whose parts depend
on a characteristic a package changes also varies by Scenario, and its rows for a package point
at the options the retrofitted values pick. globi sets Scenario from each manifest.

Components with priors (component-priors.yaml) compile into variants: n records
`auto_<component>__1..n`, one per stratified point of their curves. A part using one also
depends on a generated variant-index characteristic (`<part>_variant`, values 1..L) that
Sampling draws evenly; index k picks variant ceil(k·n/L), so components with different n keep
equal weights and every component keeps the building's rank (under retrofits too). Parts
linked to move together share one index field; correlated ones keep their own, and Sampling
draws them jointly.

A package can also act on a part directly: replace its component (`{part, to}`, fixed or
uncertain), or shift one of its numbers (`{part, number, op, value}`, op scale / add /
at_most / at_least). A shifted part gets `<its option>__<package>` records, variant by variant,
so a building keeps its draw from the curve.
"""

from __future__ import annotations

import functools
import hashlib
import itertools
import json
import math
import operator
import re
import uuid
from collections import Counter
from typing import Any, Callable

import yaml

from services import component_library as lib
from services import component_priors
from services.globi_component_map import (
    SCENARIO,
    _selectors,
    building_contexts,
    to_globi,
)

GROUPS = ("Envelope", "Operations.SpaceUse", "Operations.HVAC", "Operations.DHW")
#: Generated record names start with this; compiles delete and rewrite exactly these.
PREFIX = "auto"
#: Comes from `assembly_base` rather than a rule: it needs an area that lives on the assembly.
INTERNAL_MASS = "Envelope.Assemblies.InternalMassAssembly"
#: Above this many combinations a group uses the ones the buildings have, not every one.
MAX_PRODUCT = 5_000
BASELINE = "Baseline"
GENERATED_NOTE = "Generated from retrofits.yaml: Baseline plus one value per retrofit package."
VARIANT_NOTE = "Generated from component-priors.yaml: which variant of an uncertain component a building draws."
GENERATED_NOTES = (GENERATED_NOTE, VARIANT_NOTE)
VARIANT_SUFFIX = "_variant"
#: Most variant-index values one part may need (the lcm of its components' n).
MAX_LEVELS = 120


class PartRulesError(Exception):
    """The rules can't be compiled yet; the message says what to fix."""


@functools.cache
def _tree() -> dict[str, dict[str, Any]]:
    from services.component_tree import get_component_tree

    return {node["path"]: node for node in get_component_tree()["nodes"]}


def _children(path: str) -> list[str]:
    tree = _tree()
    return [child for child in tree[path]["children"] if tree[child]["componentType"] != "Year"]


def parts() -> list[str]:
    """Every leaf part a rule decides, in tree order."""
    out = []
    for group in GROUPS:
        stack = [group]
        while stack:
            path = stack.pop(0)
            children = _children(path)
            if not children and path != INTERNAL_MASS:
                out.append(path)
            stack = children + stack
    return out


def _group_of(part: str) -> str:
    return next(g for g in GROUPS if part == g or part.startswith(g + "."))


def _type(path: str) -> str:
    return _tree()[path]["componentType"]


def key(values: list[str]) -> str:
    return "|".join(values)


def option_for(rule: dict[str, Any], values: dict[str, str]) -> str | None:
    cells = rule.get("cells") or {}
    return cells.get(key([values[field] for field in rule.get("depends_on") or []]), rule.get("default"))


# -- retrofits -------------------------------------------------------------------


def _conditions(measure: dict[str, Any]) -> list[dict[str, Any]]:
    when = measure.get("when") or []
    return when if isinstance(when, list) else [when]


def _holds(measure: dict[str, Any], values: dict[str, str]) -> bool:
    return all(
        values.get(c["field"]) in c["in"] if "in" in c else values.get(c["field"]) not in c.get("not_in", [])
        for c in _conditions(measure)
    )


def apply_package(values: dict[str, str], package: dict[str, Any], upgrade_order: dict[str, list[str]]) -> dict[str, str]:
    """A combination's values after a retrofit package's measures, in order; never a downgrade."""
    out = dict(values)
    for measure in package.get("measures") or []:
        field = measure.get("field")
        if field not in out:  # also every part measure
            continue
        new = measure.get("to") or (measure.get("map") or {}).get(out[field])
        order = upgrade_order.get(field) or []
        if not _holds(measure, out) or new is None or (new in order and out[field] in order and order.index(new) < order.index(out[field])):
            continue
        out[field] = new
    return out


#: How a part measure shifts a number: U × 0.5, COP + 0.5, or "at most U 0.25" (never worse).
SHIFTS: dict[str, Callable[[float, float], float]] = {"scale": operator.mul, "add": operator.add, "at_most": min, "at_least": max}


def _package_slug(name: str) -> str:
    return re.sub(r"\W+", "-", name).strip("-")


# -- reading the library ------------------------------------------------------------


class _Library:
    """Cached lookups on one connected Prisma client."""

    def __init__(self, db):
        self.db = db
        self._flat: dict[tuple[str, str], dict[str, Any] | None] = {}
        self._ids: dict[str, dict[str, str]] = {}
        #: Variant records queued this compile, by name; not in the database yet.
        self.variant_rows: dict[str, dict[str, Any]] = {}
        #: Each variant's source record and the numbers set on it.
        self.variant_values: dict[str, tuple[str, dict[str, float]]] = {}
        self._conductivity: dict[str, float] | None = None

    def conductivity(self) -> dict[str, float]:
        if self._conductivity is None:
            self._conductivity = {m["Name"]: m["Conductivity"] for m in lib.list_records(self.db, "ConstructionMaterial")}
        return self._conductivity

    def queue_variant(self, component_type: str, name: str, source: str, values: dict[str, float], rows) -> None:
        """Queue record `name`: `source` with `values` in place (component_priors.variant_record)."""
        payload = component_priors.variant_record(component_type, self.record(component_type, source), values, self.conductivity())
        validated = lib._validate_payload(component_type, {**payload, "Name": name}, self.db)
        row = {**lib._to_prisma_write_data(component_type, validated, self.db), "id": str(uuid.uuid4())}
        rows.append((component_type, row))
        self.ids(component_type)[name] = row["id"]
        self.variant_rows[name] = row
        self.variant_values[name] = (source, values)

    def record(self, component_type: str, name: str) -> dict[str, Any] | None:
        if (component_type, name) not in self._flat:
            self._flat[(component_type, name)] = lib.get_record(self.db, component_type, name)
        return self._flat[(component_type, name)]

    def ids(self, component_type: str) -> dict[str, str]:
        if component_type not in self._ids:
            accessor = lib._client_accessor(self.db, component_type)
            self._ids[component_type] = {r.Name: r.id for r in accessor.find_many()}
        return self._ids[component_type]

    def child(self, owner: str, name: str, path: str) -> str | None:
        """The record `path` gets inside `owner`'s record `name` (walking flat records)."""
        current_type, current = _type(owner), name
        walked = owner
        for segment in path[len(owner) + 1 :].split(".") if path != owner else []:
            record = self.record(current_type, current) if current else None
            current = (record or {}).get(segment)
            walked = f"{walked}.{segment}"
            current_type = _type(walked)
        return current


def baseline(db) -> dict[str, Any]:
    """Rules where every part depends on nothing and takes its option from the library's first
    complete archetype (its first Envelope, SpaceUse, HVAC and DHW record), so a new project runs
    before any decision. Parts the library has no archetype for are left without a rule."""
    library = _Library(db)
    roots: dict[str, str | None] = {}
    for group in GROUPS:
        names = sorted(n for n in library.ids(_type(group)) if not n.startswith(f"{PREFIX}_"))
        roots[group] = names[0] if names else None
    rules = {}
    for part in parts():
        root = roots[_group_of(part)]
        option = library.child(_group_of(part), root, part) if root else None
        if option:
            rules[part] = {"depends_on": [], "default": option, "cells": {}}
    envelope = roots["Envelope"]
    return {"assembly_base": library.child("Envelope", envelope, "Envelope.Assemblies") if envelope else None, "parts": rules}


def infer(component_map: dict[str, Any], semantic_fields: dict[str, Any], db) -> tuple[dict[str, Any], list[str]]:
    """Rules from an existing map and library: each part keeps the record its selector finds per
    combination, and depends only on the fewest characteristics that decide it. -> (rules, notes)"""
    from epinterface.sbem.components.composer import ComponentNameConstructor

    options = {f["Name"]: [str(o) for o in f.get("Options") or []] for f in semantic_fields.get("Fields") or []}
    selectors = dict(_selectors(component_map))
    library = _Library(db)
    rules: dict[str, Any] = {}
    notes: list[str] = []
    assembly_base = None
    for part in parts():
        owner = next((p for p in sorted(selectors, key=len, reverse=True) if part == p or part.startswith(p + ".")), None)
        if owner is None:
            notes.append(f"{part}: nothing in the map chose it.")
            continue
        selector = selectors[owner]
        fields = list(selector.get("source_fields") or [])
        unknown = [f for f in fields if f not in options]
        if unknown:
            notes.append(f"{part}: the map uses {', '.join(unknown)}, which isn't a characteristic.")
            continue
        combos = list(itertools.product(*(options[f] for f in fields)))
        if len(combos) > MAX_PRODUCT:
            notes.append(f"{part}: {len(combos):,} combinations is too many to import.")
            continue
        namer = ComponentNameConstructor.model_validate(selector)
        names = {namer.construct_name(dict(zip(fields, combo))): combo for combo in combos}
        existing = library.ids(_type(owner))
        rows = {}
        for name, combo in names.items():
            if name in existing:
                option = library.child(owner, name, part)
                if option:
                    rows[combo] = option
                if assembly_base is None and part.startswith("Envelope.Assemblies."):
                    assembly_base = library.child(owner, name, "Envelope.Assemblies") if owner != part else None
        if not rows:
            notes.append(f"{part}: none of the records its selector names exist.")
            continue
        if len(rows) < len(combos):
            notes.append(f"{part}: {len(combos) - len(rows)} combination(s) had no record and now use the default.")
        varying = [i for i, f in enumerate(fields) if len(options[f]) > 1]
        deps = next(
            subset
            for size in range(len(varying) + 1)
            for subset in itertools.combinations(varying, size)
            if _decides(rows, subset)
        )
        table = {key([combo[i] for i in deps]): option for combo, option in rows.items()}
        default = Counter(table.values()).most_common(1)[0][0]
        rules[part] = {
            "depends_on": [fields[i] for i in deps],
            "default": default,
            "cells": {k: v for k, v in table.items() if v != default},
        }
    return {"assembly_base": assembly_base, "parts": rules}, notes


def _decides(rows: dict[tuple, str], subset: tuple[int, ...]) -> bool:
    seen: dict[tuple, str] = {}
    return all(seen.setdefault(tuple(combo[i] for i in subset), option) == option for combo, option in rows.items())


# -- compiling ------------------------------------------------------------------------


def _ordered(names: set[str], field_order: list[str]) -> list[str]:
    return [f for f in field_order if f in names]


def compile_rules(
    rules: dict[str, Any],
    semantic_fields: dict[str, Any],
    retrofits: dict[str, Any] | None,
    db,
    found: Callable[[], dict[str, Any]] | None = None,
    priors: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """-> {component_map, rows: [(type, row)] in write order, scenario: values | None,
    variants: {field: levels}, groups}

    `found` returns the buildings' combinations (`building_contexts`); it is only called for a
    group whose full product is too large."""
    library = _Library(db)
    rule_for = rules.get("parts") or {}
    user_fields = [f for f in semantic_fields.get("Fields") or [] if f.get("Description") not in GENERATED_NOTES]
    options = {f["Name"]: [str(o) for o in f.get("Options") or []] for f in user_fields}
    order = list(options)
    packages = (retrofits or {}).get("packages") or []
    upgrade_order = (retrofits or {}).get("upgrade_order") or {}
    if packages and SCENARIO in options:
        raise PartRulesError("Rename your 'Scenario' characteristic: with retrofit packages, the app makes its own.")
    scenarios = [BASELINE] + [p["name"] for p in packages] if packages else None

    problems = []
    for part in parts():
        rule = rule_for.get(part)
        if not rule or not rule.get("default"):
            problems.append(f"{part}: choose an option.")
            continue
        for field in rule.get("depends_on") or []:
            if field not in options:
                problems.append(f"{part} depends on {field}, which isn't a saved characteristic yet.")
        for option in {rule["default"], *(rule.get("cells") or {}).values()}:
            if option not in library.ids(_type(part)):
                problems.append(f"{part}: option {option!r} isn't a {_type(part)} record.")
    for package in packages:
        for measure in package.get("measures") or []:
            part = measure.get("part")
            if part is None:
                continue
            where = f"{package['name']}: {part.split('.')[-1]}"
            if part not in rule_for:
                problems.append(f"{where} isn't a model part.")
            elif measure.get("to"):
                if measure["to"] not in library.ids(_type(part)):
                    problems.append(f"{where}: {measure['to']!r} isn't a {_type(part)} record.")
            elif measure.get("op") not in SHIFTS or not isinstance(measure.get("value"), (int, float)) or not measure.get("number"):
                problems.append(f"{where}: give a number, how to change it ({', '.join(SHIFTS)}) and by how much.")
    if problems:
        raise PartRulesError(" ".join(problems))

    rows: list[tuple[str, dict[str, Any]]] = []
    uncertain, part_variant = _variants(rule_for, (priors or {}).get("components") or {}, options, library, rows, packages)
    _link_together(part_variant, (priors or {}).get("links") or [], options)
    for field, levels in {v[0]: v[1] for v in part_variant.values()}.items():
        options[field] = [str(k) for k in range(1, levels + 1)]
        order.append(field)

    tree_map: dict[str, Any] = {}
    generated_ids: dict[str, dict[str, str]] = {}
    base = rules.get("assembly_base")
    base_assembly = library.record("EnvelopeAssembly", base) if base else None
    summary = {}
    for group in GROUPS:
        group_parts = [p for p in parts() if _group_of(p) == group]
        deps = set().union(*(rule_for[p].get("depends_on") or [] for p in group_parts))
        deps |= {part_variant[p][0] for p in group_parts if p in part_variant}
        acting = [m for p in packages for m in p.get("measures") or [] if m.get("field") in deps or m.get("part") in group_parts]
        measured = bool(acting)
        deps |= {c["field"] for m in acting for c in _conditions(m) if c["field"] in options}
        fields = _ordered(deps, order)
        combos = _combinations(fields, options, found)
        if measured:
            combos = [(*combo, scenario) for combo in combos for scenario in scenarios]
        selector_fields = fields + [SCENARIO] if measured else fields
        node = tree_map
        for segment in group.split("."):
            node = node.setdefault(segment, {})
        node["selector"] = {"source_fields": selector_fields, "prefix": PREFIX}

        names_seen: dict[str, tuple] = {}
        for combo in combos:
            values = dict(zip(fields, combo))
            package = next((p for p in packages if p["name"] == combo[-1]), None) if measured else None
            if package:
                values = apply_package(values, package, upgrade_order)
            name = "_".join([PREFIX, "_".join(combo)])
            if names_seen.setdefault(name, combo) != combo:
                raise PartRulesError(
                    f"{' / '.join(combo)} and {' / '.join(names_seen[name])} give the same record name; "
                    "rename a value so they differ."
                )
            choice = {
                p: _part_measures(p, option_for(rule_for[p], values), values, package, uncertain, part_variant, library, rows)
                if package else _variant_of(p, option_for(rule_for[p], values), values, uncertain, part_variant)
                for p in group_parts
            }
            _build(group, name, choice, library, base_assembly, generated_ids, rows)
        summary[group] = {"fields": selector_fields, "combinations": len(combos)}
    variants = {field: levels for field, levels in part_variant.values()}
    return {"component_map": tree_map, "rows": rows, "scenario": scenarios, "variants": variants, "groups": summary}


def _variants(rule_for, components, options, library, rows, packages=()):
    """Queue the variant records of every uncertain component a rule (or a package's replace)
    uses, and give each part that uses one a variant-index field.
    -> ({(type, name): n}, {part: (field, levels)})"""
    uncertain: dict[tuple[str, str], int] = {}
    part_variant: dict[str, tuple[str, int]] = {}
    for part in parts():
        component_type = _type(part)
        rule = rule_for[part]
        replaced = {m["to"] for p in packages for m in p.get("measures") or [] if m.get("part") == part and m.get("to")}
        used = sorted({rule["default"], *(rule.get("cells") or {}).values(), *replaced} & set(components.get(component_type) or {}))
        if not used:
            continue
        for name in used:
            if (component_type, name) in uncertain:
                continue
            prior = components[component_type][name]
            try:
                for j, value in enumerate(component_priors.variants(name, prior), start=1):
                    library.queue_variant(component_type, f"{PREFIX}_{name}__{j}", name, value, rows)
            except (component_priors.PriorError, ValueError, LookupError) as exc:
                raise PartRulesError(f"{name}: {exc}") from exc
            uncertain[(component_type, name)] = prior["n"]
        field = variant_field(part)
        if field in options:
            raise PartRulesError(f"Rename your {field!r} characteristic: the app uses that name for {part}'s variants.")
        levels = math.lcm(*(uncertain[(component_type, name)] for name in used))
        if levels > MAX_LEVELS:
            raise PartRulesError(
                f"{part}: its uncertain components need {levels} variant levels together; "
                "give them the same n, or ns that divide each other."
            )
        part_variant[part] = (field, levels)
    return uncertain, part_variant


def variant_field(part: str) -> str:
    """The generated variant-index characteristic of a part (Envelope...FacadeAssembly -> FacadeAssembly_variant)."""
    return part.split(".")[-1] + VARIANT_SUFFIX


def _links(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The links, checked: each part in one link at most, and each a valid way to move together."""
    seen: set[str] = set()
    for link in links:
        how = link.get("link")
        names = " + ".join(link.get("parts") or [])
        if how != "together" and not (isinstance(how, (int, float)) and -1 < how < 1):
            raise PartRulesError(f"Link {names}: use together or a correlation between -1 and 1.")
        m = len(link.get("parts") or [])
        if how != "together" and m > 2 and how <= -1 / (m - 1):
            raise PartRulesError(f"Link {names}: {m} parts can't all be correlated at {how}; it has to be above {-1 / (m - 1):.2f}.")
        for part in link.get("parts") or []:
            if part in seen:
                raise PartRulesError(f"{part} is in two links; link it once, with every part it moves with.")
            seen.add(part)
    return links


def _link_together(part_variant: dict[str, tuple[str, int]], links: list[dict[str, Any]], options) -> None:
    """Parts linked to move together share one variant index, so variant k of each goes together."""
    for link in _links(links):
        members = [p for p in link.get("parts") or [] if p in part_variant]
        if link["link"] != "together" or len(members) < 2:
            continue
        field = "_".join(p.split(".")[-1] for p in members) + VARIANT_SUFFIX
        if field in options:
            raise PartRulesError(f"Rename your {field!r} characteristic: the app uses that name for linked variants.")
        levels = math.lcm(*(part_variant[p][1] for p in members))
        if levels > MAX_LEVELS:
            raise PartRulesError(f"{' + '.join(members)} need {levels} variant levels together; give their components the same n.")
        for part in members:
            part_variant[part] = (field, levels)


def correlated(priors: dict[str, Any], levels: dict[str, int]) -> list[tuple[list[str], float]]:
    """Variant-index fields to draw jointly, with their correlation, for Sampling."""
    groups = []
    for link in priors.get("links") or []:
        fields = [variant_field(p) for p in link.get("parts") or [] if variant_field(p) in levels]
        if isinstance(link.get("link"), (int, float)) and len(fields) > 1:
            groups.append((fields, float(link["link"])))
    return groups


def _variant_of(part, option, values, uncertain, part_variant):
    """The variant a combination's variant index picks, for an uncertain option."""
    n = uncertain.get((_type(part), option)) if part in part_variant else None
    if n is None:
        return option
    field, levels = part_variant[part]
    return f"{PREFIX}_{option}__{math.ceil(int(values[field]) * n / levels)}"


def _part_measures(part, option, values, package, uncertain, part_variant, library, rows):
    """The record a part ends on under a package's measures on it, in order: a replace swaps the
    option, a shift changes one of its numbers (on the variant the building drew)."""
    measures = package.get("measures") or []
    shifts: list[int] = []
    for i, measure in enumerate(measures):
        if measure.get("part") != part or not _holds(measure, values):
            continue
        if measure.get("to"):
            option, shifts = measure["to"], []
        else:
            shifts.append(i)
    chosen = _variant_of(part, option, values, uncertain, part_variant)
    if not shifts:
        return chosen
    stem = chosen if chosen.startswith(f"{PREFIX}_") else f"{PREFIX}_{chosen}"
    every = [i for i, m in enumerate(measures) if m.get("part") == part and not m.get("to")]
    name = f"{stem}__{_package_slug(package['name'])}" + ("" if shifts == every else "-" + "-".join(str(i + 1) for i in shifts))
    if name in library.variant_rows:
        return name
    component_type = _type(part)
    source, numbers = library.variant_values.get(chosen, (chosen, {}))
    numbers = dict(numbers)
    record = library.record(component_type, source)
    try:
        for i in shifts:
            number, op = measures[i]["number"], measures[i]["op"]
            if number not in numbers:
                numbers[number] = component_priors.u_value(record["Layers"], library.conductivity()) if number == component_priors.U else record.get(number)
            if not isinstance(numbers[number], (int, float)) or isinstance(numbers[number], bool):
                raise component_priors.PriorError(f"{component_type} has no number called {number!r}.")
            numbers[number] = SHIFTS[op](numbers[number], float(measures[i]["value"]))
        library.queue_variant(component_type, name, source, numbers, rows)
    except (component_priors.PriorError, ValueError, LookupError) as exc:
        raise PartRulesError(f"{package['name']}: {part.split('.')[-1]} ({source}): {exc}") from exc
    return name


def _combinations(fields: list[str], options: dict[str, list[str]], found) -> list[tuple]:
    size = 1
    for field in fields:
        size *= len(options[field])
    if size <= MAX_PRODUCT:
        return list(itertools.product(*(options[f] for f in fields)))
    found = found() if found else None
    if not found or not found.get("total"):
        raise PartRulesError(
            f"{' × '.join(fields)} make {size:,} combinations; save your buildings so only the ones they have are built."
        )
    # a field the buildings don't carry yet (a new variant index) expands over its options
    return sorted({combo for c in found["contexts"] for combo in itertools.product(*([c[f]] if f in c else options[f] for f in fields))})


def _build(path, name, choice, library, base_assembly, generated_ids, rows) -> str:
    """Queue the record for `path` (named `name` at a group root) and return its id."""
    component_type = _type(path)
    if path in choice:  # a leaf
        option = choice[path]
        if path not in GROUPS:
            return library.ids(component_type)[option]
        # DHW: globi looks the leaf itself up by the generated name
        source = library.variant_rows.get(option) or lib._client_accessor(library.db, component_type).find_unique(where={"Name": option}).model_dump()
        data = {k: v for k, v in source.items() if k not in ("id", "Name") and v is not None and not isinstance(v, (dict, list))}
        row = {"id": str(uuid.uuid4()), "Name": name, **data}
        rows.append((component_type, row))
        return row["id"]
    row: dict[str, Any] = {}
    for child in _children(path):
        if child == INTERNAL_MASS:
            continue
        row[f"{child.split('.')[-1]}Id"] = _build(child, None, choice, library, base_assembly, generated_ids, rows)
    if component_type == "EnvelopeAssembly" and base_assembly:
        row["InternalMassExposedAreaPerArea"] = base_assembly.get("InternalMassExposedAreaPerArea")
        if base_assembly.get("InternalMassAssembly"):
            row["InternalMassAssemblyId"] = library.ids("ConstructionAssembly")[base_assembly["InternalMassAssembly"]]
    if name is None:  # shared by every combination with the same children
        digest = hashlib.sha1(json.dumps(row, sort_keys=True).encode()).hexdigest()[:12]
        name = f"{PREFIX}_{digest}"
        known = generated_ids.setdefault(component_type, {})
        if name in known:
            return known[name]
        known[name] = row["id"] = str(uuid.uuid4())
    else:
        row["id"] = str(uuid.uuid4())
    rows.append((component_type, {**row, "Name": name}))
    return row["id"]


#: Delete order for generated rows (parents first), the reverse of how they are written.
_GENERATED_TABLES = ("Envelope", "HVAC", "SpaceUse", "DHW", "EnvelopeAssembly", "ConditioningSystems")


def write_rows(db, rows: list[tuple[str, dict[str, Any]]]) -> None:
    """Replace every generated record with `rows` (variants first), in one batch."""
    generated = {"Name": {"startswith": f"{PREFIX}_"}}
    with db.batch_() as batch:
        for component_type in _GENERATED_TABLES:
            lib._client_accessor(batch, component_type).delete_many(where=generated)
        # then the variants the group records pointed at
        batch.constructionassemblylayer.delete_many(where={"ConstructionAssembly": {"is": generated}})
        for component_type in sorted({_type(p) for p in parts()} - set(_GENERATED_TABLES)):
            lib._client_accessor(batch, component_type).delete_many(where=generated)
        for component_type, row in rows:
            lib._client_accessor(batch, component_type).create(data=row)


# -- the project ------------------------------------------------------------------------


def read_rules(workspace) -> dict[str, Any] | None:
    path = workspace.path("part_rules")
    return (yaml.safe_load(path.read_text()) or {}) if path.exists() else None


def _read_yaml(path) -> dict[str, Any]:
    return (yaml.safe_load(path.read_text()) or {}) if path.exists() else {}


def compile_project(workspace) -> dict[str, Any]:
    """Compile the saved rules into component-map.yaml, the generated records and the Scenario
    characteristic. A project without part-rules.yaml is left alone. -> {ok, errors, groups}"""
    rules = read_rules(workspace)
    if rules is None:
        return {"ok": True, "skipped": True, "errors": []}
    semantic = workspace.read_semantic_fields()
    retrofits = _read_yaml(workspace.path("retrofits"))
    priors = _read_yaml(workspace.path("component_priors"))
    db = workspace.prisma_client()
    db.connect()
    try:
        found = functools.cache(lambda: building_contexts(workspace, semantic))
        result = compile_rules(rules, semantic, retrofits, db, found, priors)
        write_rows(db, result["rows"])
    except PartRulesError as exc:
        return {"ok": False, "errors": [str(exc)]}
    finally:
        db.disconnect()
    workspace.write_component_map_selectors(result["component_map"])
    workspace.write_generated_component_map(to_globi(result["component_map"]))
    _write_generated_fields(workspace, semantic, result["scenario"], result["variants"])
    return {"ok": True, "errors": [], "groups": result["groups"], "records": len(result["rows"]), "variants": result["variants"]}


def variant_fields(semantic: dict[str, Any]) -> dict[str, int]:
    """The generated variant-index fields and their levels, for Sampling to draw."""
    return {f["Name"]: len(f.get("Options") or []) for f in semantic.get("Fields") or [] if f.get("Description") == VARIANT_NOTE}


def _write_generated_fields(workspace, semantic: dict[str, Any], scenarios: list[str] | None, variants: dict[str, int]) -> None:
    fields = [f for f in semantic.get("Fields") or [] if f.get("Description") not in GENERATED_NOTES]
    if scenarios:
        fields.append({"Name": SCENARIO, "Options": scenarios, "Description": GENERATED_NOTE})
    for name, levels in variants.items():
        fields.append({"Name": name, "Options": [str(k) for k in range(1, levels + 1)], "Description": VARIANT_NOTE})
    if fields != (semantic.get("Fields") or []):
        workspace.write_semantic_fields({**semantic, "Fields": fields})


def write_baseline(workspace) -> dict[str, Any]:
    """Give a new project rules from its library's first archetype, and compile them."""
    db = workspace.prisma_client()
    db.connect()
    try:
        rules = baseline(db)
    finally:
        db.disconnect()
    workspace.path("part_rules").write_text(yaml.safe_dump(rules, sort_keys=False))
    return compile_project(workspace)
