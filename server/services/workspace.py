"""Project workspace: a directory on disk holding all artifacts for one modeling project.

Replaces the in-memory-only state (GIS session dict, browser-only Svelte stores) with a
real project directory that survives restarts:

    <project-root>/
      project.json                  # name, created_at, schema_version
      gis/
        raw.<ext>                   # last-uploaded raw GIS file
        enriched.geojson            # GIS + deterministic semantic-field columns
        column_mappings.json        # column -> GloBI role mapping
      semantic-fields.yaml          # SemanticFieldsConfig
      component-map.selectors.yaml  # per-node selector declarations (source of truth)
      component-map.yaml            # generated output
      components-lib.db             # real Prisma SQLite DB (epinterface schema)
      priors/priors.yaml            # semantic-priors RegionConfig shape
      manifest.json                 # readiness/export summary

`project.json` may override any of these locations with a `"files"` map (keys are the
`FILE_KEYS` below, values paths relative to the project root), which lets an existing
repo layout -- e.g. norway-globi's `inputs/` folder -- be opened as a project. An optional
`"runner"` (path relative to the project root) names the repo whose `norway` CLI
validates inputs and runs local test simulations.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from prisma import Prisma

SCHEMA_VERSION = 1

PROJECT_FILE = "project.json"
SEMANTIC_FIELDS_FILE = "semantic-fields.yaml"
COMPONENT_MAP_SELECTORS_FILE = "component-map.selectors.yaml"
COMPONENT_MAP_FILE = "component-map.yaml"
COMPONENTS_DB_FILE = "components-lib.db"
PRIORS_FILE = "priors/priors.yaml"
GIS_DIR = "gis"
GIS_COLUMN_MAPPINGS_FILE = "gis/column_mappings.json"
GIS_DATASET_FILE = "gis/dataset.json"
RETROFITS_FILE = "retrofits.yaml"

#: Default location of every file a project can hold, keyed by the names `project.json`'s
#: optional `"files"` map uses to relocate them.
FILE_KEYS: dict[str, str] = {
    "semantic_fields": SEMANTIC_FIELDS_FILE,
    "component_map_selectors": COMPONENT_MAP_SELECTORS_FILE,
    "component_map": COMPONENT_MAP_FILE,
    "components_db": COMPONENTS_DB_FILE,
    "priors": PRIORS_FILE,
    "retrofits": RETROFITS_FILE,
    "gis_dir": GIS_DIR,
    "training_config": "configs/training.yml",
    "inference_config": "configs/inference.yml",
}


class WorkspaceError(Exception):
    """Raised for workspace creation/open failures."""


class ProjectWorkspace:
    """A single open project directory. One FastAPI process holds at most one of these."""

    def __init__(self, root: Path):
        self.root = root
        project_file = root / PROJECT_FILE
        metadata = json.loads(project_file.read_text()) if project_file.exists() else {}
        self._files: dict[str, str] = {**FILE_KEYS, **(metadata.get("files") or {})}
        runner = metadata.get("runner")
        self.runner: Path | None = (root / runner).resolve() if runner else None

    def path(self, key: str) -> Path:
        """Absolute path of one project file (see `FILE_KEYS`), honoring `project.json`."""
        return self.root / self._files[key]

    def relative(self, key: str) -> str:
        """Project-relative path of one project file."""
        return self._files[key]

    # -- lifecycle -----------------------------------------------------------

    @classmethod
    def create(cls, root: Path, name: str, init_db: bool = True) -> "ProjectWorkspace":
        """Scaffold a brand-new project workspace directory.

        `init_db` runs the (relatively slow, ~seconds: spawns `prisma migrate
        deploy`) components-lib.db schema setup. It's on by default for real
        workspace creation; tests that don't touch the component library can
        pass `init_db=False` and skip straight past it.
        """
        if (root / PROJECT_FILE).exists():
            raise WorkspaceError(f"{root} is already a project; open it instead.")
        adopting = root.exists() and any(root.iterdir())
        root.mkdir(parents=True, exist_ok=True)
        (root / GIS_DIR).mkdir(exist_ok=True)
        (root / "priors").mkdir(exist_ok=True)

        workspace = cls(root)
        workspace._write_project_metadata(name)
        # an existing folder keeps its files; only missing ones are scaffolded
        if not (adopting and workspace.path("semantic_fields").exists()):
            workspace.write_semantic_fields({"Name": name, "Fields": []})
        if not (adopting and workspace.path("component_map_selectors").exists()):
            workspace.write_component_map_selectors({})
        if init_db and not workspace.components_db_path.exists():
            workspace._init_components_db()
        return workspace

    @classmethod
    def open(cls, root: Path) -> "ProjectWorkspace":
        """Open an existing project workspace directory."""
        project_file = root / PROJECT_FILE
        if not project_file.exists():
            raise WorkspaceError(f"{root} is not a project workspace (missing {PROJECT_FILE}).")
        metadata = json.loads(project_file.read_text())
        if metadata.get("schema_version") != SCHEMA_VERSION:
            raise WorkspaceError(
                f"{root} was created with an incompatible schema version "
                f"({metadata.get('schema_version')!r}, expected {SCHEMA_VERSION!r})."
            )
        return cls(root)

    def status(self) -> dict[str, Any]:
        metadata = self._read_project_metadata()
        return {
            "path": str(self.root),
            "name": metadata.get("name"),
            "createdAt": metadata.get("created_at"),
            "lastOpenedWorkflow": metadata.get("last_opened_workflow"),
        }

    def set_last_opened_workflow(self, workflow: str) -> None:
        metadata = self._read_project_metadata()
        metadata["last_opened_workflow"] = workflow
        (self.root / PROJECT_FILE).write_text(json.dumps(metadata, indent=2))

    # -- project metadata ------------------------------------------------------

    def _write_project_metadata(self, name: str) -> None:
        metadata = {
            "name": name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "schema_version": SCHEMA_VERSION,
            "last_opened_workflow": None,
        }
        (self.root / PROJECT_FILE).write_text(json.dumps(metadata, indent=2))

    def _read_project_metadata(self) -> dict[str, Any]:
        return json.loads((self.root / PROJECT_FILE).read_text())

    # -- semantic fields ---------------------------------------------------

    def read_semantic_fields(self) -> dict[str, Any]:
        """The saved config, in the same `Name:`/`Fields:` shape the editor exports."""
        path = self.path("semantic_fields")
        if not path.exists():
            return {"Name": self.status()["name"], "Fields": []}
        return yaml.safe_load(path.read_text()) or {"Name": "", "Fields": []}

    def write_semantic_fields(self, config: dict[str, Any]) -> None:
        path = self.path("semantic_fields")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(config, sort_keys=False))

    # -- component map -------------------------------------------------------

    def read_component_map_selectors(self) -> dict[str, Any]:
        path = self.path("component_map_selectors")
        if not path.exists():
            return {}
        return yaml.safe_load(path.read_text()) or {}

    def write_component_map_selectors(self, selectors: dict[str, Any]) -> None:
        path = self.path("component_map_selectors")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(selectors, sort_keys=False))

    def read_generated_component_map(self) -> dict[str, Any] | None:
        path = self.path("component_map")
        if not path.exists():
            return None
        return yaml.safe_load(path.read_text()) or {}

    def write_generated_component_map(self, component_map: dict[str, Any]) -> None:
        path = self.path("component_map")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(component_map, sort_keys=False))

    # -- component library (Prisma SQLite) -----------------------------------

    @property
    def components_db_path(self) -> Path:
        return self.path("components_db")

    def _init_components_db(self) -> None:
        from epinterface.sbem.prisma.client import PrismaSettings

        PrismaSettings.New(
            database_path=self.components_db_path, if_exists="raise", auto_register=False
        )

    def prisma_client(self) -> Prisma:
        """A Prisma client bound to this workspace's components-lib.db.

        Caller is responsible for connect()/disconnect() (or `with workspace.prisma_client():`).
        """
        from epinterface.sbem.prisma.client import PrismaSettings

        settings = PrismaSettings.New(
            database_path=self.components_db_path, if_exists="ignore", auto_register=False
        )
        return settings.db

    # -- priors ----------------------------------------------------------------

    def read_priors(self) -> dict[str, Any]:
        path = self.path("priors")
        if not path.exists():
            return {"registry": {"fields": []}, "priors": {}, "joints": [], "scenarios": []}
        return yaml.safe_load(path.read_text()) or {}

    def write_priors(self, config: dict[str, Any]) -> None:
        path = self.path("priors")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(config, sort_keys=False))

    # -- GIS -------------------------------------------------------------------

    def read_gis_dataset(self) -> dict[str, Any] | None:
        path = self.path("gis_dir") / "dataset.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def write_gis_dataset(self, dataset: dict[str, Any]) -> None:
        path = self.path("gis_dir") / "dataset.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dataset))

    def clear_gis_dataset(self) -> None:
        path = self.path("gis_dir") / "dataset.json"
        path.unlink(missing_ok=True)
