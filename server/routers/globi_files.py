"""globi run files API router: building.yml, manifest.yml, artifacts.yml from the saved project."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dependencies import get_workspace
from services.globi_run_files import GlobiFilesError, generate_run_files, run_file_status
from services.globi_runs import GlobiRunError, latest_runs, scenario_manifests, start_building_run, start_sample_run
from services.jobs import JobError, get_job
from services.workspace import ProjectWorkspace

router = APIRouter(prefix="/api/globi-files", tags=["globi-files"])


class BuildingGeometry(BaseModel):
    """The single building's shape; globi's MinimalBuildingSpec checks the bounds."""

    length: float = 20.0
    width: float = 15.0
    num_floors: int = 2
    f2f_height: float = 3.5
    wwr: float = 0.3


class GenerateRequest(BaseModel):
    name: str = "sbem-ui"
    epwzip_file: str = ""
    context: dict[str, str] = Field(default_factory=dict)
    building: BuildingGeometry = Field(default_factory=BuildingGeometry)


@router.get("/")
async def get_status(workspace: ProjectWorkspace = Depends(get_workspace)) -> dict[str, Any]:
    """Saved semantic fields (for the building values), weather files and the saved GIS."""
    return run_file_status(workspace)


@router.post("/generate")
async def generate(
    body: GenerateRequest, workspace: ProjectWorkspace = Depends(get_workspace)
) -> dict[str, Any]:
    """Write globi's run files into the project and return how to run them."""
    try:
        return generate_run_files(
            workspace, body.name, body.epwzip_file, body.context, body.building.model_dump()
        )
    except GlobiFilesError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class SampleRunRequest(BaseModel):
    n: int = Field(10, ge=1)
    #: Scenario values to run, each on the same buildings; empty runs every generated manifest.
    scenarios: list[str] = Field(default_factory=list)


@router.get("/scenarios")
async def get_scenarios(workspace: ProjectWorkspace = Depends(get_workspace)) -> dict[str, Any]:
    """The Scenario values that have a generated batch manifest."""
    return {"scenarios": list(scenario_manifests(workspace))}


@router.post("/run-building")
async def run_building(workspace: ProjectWorkspace = Depends(get_workspace)) -> dict[str, Any]:
    """Simulate building.yml in the background (EnergyPlus on this machine)."""
    try:
        return start_building_run(workspace).as_dict()
    except (GlobiRunError, JobError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/run-sample")
async def run_sample(body: SampleRunRequest, workspace: ProjectWorkspace = Depends(get_workspace)) -> dict[str, Any]:
    """Simulate a random sample of the stock under each scenario on globi's local Hatchet."""
    try:
        return start_sample_run(workspace, body.n, body.scenarios or list(scenario_manifests(workspace))).as_dict()
    except (GlobiRunError, JobError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/jobs/{job_id}")
async def get_run(job_id: str) -> dict[str, Any]:
    """One run's status, current stage and, when done, its results."""
    try:
        return get_job(job_id).as_dict()
    except JobError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs")
async def get_latest_runs(workspace: ProjectWorkspace = Depends(get_workspace)) -> dict[str, Any]:
    """The project's last example and sample runs, so a reloaded page picks them up again."""
    return latest_runs(workspace)
