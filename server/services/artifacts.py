"""Saving the artifacts the editors generate into the open project workspace, and reading them back.

The "Export YAML" buttons hand the user a download; saving writes those exact same bytes
into the project directory instead, so closing the browser (or the project) doesn't lose
the work. `ARTIFACTS` is the one place that knows which file each editor's working state
belongs in, and how to turn that state into the document that lands on disk -- the same
converters the export endpoints use, so a saved file and a downloaded one are identical.

Saved documents are written in the *template* shape (`Name:`/`Fields:` ...), which is what
the frontend stores already know how to load -- so reading a project back in reuses the
template-loading path rather than needing a second importer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from services.semantic_fields import semantic_fields_to_yaml
from services.globi_component_map import to_globi
from services.workspace import ProjectWorkspace

# Files we're willing to render in the browser's file viewer. Everything else
# (components-lib.db, most notably) is listed but not viewable.
TEXT_SUFFIXES = {".yaml", ".yml", ".json", ".geojson", ".csv", ".txt", ".md"}

# A cleaned GIS dataset.json can be tens of MB; don't ship all of it to the viewer.
MAX_VIEW_BYTES = 512 * 1024


class ArtifactError(Exception):
    """Raised for unknown artifact kinds and out-of-workspace file paths."""


def _as_is(payload: dict[str, Any]) -> dict[str, Any]:
    """Editors whose working state is already the on-disk document."""
    return payload


@dataclass(frozen=True)
class ArtifactSpec:
    """One saveable editor output: where it lives and how its state becomes a document."""

    kind: str
    label: str
    file_key: str
    description: str
    to_document: Callable[[dict[str, Any]], dict[str, Any]]


ARTIFACTS: dict[str, ArtifactSpec] = {
    "semantic-fields": ArtifactSpec(
        kind="semantic-fields",
        label="Semantic fields",
        file_key="semantic_fields",
        description="Field definitions and their GIS transformation rules.",
        to_document=semantic_fields_to_yaml,
    ),
    "component-map": ArtifactSpec(
        kind="component-map",
        label="Component map",
        file_key="component_map_selectors",
        description="Per-node selector declarations over the component tree.",
        to_document=_as_is,
    ),
    "priors": ArtifactSpec(
        kind="priors",
        label="Prior trees",
        file_key="priors",
        description="Prior distributions for stochastic semantic fields.",
        to_document=_as_is,
    ),
    "retrofits": ArtifactSpec(
        kind="retrofits",
        label="Retrofit packages",
        file_key="retrofits",
        description="Retrofit packages applied to every prior draw.",
        to_document=_as_is,
    ),
}


def get_spec(kind: str) -> ArtifactSpec:
    spec = ARTIFACTS.get(kind)
    if spec is None:
        known = ", ".join(sorted(ARTIFACTS))
        raise ArtifactError(f"Unknown artifact kind '{kind}'. Expected one of: {known}.")
    return spec


# -- saving / reading back ---------------------------------------------------


def save_artifact(
    workspace: ProjectWorkspace, kind: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """Write one editor's working state into the project, returning its file entry."""
    spec = get_spec(kind)
    document = spec.to_document(payload)

    path = workspace.path(spec.file_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document, sort_keys=False))
    if kind == "component-map":
        # globi reads the pruned map; when both keys point at one file, this wins
        workspace.write_generated_component_map(to_globi(document))

    return _file_entry(workspace, path)


def read_artifact(workspace: ProjectWorkspace, kind: str) -> dict[str, Any]:
    """Read one saved artifact back, or report that it hasn't been saved yet."""
    spec = get_spec(kind)
    path = workspace.path(spec.file_key)
    if kind == "component-map" and not path.exists() and workspace.path("component_map").exists():
        # no editor file yet, but a globi map exists (e.g. a repo's inputs/): open that
        path = workspace.path("component_map")

    if not path.exists():
        return {
            "kind": spec.kind,
            "label": spec.label,
            "path": workspace.relative(spec.file_key),
            "exists": False,
            "savedAt": None,
            "content": None,
        }

    return {
        "kind": spec.kind,
        "label": spec.label,
        "path": workspace.relative(spec.file_key),
        "exists": True,
        "savedAt": _modified_at(path),
        "content": yaml.safe_load(path.read_text()) or {},
    }


def list_artifacts(workspace: ProjectWorkspace) -> list[dict[str, Any]]:
    """Saved-or-not status for every artifact kind, in workflow order."""
    return [
        {
            "kind": spec.kind,
            "label": spec.label,
            "description": spec.description,
            "path": workspace.relative(spec.file_key),
            "exists": workspace.path(spec.file_key).exists(),
            "savedAt": _modified_at(workspace.path(spec.file_key)),
        }
        for spec in ARTIFACTS.values()
    ]


# -- browsing the project directory ------------------------------------------


def list_workspace_files(workspace: ProjectWorkspace) -> list[dict[str, Any]]:
    """Every file in the project directory, newest-looking layout order (sorted by path)."""
    root = workspace.root
    files = [
        _file_entry(workspace, path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.name.startswith(".")
    ]
    return files


def read_workspace_file(workspace: ProjectWorkspace, relative_path: str) -> dict[str, Any]:
    """Read one project file for display, truncating anything over `MAX_VIEW_BYTES`."""
    path = _resolve_within_workspace(workspace, relative_path)
    if not path.is_file():
        raise ArtifactError(f"'{relative_path}' is not a file in this project.")

    entry = _file_entry(workspace, path)
    if not entry["viewable"]:
        return {**entry, "content": None, "truncated": False}

    raw = path.read_bytes()
    truncated = len(raw) > MAX_VIEW_BYTES
    content = raw[:MAX_VIEW_BYTES].decode("utf-8", errors="replace")
    return {**entry, "content": content, "truncated": truncated}


def _resolve_within_workspace(workspace: ProjectWorkspace, relative_path: str) -> Path:
    """Resolve a client-supplied relative path, refusing anything outside the project."""
    root = workspace.root.resolve()
    target = (root / relative_path).resolve()
    if target != root and not target.is_relative_to(root):
        raise ArtifactError(f"'{relative_path}' is outside the project directory.")
    if not target.exists():
        raise ArtifactError(f"'{relative_path}' does not exist in this project.")
    return target


def _file_entry(workspace: ProjectWorkspace, path: Path) -> dict[str, Any]:
    # Both sides are resolved: on macOS the workspace root is often handed to us as
    # /var/... while a resolved path reads /private/var/..., and relative_to() is literal.
    root = workspace.root
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    spec = next(
        (s for s in ARTIFACTS.values() if workspace.relative(s.file_key) == relative), None
    )
    return {
        "path": relative,
        "name": path.name,
        "size": path.stat().st_size,
        "modifiedAt": _modified_at(path),
        "viewable": path.suffix.lower() in TEXT_SUFFIXES,
        "kind": spec.kind if spec else None,
        "label": spec.label if spec else None,
    }


def _modified_at(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
