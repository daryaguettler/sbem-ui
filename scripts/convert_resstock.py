"""Pre-convert ResStock's options lookup into the `resstock` project template.

    uv run python scripts/convert_resstock.py <resstock checkout at TAG>

Each option of the characteristics in SPECS becomes one library record, named
`resstock_<Characteristic>_<Option>`: a copy of the starter archetype's record for that part
with the values ResStock sets replaced, using the simple factors in ASSUMPTIONS. Writes
templates/projects/resstock/{components-lib.db, resstock-preset.yml, NOTICE}, which the app offers as
ready-made characteristics (semantic field + part rule) in a project made from that template.
"""

from __future__ import annotations

import csv
import re
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from epinterface.sbem.prisma.client import PrismaSettings

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from services import component_library as lib
from services import part_rules

TAG = "v3.4.0"
STARTER = ROOT / "templates" / "projects" / "globi-starter"
OUT = ROOT / "templates" / "projects" / "resstock"
PRESET_FILE = "resstock-preset.yml"

R_IP_TO_SI = 0.1761  # ft²·°F·h/Btu -> m²K/W
U_IP_TO_SI = 5.678  # Btu/h·ft²·°F -> W/m²K
BTU_PER_WH_TO_COP = 0.293  # SEER / EER / HSPF -> W/W
ACH50_TO_NATURAL = 1 / 20
ASSUMPTIONS = [
    f"R-values: ResStock's assembly R (IP, incl. air films) x {R_IP_TO_SI} -> SI; an insulation layer is sized to reach 1/R (construction-for-U stacks).",
    f"Window U-factor (IP) x {U_IP_TO_SI} -> W/m2K; SHGC as is; visible transmittance set equal to SHGC (ResStock doesn't give it).",
    f"Infiltration: ACH50 x {ACH50_TO_NATURAL:g} -> air changes per hour.",
    f"Heat pumps: HSPF x {BTU_PER_WH_TO_COP} -> heating COP (dual-fuel treated as all-electric); GSHP COP as is.",
    "Furnaces, boilers, baseboards: AFUE / efficiency -> COP; 'Fuel' systems are NaturalGas (ResStock sets the fuel in Heating Fuel).",
    f"Cooling: SEER or EER x {BTU_PER_WH_TO_COP} -> COP; heat-pump cooling is set by HVAC Heating Efficiency, so those options are skipped.",
    "Water heaters: EF / UEF -> COP; fuel from ResStock's water_heater_fuel_type.",
    "Heating setpoint: constant all year, F -> C; the cooling setpoint stays the starter's.",
    "Every value ResStock doesn't set (distribution COP, schedules, layer materials, ...) keeps the starter archetype's.",
]
FUELS = {"electricity": "Electricity", "natural gas": "NaturalGas", "propane": "Propane", "fuel oil": "FuelOil"}

Converter = Callable[[dict[str, str], str], dict[str, Any] | str]


def _f(args: dict[str, str], key: str) -> float:
    return float(args[key])


def _construction(key: str, construction_type: str) -> Converter:
    def convert(args, option):
        r = _f(args, key)
        return {"u_value": 1 / (r * R_IP_TO_SI), "type": construction_type} if r > 0 else "no assembly R-value"
    return convert


def _window(args, option):
    if option == "No Windows":
        return "no windows"
    shgc = _f(args, "window_shgc")
    return {"UValue": round(_f(args, "window_ufactor") * U_IP_TO_SI, 3), "SHGF": shgc, "TVis": shgc, "Type": option.split(",")[0]}


def _infiltration(args, option):
    return {"AirChangesPerHour": round(_f(args, "air_leakage_value") * ACH50_TO_NATURAL, 4)}


def _heating(args, option):
    if args.get("heat_pump_type", "none") != "none":
        efficiency = _f(args, "heat_pump_heating_efficiency")
        cop = efficiency if args["heat_pump_heating_efficiency_type"] == "COP" else efficiency * BTU_PER_WH_TO_COP
        return {"ConditioningType": "Heating", "Fuel": "Electricity", "SystemCOP": round(cop, 3)}
    if args.get("heating_system_type", "none") == "none":
        return "no heating system"
    fuel = "Electricity" if option.startswith("Electric") else "NaturalGas"
    return {"ConditioningType": "Heating", "Fuel": fuel, "SystemCOP": _f(args, "heating_system_heating_efficiency")}


def _cooling(args, option):
    if args.get("cooling_system_type", "none") == "none":
        return "no cooling system of its own"
    return {"ConditioningType": "Cooling", "Fuel": "Electricity", "SystemCOP": round(_f(args, "cooling_system_cooling_efficiency") * BTU_PER_WH_TO_COP, 3)}


def _heating_setpoint(args, option):
    return {"HeatingSetpoint": round((_f(args, "hvac_control_heating_weekday_setpoint_temp") - 32) * 5 / 9, 2)}


def _water_heater(args, option):
    fuel = FUELS.get(args.get("water_heater_fuel_type", ""))
    if fuel is None:
        return f"fuel {args.get('water_heater_fuel_type')!r} has no DHW fuel type"
    return {"SystemCOP": _f(args, "water_heater_efficiency"), "FuelType": fuel}


#: ResStock characteristic -> the parts its options decide, and how its arguments become the record.
SPECS: dict[str, tuple[list[str], Converter]] = {
    "Insulation Wall": (["Envelope.Assemblies.FacadeAssembly"], _construction("wall_assembly_r", "Facade")),
    "Insulation Ceiling": (["Envelope.Assemblies.AtticFloorAssembly"], _construction("ceiling_assembly_r", "AtticFloor")),
    "Insulation Roof": (["Envelope.Assemblies.AtticRoofAssembly", "Envelope.Assemblies.FlatRoofAssembly"], _construction("roof_assembly_r", "AtticRoof")),
    "Windows": (["Envelope.Window"], _window),
    "Infiltration": (["Envelope.Infiltration"], _infiltration),
    "HVAC Heating Efficiency": (["Operations.HVAC.ConditioningSystems.Heating"], _heating),
    "HVAC Cooling Efficiency": (["Operations.HVAC.ConditioningSystems.Cooling"], _cooling),
    "Heating Setpoint": (["Operations.SpaceUse.Thermostat"], _heating_setpoint),
    "Water Heater Efficiency": (["Operations.DHW"], _water_heater),
}


def read_lookup(path: Path) -> dict[str, dict[str, dict[str, str]]]:
    """options_lookup.tsv -> {characteristic: {option: {argument: value}}} for SPECS."""
    out: dict[str, dict[str, dict[str, str]]] = {}
    with path.open(newline="") as f:
        for row in csv.reader(f, delimiter="\t"):
            if row and row[0] in SPECS:
                out.setdefault(row[0], {})[row[1]] = dict(arg.split("=", 1) for arg in row[3:] if "=" in arg)
    return out


def record_name(characteristic: str, option: str) -> str:
    return "resstock_" + re.sub(r"[^A-Za-z0-9.-]+", "_", f"{characteristic} {option}").strip("_")


def _constant_setpoint(db, name: str, celsius: float) -> str:
    """A Day/Week/Year chain holding `celsius` all year (the thermostat follows its schedule)."""
    lib.create_record(db, "Day", {"Name": name, "Type": "Temperature", **{f"Hour_{h:02d}": celsius for h in range(24)}})
    days = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
    lib.create_record(db, "Week", {"Name": name, **dict.fromkeys(days, name)})
    months = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
    lib.create_record(db, "Year", {"Name": name, "Type": "Setpoint", **dict.fromkeys(months, name)})
    return name


def write_records(db, lookup: dict[str, dict[str, dict[str, str]]]) -> list[dict[str, Any]]:
    """Create one record per convertible option -> the preset's characteristics."""
    starter = part_rules.baseline(db)["parts"]
    characteristics = []
    for characteristic, (parts, convert) in SPECS.items():
        part_type = part_rules._type(parts[0])
        template = lib.get_record(db, part_type, starter[parts[0]]["default"])
        options, skipped = {}, {}
        for option, args in lookup.get(characteristic, {}).items():
            if option == "Void" or option.startswith("Shared"):
                skipped[option] = "not a modelled option"
                continue
            values = convert(args, option)
            if isinstance(values, str):
                skipped[option] = values
                continue
            name = record_name(characteristic, option)
            if "u_value" in values:
                lib.construction_for_u(db, name, values["type"], values["u_value"])
            else:
                if "HeatingSetpoint" in values:
                    values["HeatingSchedule"] = _constant_setpoint(db, name, values["HeatingSetpoint"])
                lib.create_record(db, part_type, {**template, **values, "Name": name})
            options[option] = name
        characteristics.append({"name": characteristic, "parts": parts, "options": options, "skipped": skipped})
    return characteristics


def main(resstock: Path) -> None:
    lookup = read_lookup(resstock / "resources" / "options_lookup.tsv")
    missing = set(SPECS) - set(lookup)
    if missing:
        sys.exit(f"Not in this options_lookup.tsv: {', '.join(sorted(missing))}")
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(STARTER, OUT)
    license_text = (resstock / "LICENSE.md").read_text()
    (OUT / "NOTICE").write_text(
        f"components-lib.db and {PRESET_FILE} contain values derived (unit-converted, not ResStock itself)\n"
        f"from ResStock {TAG} resources/options_lookup.tsv, under its license:\n\n{license_text}"
    )
    db = PrismaSettings.New(database_path=OUT / "components-lib.db", if_exists="ignore", auto_register=False).db
    db.connect()
    try:
        characteristics = write_records(db, lookup)
    finally:
        db.disconnect()
    preset = {
        "source": {"repo": "https://github.com/NREL/resstock", "tag": TAG, "file": "resources/options_lookup.tsv", "license": "ResStock license (BSD-style with extra clauses), see NOTICE"},
        "assumptions": ASSUMPTIONS,
        "characteristics": characteristics,
    }
    (OUT / PRESET_FILE).write_text(
        "# Generated by scripts/convert_resstock.py; edit the script and rerun rather than this file.\n"
        + yaml.safe_dump(preset, sort_keys=False, allow_unicode=True, width=120)
    )
    print(f"{sum(len(c['options']) for c in characteristics)} records in {OUT}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))
