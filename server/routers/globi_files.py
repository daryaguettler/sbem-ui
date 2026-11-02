"""globi run files API router: building.yml, manifest.yml, artifacts.yml from the saved project."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dependencies import get_workspace
from services.globi_run_files import GlobiFilesError, generate_run_files, run_file_status
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
