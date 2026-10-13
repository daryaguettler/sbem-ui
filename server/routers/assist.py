"""AI drafting: describe a definition in plain language, get a checked draft back."""

from typing import Any

from dependencies import get_workspace
from fastapi import APIRouter, Depends, HTTPException
from models.semantic_fields import SemanticField
from pydantic import BaseModel, Field
from services.gis_session import get_dataset
from services.llm_assist import (
    AssistFailed,
    AssistUnavailable,
    check_field,
    credentials_available,
    draft_to_semantic_field,
    request_draft,
    summarize_gis,
)
from services.workspace import ProjectWorkspace

router = APIRouter(prefix="/api/assist", tags=["assist"])


class SemanticFieldAssistRequest(BaseModel):
    description: str = Field(min_length=3, max_length=4000)
    field_name: str | None = None
    field_id: str | None = None
    existing_fields: list[SemanticField] = Field(default_factory=list)
    previous: dict[str, Any] | None = None


@router.get("/status")
def assist_status() -> dict[str, Any]:
    available = credentials_available()
    return {
        "available": available,
        "reason": None
        if available
        else "Set ANTHROPIC_API_KEY on the backend to enable AI drafting.",
    }


@router.post("/semantic-field")
def draft_semantic_field(
    payload: SemanticFieldAssistRequest,
    workspace: ProjectWorkspace = Depends(get_workspace),
) -> dict[str, Any]:
    """Draft one semantic field from a description and check it against the GIS data."""
    dataset = get_dataset(workspace)
    if not dataset or not dataset.get("rows"):
        raise HTTPException(
            status_code=400,
            detail="Upload GIS data first: drafts are built from its columns.",
        )

    existing = [
        field.model_dump()
        for field in payload.existing_fields
        if field.id != payload.field_id and field.name
    ]
    try:
        draft = request_draft(
            payload.description,
            summarize_gis(dataset),
            existing,
            previous=payload.previous,
            field_name=payload.field_name,
        )
    except AssistUnavailable as err:
        raise HTTPException(status_code=503, detail=str(err)) from err
    except AssistFailed as err:
        raise HTTPException(status_code=502, detail=str(err)) from err

    field = draft_to_semantic_field(draft.field, payload.field_id)
    column_names = [column["name"] for column in dataset.get("columns", [])]
    checks = check_field(field, dataset.get("rows", []), column_names)
    if field["name"] in {f["name"] for f in existing}:
        checks["errors"].append(f"A field named '{field['name']}' already exists.")

    return {
        "field": field,
        "draft": draft.field.model_dump(),
        "assumptions": draft.assumptions,
        "questions": draft.questions,
        **checks,
    }
