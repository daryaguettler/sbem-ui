"""Schedule variability preview: what globi's per-building perturbation does to one
SpaceUse from the project's component library, for a handful of synthetic buildings."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError

from dependencies import get_workspace
from services.workspace import ProjectWorkspace

router = APIRouter(prefix="/api/schedule-variability", tags=["schedule-variability"])


class PreviewRequest(BaseModel):
    config: dict[str, Any]
    space_use: str
    # semantic field value whose overrides to preview; None previews `default`
    value: str | None = None
    n: int = Field(default=20, ge=1, le=100)


def _curves(space_use: Any) -> dict[str, list[float]]:
    """January Monday, the first representative day, of the two most visible loads."""
    return {
        "occupancy": space_use.Occupancy.Schedule.January.Monday.Values,
        "equipment": space_use.Equipment.Schedule.January.Monday.Values,
    }


@router.post("/preview")
async def preview(body: PreviewRequest, workspace: ProjectWorkspace = Depends(get_workspace)):
    from epinterface.sbem.prisma.client import SBEMDeepObjectNotFoundError, deep_fetcher
    from globi.models.schedule_variability import ScheduleVariabilityConfig, perturb_space_use

    try:
        config = ScheduleVariabilityConfig.model_validate(body.config)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    params = config.default if body.value is None else config.params_for_value(body.value)

    client = workspace.prisma_client()
    client.connect()
    try:
        _, space_use = deep_fetcher.SpaceUse.get_deep_object(body.space_use, db=client)
    except SBEMDeepObjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        client.disconnect()

    samples = []
    for i in range(body.n):
        perturbed, draws = perturb_space_use(space_use, params, config.seed, f"preview-{i}")
        samples.append({"curves": _curves(perturbed), "draws": draws})
    return {"base": _curves(space_use), "samples": samples}
