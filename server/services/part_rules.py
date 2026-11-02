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
"""

from __future__ import annotations

import functools
import hashlib
import itertools
import json
import uuid
from collections import Counter
from typing import Any, Callable

import yaml

from services import component_library as lib
from services.globi_component_map import SCENARIO, _selectors, building_contexts, to_globi

GROUPS = ("Envelope", "Operations.SpaceUse", "Operations.HVAC", "Operations.DHW")
#: Generated record names start with this; compiles delete and rewrite exactly these.
PREFIX = "auto"
#: Comes from `assembly_base` rather than a rule: it needs an area that lives on the assembly.
INTERNAL_MASS = "Envelope.Assemblies.InternalMassAssembly"
#: Above this many combinations a group uses the ones the buildings have, not every one.
MAX_PRODUCT = 5_000
BASELINE = "Baseline"
GENERATED_NOTE = "Generated from retrofits.yaml: Baseline plus one value per retrofit package."


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


def apply_package(values: dict[str, str], package: dict[str, Any], upgrade_order: dict[str, list[str]]) -> dict[str, str]:
    """A combination's values after a retrofit package's measures, in order; never a downgrade."""
    out = dict(values)
    for measure in package.get("measures") or []:
        field = measure["field"]
        if field not in out:
            continue
        holds = all(
            out.get(c["field"]) in c["in"] if "in" in c else out.get(c["field"]) not in c.get("not_in", [])
            for c in _conditions(measure)
        )
        new = measure.get("to") or (measure.get("map") or {}).get(out[field])
        order = upgrade_order.get(field) or []
        if not holds or new is None or (new in order and out[field] in order and order.index(new) < order.index(out[field])):
            continue
        out[field] = new
    return out


# -- reading the library ------------------------------------------------------------


class _Library:
    """Cached lookups on one connected Prisma client."""

    def __init__(self, db):
        self.db = db
        self._flat: dict[tuple[str, str], dict[str, Any] | None] = {}
        self._ids: dict[str, dict[str, str]] = {}

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
) -> dict[str, Any]:
    """-> {component_map, rows: [(type, row)] in write order, scenario: values | None, groups}

    `found` returns the buildings' combinations (`building_contexts`); it is only called for a
    group whose full product is too large."""
    library = _Library(db)
    rule_for = rules.get("parts") or {}
    user_fields = [f for f in semantic_fields.get("Fields") or [] if f.get("Description") != GENERATED_NOTE]
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
    if problems:
        raise PartRulesError(" ".join(problems))

    tree_map: dict[str, Any] = {}
    rows: list[tuple[str, dict[str, Any]]] = []
    generated_ids: dict[str, dict[str, str]] = {}
    base = rules.get("assembly_base")
    base_assembly = library.record("EnvelopeAssembly", base) if base else None
    summary = {}
    for group in GROUPS:
        group_parts = [p for p in parts() if _group_of(p) == group]
        deps = set().union(*(rule_for[p].get("depends_on") or [] for p in group_parts))
        measured = {m["field"] for p in packages for m in p.get("measures") or [] if m["field"] in deps}
        if measured:
            deps |= {c["field"] for p in packages for m in p.get("measures") or [] if m["field"] in measured
                     for c in _conditions(m) if c["field"] in options}
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
            if measured and combo[-1] != BASELINE:
                values = apply_package(values, next(p for p in packages if p["name"] == combo[-1]), upgrade_order)
            name = "_".join([PREFIX, "_".join(combo)])
            if names_seen.setdefault(name, combo) != combo:
                raise PartRulesError(
                    f"{' / '.join(combo)} and {' / '.join(names_seen[name])} give the same record name; "
                    "rename a value so they differ."
                )
            choice = {p: option_for(rule_for[p], values) for p in group_parts}
            _build(group, name, choice, library, base_assembly, generated_ids, rows)
        summary[group] = {"fields": selector_fields, "combinations": len(combos)}
    return {"component_map": tree_map, "rows": rows, "scenario": scenarios, "groups": summary}


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
    return sorted({tuple(c[f] for f in fields) for c in found["contexts"]})


def _build(path, name, choice, library, base_assembly, generated_ids, rows) -> str:
    """Queue the record for `path` (named `name` at a group root) and return its id."""
    component_type = _type(path)
    if path in choice:  # a leaf
        option = choice[path]
        if path not in GROUPS:
            return library.ids(component_type)[option]
        # DHW: globi looks the leaf itself up by the generated name
        source = lib._client_accessor(library.db, component_type).find_unique(where={"Name": option})
        data = {k: v for k, v in source.model_dump().items() if k not in ("id", "Name") and v is not None and not isinstance(v, (dict, list))}
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
    """Replace every generated record with `rows`, in one batch."""
    with db.batch_() as batch:
        for component_type in _GENERATED_TABLES:
            lib._client_accessor(batch, component_type).delete_many(where={"Name": {"startswith": f"{PREFIX}_"}})
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
    db = workspace.prisma_client()
    db.connect()
    try:
        found = functools.cache(lambda: building_contexts(workspace, semantic))
        result = compile_rules(rules, semantic, retrofits, db, found)
        write_rows(db, result["rows"])
    except PartRulesError as exc:
        return {"ok": False, "errors": [str(exc)]}
    finally:
        db.disconnect()
    workspace.write_component_map_selectors(result["component_map"])
    workspace.write_generated_component_map(to_globi(result["component_map"]))
    _write_scenario_field(workspace, semantic, result["scenario"])
    return {"ok": True, "errors": [], "groups": result["groups"], "records": len(result["rows"])}


def _write_scenario_field(workspace, semantic: dict[str, Any], scenarios: list[str] | None) -> None:
    fields = [f for f in semantic.get("Fields") or [] if f.get("Description") != GENERATED_NOTE]
    if scenarios:
        fields.append({"Name": SCENARIO, "Options": scenarios, "Description": GENERATED_NOTE})
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
