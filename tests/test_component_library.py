import tempfile
from pathlib import Path

import pytest

from services import component_library as lib
from services.workspace import ProjectWorkspace


@pytest.fixture
def client():
    root = Path(tempfile.mkdtemp()) / "workspace"
    workspace = ProjectWorkspace.create(root, "Test Project", init_db=True)
    db_client = workspace.prisma_client()
    db_client.connect()
    yield db_client
    db_client.disconnect()


INFILTRATION_PAYLOAD = {
    "Name": "MA_SFH_LeakyEnvelope_Main",
    "IsOn": True,
    "ConstantCoefficient": 1.0,
    "TemperatureCoefficient": 0.0,
    "WindVelocityCoefficient": 0.0,
    "WindVelocitySquaredCoefficient": 0.0,
    "AFNAirMassFlowCoefficientCrack": 0.001,
    "AirChangesPerHour": 0.5,
    "FlowPerExteriorSurfaceArea": 0.0002,
    "CalculationMethod": "AirChanges/Hour",
}


def test_list_component_types_includes_known_real_types():
    types = lib.list_component_types()
    for expected in ["Lighting", "Infiltration", "Envelope", "Year", "Week", "Day", "DHW"]:
        assert expected in types


def test_schema_for_relation_free_type_has_expected_fields_and_constraints():
    schema = lib.get_component_type_schema("Infiltration")
    fields_by_name = {f["name"]: f for f in schema["fields"]}
    assert fields_by_name["AirChangesPerHour"]["kind"] == "number"
    assert fields_by_name["AirChangesPerHour"]["ge"] == 0
    assert fields_by_name["CalculationMethod"]["kind"] == "enum"
    assert "AirChanges/Hour" in fields_by_name["CalculationMethod"]["options"]


def test_schema_for_type_with_relation_marks_it_as_relation():
    schema = lib.get_component_type_schema("Lighting")
    fields_by_name = {f["name"]: f for f in schema["fields"]}
    assert fields_by_name["Schedule"]["kind"] == "relation"
    assert fields_by_name["Schedule"]["relationType"] == "Year"


def test_pep604_optional_string_fields_classify_as_string_not_raw():
    """Regression guard: epinterface's shared metadata fields (Category, Comment,
    DataSource, Version) are typed `Annotated[str | None, ...] | None` -- the
    PEP 604 `X | None` form produces a different get_origin() than
    `Optional[X]`/`Union[X, None]` (types.UnionType vs typing.Union), and an
    earlier version of _strip_optional only handled the latter, silently
    misclassifying these as the 'raw' fallback kind instead of 'string'."""
    schema = lib.get_component_type_schema("Lighting")
    fields_by_name = {f["name"]: f for f in schema["fields"]}
    for name in ["Category", "Comment", "DataSource", "Version"]:
        assert fields_by_name[name]["kind"] == "string", f"{name} misclassified as {fields_by_name[name]['kind']!r}"


def test_unknown_component_type_raises():
    with pytest.raises(ValueError):
        lib.get_component_type_schema("NotAReakType")


def test_create_and_list_relation_free_record(client):
    created = lib.create_record(client, "Infiltration", INFILTRATION_PAYLOAD)
    assert created["Name"] == "MA_SFH_LeakyEnvelope_Main"
    assert created["AirChangesPerHour"] == 0.5
    # Prisma reverse-relation noise (Metadata, MainInfiltrations, ...) must not leak through.
    assert "Metadata" not in created
    assert "MainInfiltrations" not in created

    records = lib.list_records(client, "Infiltration")
    assert [r["Name"] for r in records] == ["MA_SFH_LeakyEnvelope_Main"]


def test_create_rejects_payload_missing_required_field(client):
    bad_payload = {k: v for k, v in INFILTRATION_PAYLOAD.items() if k != "AirChangesPerHour"}
    with pytest.raises(ValueError):
        lib.create_record(client, "Infiltration", bad_payload)


def test_update_and_delete_record(client):
    lib.create_record(client, "Infiltration", INFILTRATION_PAYLOAD)

    updated = lib.update_record(
        client, "Infiltration", "MA_SFH_LeakyEnvelope_Main", {**INFILTRATION_PAYLOAD, "AirChangesPerHour": 0.8}
    )
    assert updated["AirChangesPerHour"] == 0.8

    lib.delete_record(client, "Infiltration", "MA_SFH_LeakyEnvelope_Main")
    assert lib.list_records(client, "Infiltration") == []


def test_check_existence(client):
    lib.create_record(client, "Infiltration", INFILTRATION_PAYLOAD)
    result = lib.check_existence(client, "Infiltration", ["MA_SFH_LeakyEnvelope_Main", "DoesNotExist"])
    assert result == {"MA_SFH_LeakyEnvelope_Main": True, "DoesNotExist": False}


def _day_payload(name: str) -> dict:
    return {"Name": name, "Type": "Fraction", **{f"Hour_{h:02d}": 0.1 for h in range(24)}}


def _week_payload(name: str, day_name: str) -> dict:
    return {"Name": name, **{d: day_name for d in
        ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]}}


def _year_payload(name: str, week_name: str) -> dict:
    months = ["January", "February", "March", "April", "May", "June", "July",
              "August", "September", "October", "November", "December"]
    return {"Name": name, "Type": "Lighting", **{m: week_name for m in months}}


def test_relation_chain_day_week_year_lighting_round_trips(client):
    lib.create_record(client, "Day", _day_payload("AlwaysOnDay"))
    lib.create_record(client, "Week", _week_payload("AlwaysOnWeek", "AlwaysOnDay"))
    lib.create_record(client, "Year", _year_payload("AlwaysOnLightingSchedule", "AlwaysOnWeek"))

    lighting = lib.create_record(
        client,
        "Lighting",
        {
            "Name": "MA_SFH_LED",
            "PowerDensity": 2.2,
            "DimmingType": "Off",
            "IsOn": True,
            "Schedule": "AlwaysOnLightingSchedule",
        },
    )

    # Shallow view: the relation collapses to just the related record's Name.
    assert lighting["Schedule"] == "AlwaysOnLightingSchedule"

    # Deep view: fully hydrated nested tree, matching what epinterface's own
    # pydantic model (and downstream simulation code) expects.
    deep = lib.get_record(client, "Lighting", "MA_SFH_LED", deep=True)
    assert deep["Schedule"]["January"]["Monday"]["Hour_00"] == 0.1


def test_relation_field_referencing_missing_record_raises(client):
    with pytest.raises(LookupError):
        lib.create_record(
            client,
            "Lighting",
            {
                "Name": "MA_SFH_LED",
                "PowerDensity": 2.2,
                "DimmingType": "Off",
                "IsOn": True,
                "Schedule": "DoesNotExist",
            },
        )
