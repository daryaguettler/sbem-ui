"""Single building as a flat model: every parameter typed into one form, run through globi.

The form's fields, groups, defaults and units come from globi's own example
(`examples/tutorial/flat-building.yml`), its types, choices and limits from epinterface's
`FlatModel`. A run calls `make cli simulate-flat` in the globi repo (EnergyPlus in Docker),
so the project must live inside that repo, e.g. `globi/inputs/my-model`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal, get_args, get_origin

import yaml
from pydantic import ValidationError

from services.norway_runner import Job, start_command

FLAT_MODEL_FILE = "flat-building.yml"
EXAMPLE = Path("examples/tutorial/flat-building.yml")
#: globi's Docker containers only see these folders of the repo.
DOCKER_DIRS = ("inputs", "examples", "outputs")
#: The first run builds globi's Docker image, which takes several minutes.
RUN_TIMEOUT = 1800

_FIELD_LINE = re.compile(r"^(\w+):[^#]*(?:#\s*(.*))?$")


class FlatModelError(Exception):
    """The form can't be shown, saved or run; `fields` maps field names to messages."""

    def __init__(self, message: str, fields: dict[str, str] | None = None):
        super().__init__(message)
        self.fields = fields or {}


def find_globi_root(project_root: Path) -> Path | None:
    """The globi repo that contains the project, if any."""
    for parent in [project_root, *project_root.parents]:
        if (parent / "src" / "globi").is_dir() and (parent / "Makefile").exists():
            return parent
    return None


def parse_example(text: str) -> list[dict[str, str]]:
    """Fields of the example in file order, each with its group and hint.

    A group is the comment line that follows a blank line ("# Geometry", text before any
    ":" or "("); a hint is a field line's trailing comment ("footprint length [m]").
    """
    fields: list[dict[str, str]] = []
    group, after_blank = "Other", True
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            after_blank = True
            continue
        if stripped.startswith("#"):
            if after_blank:
                group = re.split(r"[:(]", stripped.lstrip("# "))[0].strip()
        elif match := _FIELD_LINE.match(stripped):
            fields.append({"name": match[1], "group": group, "hint": match[2] or ""})
        after_blank = False
    return fields


def _describe(info: Any) -> dict[str, Any]:
    """Input type, choices and limits of one FlatModel field."""
    annotation = info.annotation
    if get_origin(annotation) is Literal:
        return {"type": "choice", "options": list(get_args(annotation))}
    if annotation not in (int, float):
        return {"type": "text"}
    limits: dict[str, Any] = {"type": "integer" if annotation is int else "number"}
    for constraint in info.metadata:
        if (ge := getattr(constraint, "ge", None)) is not None:
            limits["min"] = ge
        if (le := getattr(constraint, "le", None)) is not None:
            limits["max"] = le
    return limits


def _globi_root(project_root: Path) -> Path:
    globi = find_globi_root(project_root)
    if globi is None:
        raise FlatModelError(
            "Open a project inside the globi repo (e.g. globi/inputs/my-model) to run a single building."
        )
    return globi


def read_form(project_root: Path) -> dict[str, Any]:
    """The form: one entry per field, with the saved value or the example's default."""
    from epinterface.sbem.flat_model import FlatModel

    globi = _globi_root(project_root)
    example = (globi / EXAMPLE).read_text()
    values = yaml.safe_load(example)
    saved = project_root / FLAT_MODEL_FILE
    if saved.exists():
        values |= yaml.safe_load(saved.read_text()) or {}
    model_fields = FlatModel.model_fields
    listed = [f for f in parse_example(example) if f["name"] in model_fields]
    names = {f["name"] for f in listed}
    listed += [{"name": n, "group": "Other", "hint": ""} for n in model_fields if n not in names]
    return {
        "file": FLAT_MODEL_FILE,
        "fields": [
            {**f, **_describe(model_fields[f["name"]]), "value": values.get(f["name"])}
            for f in listed
        ],
    }


def save_form(project_root: Path, values: dict[str, Any]) -> None:
    """Validate the values with epinterface and write them to the project's flat model file."""
    from epinterface.sbem.flat_model import FlatModel

    try:
        FlatModel.model_validate(values)
    except ValidationError as exc:
        fields = {str(e["loc"][0]): e["msg"] for e in exc.errors() if e["loc"]}
        raise FlatModelError("Some values are not valid.", fields) from exc
    ordered = {name: values[name] for name in FlatModel.model_fields if name in values}
    (project_root / FLAT_MODEL_FILE).write_text(yaml.safe_dump(ordered, sort_keys=False))


def run_command(project_root: Path) -> tuple[list[str], Path]:
    """The `make cli simulate-flat` call for the project's saved flat model, and its cwd."""
    globi = _globi_root(project_root)
    config = (project_root / FLAT_MODEL_FILE).relative_to(globi)
    if config.parts[0] not in DOCKER_DIRS:
        raise FlatModelError(f"Move the project under globi/inputs/: Docker can't see {config.parts[0]}/.")
    output_dir = f"outputs/{project_root.name}-flat"
    cmd = ["make", "-C", str(globi), "cli", "simulate-flat", "--"]
    cmd += ["--config", config.as_posix(), "--output-dir", output_dir, "--json"]
    return cmd, globi


def start_run(project_root: Path) -> Job:
    """Simulate the saved flat model in the background (poll it like any runner job)."""
    if not (project_root / FLAT_MODEL_FILE).exists():
        raise FlatModelError("Save the building first.")
    cmd, cwd = run_command(project_root)
    return start_command("flat-model", cmd, cwd, RUN_TIMEOUT)
