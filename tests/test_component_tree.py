from services.component_tree import get_component_tree


def test_roots_are_envelope_and_operations():
    tree = get_component_tree()
    assert tree["roots"] == ["Envelope", "Operations"]


def test_known_real_world_paths_are_present():
    """Regression guard: these are real selector paths used by globi-partners-data
    component maps (e.g. Korea, MA). If epinterface's ZoneComponent shape drifts,
    this test should be the first thing to fail, not a silent frontend mismatch."""
    tree = get_component_tree()
    paths = {node["path"] for node in tree["nodes"]}

    for expected_path in [
        "Envelope.Assemblies.FacadeAssembly",
        "Envelope.Infiltration",
        "Envelope.Window",
        "Operations.SpaceUse.Lighting",
        "Operations.SpaceUse.Occupancy",
        "Operations.HVAC.ConditioningSystems.Heating",
        "Operations.HVAC.ConditioningSystems.Cooling",
        "Operations.HVAC.Ventilation",
        "Operations.DHW",
    ]:
        assert expected_path in paths, f"expected path {expected_path!r} missing from component tree"


def test_shared_field_names_are_distinct_positions_not_merged():
    """epinterface's raw graph merges same-named fields (e.g. "Schedule") from
    different parents into one DAG node; the selector tree must keep them as
    separate, independently-addressable paths."""
    tree = get_component_tree()
    paths = {node["path"] for node in tree["nodes"]}

    assert "Operations.SpaceUse.Lighting.Schedule" in paths
    assert "Operations.SpaceUse.Equipment.Schedule" in paths


def test_leaf_nodes_have_no_children():
    tree = get_component_tree()
    for node in tree["nodes"]:
        if node["isLeaf"]:
            assert node["children"] == []
        else:
            assert node["children"]


def test_node_paths_are_unique():
    tree = get_component_tree()
    paths = [node["path"] for node in tree["nodes"]]
    assert len(paths) == len(set(paths))


def test_schedule_nodes_are_pruned_leaves():
    """Year/Week/Day are authored as their own component-library records (via a
    relation picker, e.g. Lighting.Schedule -> pick an existing Year), never as
    further selector branches -- no real component-map.yaml ever sets a
    selector on Year.January or Week.Monday. Without pruning, this expands to
    710 nodes; with it, the tree stays close to epinterface's ~54 raw nodes."""
    tree = get_component_tree()
    by_path = {node["path"]: node for node in tree["nodes"]}

    schedule_node = by_path["Operations.SpaceUse.Lighting.Schedule"]
    assert schedule_node["componentType"] == "Year"
    assert schedule_node["isLeaf"] is True
    assert schedule_node["children"] == []
    assert "Operations.SpaceUse.Lighting.Schedule.January" not in by_path

    assert len(tree["nodes"]) < 100


def test_component_type_reports_library_key_name_not_raw_class_name():
    tree = get_component_tree()
    by_path = {node["path"]: node for node in tree["nodes"]}

    assert by_path["Operations.SpaceUse.Lighting"]["componentType"] == "Lighting"
    assert by_path["Envelope.Assemblies.FacadeAssembly"]["componentType"] == "ConstructionAssembly"
    # A "grouping" node (SpaceUse bundles Occupancy/Lighting/Equipment/...) is
    # ALSO independently library-backed -- real component maps sometimes select
    # a whole SpaceUse record at once rather than each child separately.
    assert by_path["Operations.SpaceUse"]["componentType"] == "SpaceUse"
