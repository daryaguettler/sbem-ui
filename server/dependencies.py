"""Shared FastAPI dependencies."""

from fastapi import HTTPException, Request

from services.workspace import ProjectWorkspace


def get_workspace(request: Request) -> ProjectWorkspace:
    """Return the currently-open project workspace, or 409 if none is open."""
    workspace: ProjectWorkspace | None = getattr(request.app.state, "workspace", None)
    if workspace is None:
        raise HTTPException(status_code=409, detail="No project workspace is open.")
    return workspace
