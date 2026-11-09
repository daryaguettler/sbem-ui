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
    from services.schedule_variability import ScheduleVariabilityConfig, perturb_space_use

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


class ProfilePreviewRequest(BaseModel):
    config: dict[str, Any]
    value: str | None = None
    limit: str = "Fraction"
    values: list[float] = Field(min_length=24, max_length=24)
    # the Day record name globi seeds the hourly noise with
    day_name: str
    n: int = Field(default=20, ge=1, le=100)


def perturb_profile(values: list[float], limit: str, day_name: str, params: Any, seed: int, building_id: str) -> list[float]:
    """One building's copy of a day profile, as globi's perturb_space_use makes it.

    shortcut: mirrors the body of globi's private perturb_day (tests/test_schedule_editor.py
    checks they agree); switch to a public globi helper once it exposes one."""
    import numpy as np
    from epinterface.sbem.components.schedules import TypeLimits
    from services.schedule_variability import _ar1, _clipped_normal, seeded_rng, shift_values

    def rng(*keys: str):
        return seeded_rng(seed, building_id, *keys)

    out = np.array(values, dtype=float)
    if limit == "Temperature":
        out = out + _clipped_normal(rng("setpoint_offset"), params.setpoint_offset_std_c)
    else:
        out = shift_values(out, _clipped_normal(rng("time_shift"), params.time_shift_std_h))
        if params.hourly_noise_std > 0:
            out = out + _ar1(rng("day", day_name), params.hourly_noise_std, params.hourly_noise_autocorr)
    limits = TypeLimits[limit]
    return np.clip(out, limits.Lower_Limit_Value, limits.Upper_Limit_Value).tolist()


@router.post("/preview-profile")
async def preview_profile(body: ProfilePreviewRequest):
    """n buildings' copies of one (possibly unsaved) day profile from the schedule editor."""
    from services.schedule_variability import ScheduleVariabilityConfig

    try:
        config = ScheduleVariabilityConfig.model_validate(body.config)
        params = config.default if body.value is None else config.params_for_value(body.value)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if body.limit not in ("Fraction", "Temperature", "AnyNumber"):
        raise HTTPException(status_code=422, detail=f"Unknown limit {body.limit!r}.")
    return {
        "samples": [
            perturb_profile(body.values, body.limit, body.day_name, params, config.seed, f"preview-{i}")
            for i in range(body.n)
        ]
    }
