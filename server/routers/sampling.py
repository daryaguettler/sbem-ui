"""Sampling API router: buildings to simulate and draws of the estimated characteristics."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dependencies import get_workspace
from models.semantic_fields import SemanticField
from services.sampling import SamplingRequestError, preview_sample, read_settings, write_sample
from services.workspace import ProjectWorkspace

router = APIRouter(prefix="/api/sampling", tags=["sampling"])


class BuildingSelection(BaseModel):
    mode: Literal["all", "random", "stratified"] = "all"
    n: int = Field(default=100, ge=1)
    per_stratum: int = Field(default=5, ge=1)
    strata: list[str] = Field(default_factory=list)


class SamplingSettings(BaseModel):
    draws: int = Field(default=1, ge=1, le=1000)
    seed: int = 0
    buildings: BuildingSelection = Field(default_factory=BuildingSelection)


class SamplingRequest(BaseModel):
    """The editor's characteristics and estimates (saved state, the page checks) plus the settings."""

    fields: list[SemanticField] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    settings: SamplingSettings = Field(default_factory=SamplingSettings)


def _args(body: SamplingRequest) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    return [f.model_dump(by_alias=False) for f in body.fields], body.config, body.settings.model_dump()


@router.get("/")
async def get_settings(workspace: ProjectWorkspace = Depends(get_workspace)) -> dict[str, Any]:
    """The saved sampling settings (defaults when none are saved)."""
    return read_settings(workspace)


@router.post("/preview")
async def preview(body: SamplingRequest, workspace: ProjectWorkspace = Depends(get_workspace)) -> dict[str, Any]:
    """Buildings, draws and simulations the settings produce."""
    try:
        return preview_sample(workspace, *_args(body))
    except SamplingRequestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/write")
async def write(body: SamplingRequest, workspace: ProjectWorkspace = Depends(get_workspace)) -> dict[str, Any]:
    """Write gis/buildings-sampled.geojson and sampling.yaml."""
    try:
        return write_sample(workspace, *_args(body))
    except SamplingRequestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
