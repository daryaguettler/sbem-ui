"""Project artifacts API router: save editor state into the project, read it back, browse files."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from dependencies import get_workspace
from services.artifacts import (
    ArtifactError,
    list_artifacts,
    list_workspace_files,
    read_artifact,
    read_workspace_file,
    save_artifact,
)
from services.workspace import ProjectWorkspace

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


class SaveArtifactRequest(BaseModel):
    """The editor's working state, in whatever shape that editor already POSTs to /export."""

    payload: dict[str, Any] = Field(default_factory=dict)


@router.get("/")
async def get_artifacts(workspace: ProjectWorkspace = Depends(get_workspace)) -> dict[str, Any]:
    """Saved-or-not status for every artifact kind in the open project."""
    return {"artifacts": list_artifacts(workspace)}


# Declared before /{kind} so "files" is never read as an artifact kind.
@router.get("/files")
async def get_workspace_files(
    workspace: ProjectWorkspace = Depends(get_workspace),
) -> dict[str, Any]:
    """Every file in the project directory, with size and last-modified time."""
    return {"root": str(workspace.root), "files": list_workspace_files(workspace)}


@router.get("/files/content")
async def get_workspace_file_content(
    path: str = Query(..., description="Path relative to the project directory."),
    workspace: ProjectWorkspace = Depends(get_workspace),
) -> dict[str, Any]:
    """Read one project file for display. Binary files come back with a null body."""
    try:
        return read_workspace_file(workspace, path)
    except ArtifactError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{kind}")
async def get_artifact(
    kind: str, workspace: ProjectWorkspace = Depends(get_workspace)
) -> dict[str, Any]:
    """Read one saved artifact back, parsed, ready to load into its editor."""
    try:
        return read_artifact(workspace, kind)
    except ArtifactError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{kind}")
async def post_artifact(
    kind: str,
    body: SaveArtifactRequest,
    workspace: ProjectWorkspace = Depends(get_workspace),
) -> dict[str, Any]:
    """Save one editor's working state into the project directory."""
    try:
        return save_artifact(workspace, kind, body.payload)
    except ArtifactError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
