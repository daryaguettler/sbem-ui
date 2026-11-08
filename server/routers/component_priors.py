"""Component priors API router: preview a component's curves and the variants they make."""

from typing import Any

from dependencies import get_workspace
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from services import component_priors
from services.workspace import ProjectWorkspace

router = APIRouter(prefix="/api/component-priors", tags=["component-priors"])


class PreviewRequest(BaseModel):
    component_type: str | None = None
    name: str | None = None
    prior: dict[str, Any]


@router.post("/preview")
async def preview(payload: PreviewRequest, workspace: ProjectWorkspace = Depends(get_workspace)) -> dict[str, Any]:
    """Each field's curve and n values, the variants, and why any variant can't be built."""
    db = workspace.prisma_client()
    db.connect()
    try:
        return component_priors.preview(payload.component_type, payload.name, payload.prior, db)
    finally:
        db.disconnect()
