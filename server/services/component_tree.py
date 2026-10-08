"""Introspects the real epinterface component graph, replacing the frontend's
hardcoded prismaComponents.ts mirror with a live, always-correct source of truth.

This is the *selector* tree (what the Component Map authoring UI walks) -- not
the full pydantic field graph. Two adjustments on top of epinterface's raw
construct_graph() output:

1. Path-qualification: construct_graph() is keyed by *field name*, so a node
   named "Schedule" merges five different parents (Occupancy, Lighting,
   Equipment, WaterUse, Ventilation all have a field called "Schedule" pointing
   at YearComponent) into one graph node. The selector tree needs each of those
   as a distinct, independently-selectable position, so this expands the DAG
   into a tree of dotted paths (see get_component_tree docstring below).

2. Schedule pruning: a node whose type is Year/Week/Day is a component-library
   record in its own right (authored via its own form + relation picker, e.g.
   "Lighting -> Schedule -> pick an existing Year record"), not a further
   selector branch point -- no real-world component-map.yaml ever sets a
   selector on Year.January or Week.Monday. Without this, the walk would
   recurse Year -> 12 months -> Week -> 7 days -> Day, ballooning ~54 raw graph
   nodes into 710 path-qualified ones for no purpose the selector UI needs.
"""

from typing import Any

_SCHEDULE_TYPES = {"YearComponent", "WeekComponent", "DayComponent"}


def _component_library_type_map() -> dict[type, str]:
    """{LightingComponent: "Lighting", YearComponent: "Year", ...} -- reverse of
    component_library._component_type_map(), used to tag each selector-tree
    node with the ComponentLibrary key it's authored under (or None for the
    Zone/Operations/SpaceUse/etc. "grouping" types that aren't themselves a
    library record type)."""
    from epinterface.sbem.interface import ComponentLibrary
    from typing import get_args

    mapping: dict[type, str] = {}
    for name, info in ComponentLibrary.model_fields.items():
        args = get_args(info.annotation)
        if len(args) == 2 and args[0] is str and isinstance(args[1], type):
            mapping[args[1]] = name
    return mapping


def get_component_tree() -> dict[str, Any]:
    """Serialize epinterface's ZoneComponent graph as a path-qualified node list.

    Returns {nodes: [{path, displayName, componentType, children, isLeaf}], roots}.
    `path` is a dot-joined path from the top-level roots (e.g. "Envelope",
    "Operations.SpaceUse.Lighting") -- the same addressing scheme already used by
    server/services/component_map.py's selector path helpers. `componentType` is
    the ComponentLibrary key this node is authored under (e.g. "Lighting"), or
    null for structural grouping nodes that aren't independently library-backed
    (Operations, SpaceUse, HVAC, ConditioningSystems).
    """
    from epinterface.sbem.components.composer import construct_graph
    from epinterface.sbem.components.zones import ZoneComponent

    g = construct_graph(ZoneComponent)
    library_types = _component_library_type_map()

    def target_type(field_name: str) -> type | None:
        in_edges = list(g.in_edges(field_name, data=True))
        if not in_edges:
            return None
        return in_edges[0][2].get("data", {}).get("type")

    nodes: dict[str, dict[str, Any]] = {}

    def visit(field_name: str, path: str) -> None:
        node_type = target_type(field_name)
        component_type = library_types.get(node_type) if node_type is not None else None
        is_schedule = node_type is not None and node_type.__name__ in _SCHEDULE_TYPES

        children = [] if is_schedule else sorted(g.successors(field_name))
        child_paths = [f"{path}.{child}" for child in children]

        nodes[path] = {
            "path": path,
            "displayName": field_name,
            "componentType": component_type,
            "children": child_paths,
            "isLeaf": len(child_paths) == 0,
        }
        for child, child_path in zip(children, child_paths):
            visit(child, child_path)

    roots = sorted(g.successors("root"))
    for root_name in roots:
        visit(root_name, root_name)

    return {
        "nodes": sorted(nodes.values(), key=lambda n: n["path"]),
        "roots": roots,
    }
