"""Project workspace API router: create/open/close the on-disk project directory."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from services.workspace import ProjectWorkspace, WorkspaceError

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


class CreateWorkspaceRequest(BaseModel):
    path: str
    name: str


class OpenWorkspaceRequest(BaseModel):
    path: str


@router.post("/create")
async def create_workspace(request: Request, body: CreateWorkspaceRequest):
    """Scaffold a brand-new project workspace directory and open it."""
    try:
        workspace = ProjectWorkspace.create(Path(body.path).expanduser(), body.name)
    except WorkspaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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


@router.post("/close")
async def close_workspace(request: Request):
    """Close the currently open workspace."""
    request.app.state.workspace = None
    return {"open": False}
