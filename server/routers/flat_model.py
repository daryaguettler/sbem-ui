"""Single building API: the flat model form, saving it, and running it through globi.

Runs are runner jobs: poll them with `GET /api/runner/jobs/{id}`.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_workspace
from services.flat_model import FlatModelError, read_form, save_form, start_run
from services.norway_runner import RunnerError
from services.workspace import ProjectWorkspace

router = APIRouter(prefix="/api/flat-model", tags=["flat-model"])


def _bad_request(exc: FlatModelError | RunnerError) -> HTTPException:
    fields = getattr(exc, "fields", {})
    return HTTPException(status_code=400, detail={"message": str(exc), "fields": fields})


@router.get("")
async def get_form(workspace: ProjectWorkspace = Depends(get_workspace)):
    """The form fields with their saved values (or the example's defaults)."""
    try:
        return read_form(workspace.root)
    except FlatModelError as exc:
        raise _bad_request(exc) from exc


@router.post("")
async def post_form(body: dict[str, Any], workspace: ProjectWorkspace = Depends(get_workspace)):
    """Validate and save the building."""
    try:
        save_form(workspace.root, body)
        return read_form(workspace.root)
    except FlatModelError as exc:
        raise _bad_request(exc) from exc


@router.post("/run")
async def post_run(workspace: ProjectWorkspace = Depends(get_workspace)):
    """Simulate the saved building in the background."""
    try:
        return start_run(workspace.root).as_dict()
    except (FlatModelError, RunnerError) as exc:
        raise _bad_request(exc) from exc
