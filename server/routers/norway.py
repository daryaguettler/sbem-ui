"""Runner API: validate inputs, preview retrofits, sampling settings, local test runs.

Everything here is delegated to the project's runner repo (norway-globi) through
`services.norway_runner`; see its docstring.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dependencies import get_workspace
from services.norway_runner import (
    RunnerError,
    get_job,
    read_sampling,
    runner_status,
    start_job,
    write_sampling,
)
from services.workspace import ProjectWorkspace

router = APIRouter(prefix="/api/runner", tags=["runner"])


class JobRequest(BaseModel):
    command: str
    options: dict[str, Any] = Field(default_factory=dict)


@router.get("/status")
async def get_runner_status(workspace: ProjectWorkspace = Depends(get_workspace)):
    """Whether this project has a runner repo to delegate to."""
    return runner_status(workspace.runner)


@router.post("/jobs")
async def post_job(body: JobRequest, workspace: ProjectWorkspace = Depends(get_workspace)):
    """Start validate / retrofit-preview / sampling / test-run in the background."""
    try:
        return start_job(workspace.runner, body.command, body.options).as_dict()
    except RunnerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, workspace: ProjectWorkspace = Depends(get_workspace)):
    """Poll a job."""
    try:
        return get_job(job_id).as_dict()
    except RunnerError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/sampling")
async def get_sampling(workspace: ProjectWorkspace = Depends(get_workspace)):
    """Strata / budget / partition settings from training.yml and inference.yml."""
    return read_sampling(workspace.path("training_config"), workspace.path("inference_config"))


@router.post("/sampling")
async def post_sampling(
    body: dict[str, Any], workspace: ProjectWorkspace = Depends(get_workspace)
):
    """Write the settings back (comments in the files are kept)."""
    training, inference = workspace.path("training_config"), workspace.path("inference_config")
    try:
        write_sampling(training, inference, body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return read_sampling(training, inference)
