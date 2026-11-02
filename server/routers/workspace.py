"""Project workspace API router: create/open/close the on-disk project directory."""

from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from services.part_rules import write_baseline
from services.template_loader import list_yaml_templates, resolve_template_path
from services.workspace import ProjectWorkspace, WorkspaceError

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


class CreateWorkspaceRequest(BaseModel):
    path: str
    name: str
    #: a templates/projects/*.yml filename; its sibling folder is copied into the project
    template: str | None = None


class OpenWorkspaceRequest(BaseModel):
    path: str


#: Where new projects go unless the user picks another folder (git-ignored).
PROJECTS_DIR = Path(__file__).resolve().parents[2] / "data"


@router.get("/defaults")
async def get_defaults():
    """The folder new projects are created in by default: sbem-ui/data/<project name>."""
    return {"projectsDir": str(PROJECTS_DIR)}


@router.get("/templates")
async def get_project_templates():
    """Project templates a new project can start from (e.g. a populated component library)."""
    return {"templates": list_yaml_templates("projects")}


@router.post("/create")
async def create_workspace(request: Request, body: CreateWorkspaceRequest):
    """Scaffold a brand-new project workspace directory and open it."""
    template_dir = resolve_template_path("projects", body.template).with_suffix("") if body.template else None
    try:
        workspace = ProjectWorkspace.create(
            Path(body.path).expanduser(), body.name, template_dir=template_dir
        )
    except WorkspaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not workspace.path("part_rules").exists():
        # start from a model that runs: every part takes the library's first archetype
        write_baseline(workspace)
    request.app.state.workspace = workspace
    return workspace.status()


@router.post("/open")
async def open_workspace(request: Request, body: OpenWorkspaceRequest):
    """Open an existing project workspace directory."""
    try:
        workspace = ProjectWorkspace.open(Path(body.path).expanduser())
    except WorkspaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    request.app.state.workspace = workspace
    return workspace.status()


@router.get("/status")
async def workspace_status(request: Request):
    """Return the currently open workspace, or null if none is open."""
    workspace: ProjectWorkspace | None = getattr(request.app.state, "workspace", None)
    if workspace is None:
        return {"open": False, "workspace": None}
    return {"open": True, "workspace": workspace.status()}


@router.get("/stock-preset")
async def get_stock_preset(request: Request):
    """The ready-made characteristics the project's template came with, or null."""
    workspace: ProjectWorkspace | None = getattr(request.app.state, "workspace", None)
    path = workspace.path("stock_preset") if workspace else None
    return {"preset": yaml.safe_load(path.read_text()) if path and path.exists() else None}


@router.post("/close")
async def close_workspace(request: Request):
    """Close the currently open workspace."""
    request.app.state.workspace = None
    return {"open": False}
