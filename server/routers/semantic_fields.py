"""Semantic fields API router."""

from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from dependencies import get_workspace
from models.semantic_fields import SemanticField, SemanticFieldsConfig
from services.gis_session import get_dataset
from services.semantic_fields import (
    semantic_fields_to_yaml,
    validate_semantic_field,
    validate_semantic_fields_config,
)
from services.semantic_transform import preview_semantic_fields
from services.template_loader import list_yaml_templates, load_yaml_template
from services.workspace import ProjectWorkspace

router = APIRouter(prefix="/api/semantic-fields", tags=["semantic-fields"])


class SemanticFieldsPayload(BaseModel):
    name: str = "Semantic Fields"
    building_id_col: str | None = None
    num_floors_col: str | None = None
    fields: list[SemanticField] = Field(default_factory=list)


def _gis_column_names(workspace: ProjectWorkspace) -> list[str]:
    dataset = get_dataset(workspace)
    if not dataset:
        return []
    return [column["name"] for column in dataset.get("columns", [])]


@router.get("/")
async def get_semantic_fields() -> dict[str, Any]:
    """Get all semantic fields."""
    return {"fields": []}


@router.post("/")
async def create_semantic_field(
    field: SemanticField, workspace: ProjectWorkspace = Depends(get_workspace)
) -> dict[str, Any]:
    """Create a new semantic field."""
    errors = validate_semantic_field(field.model_dump(by_alias=False), _gis_column_names(workspace))
    if errors:
        raise HTTPException(status_code=400, detail={"valid": False, "errors": errors})
    return {"field": field}


@router.get("/templates")
async def get_semantic_field_templates() -> dict[str, Any]:
    """Get available semantic field templates."""
    return {"templates": list_yaml_templates("semantic_fields")}


@router.get("/templates/{template_name}")
async def get_semantic_field_template(template_name: str) -> dict[str, Any]:
    """Get a specific semantic field template."""
    return load_yaml_template("semantic_fields", template_name)


class PreviewRequest(SemanticFieldsPayload):
    sample_limit: int = 25


def _fields_payload(payload: SemanticFieldsPayload) -> list[dict[str, Any]]:
    return [field.model_dump(by_alias=False) for field in payload.fields]


@router.post("/preview")
async def preview_semantic_fields_endpoint(
    payload: PreviewRequest, workspace: ProjectWorkspace = Depends(get_workspace)
) -> dict[str, Any]:
    """Preview semantic field transformations against uploaded GIS data."""
    dataset = get_dataset(workspace)
    if dataset is None:
        raise HTTPException(status_code=400, detail="Upload and validate GIS data first.")
    if not dataset.get("validated"):
        raise HTTPException(status_code=400, detail="Validate GIS data before previewing semantic fields.")

    fields = _fields_payload(payload)
    preview = preview_semantic_fields(dataset.get("rows", []), fields, payload.sample_limit)
    validation = validate_semantic_fields_config(
        {
            "name": payload.name,
            "building_id_col": payload.building_id_col,
            "num_floors_col": payload.num_floors_col,
            "fields": fields,
        },
        _gis_column_names(workspace),
    )

    return {
        **preview,
        "validation": validation,
    }


@router.post("/validate")
async def validate_semantic_fields(
    payload: SemanticFieldsPayload, workspace: ProjectWorkspace = Depends(get_workspace)
) -> dict[str, Any]:
    """Validate semantic field configuration."""
    config = payload.model_dump()
    result = validate_semantic_fields_config(
        {
            "name": config["name"],
            "building_id_col": config.get("building_id_col"),
            "num_floors_col": config.get("num_floors_col"),
            "fields": [field.model_dump(by_alias=False) for field in payload.fields],
        },
        _gis_column_names(workspace),
    )
    return result


@router.post("/export")
async def export_semantic_fields(payload: SemanticFieldsPayload) -> Response:
    """Export semantic fields as YAML."""
    config = payload.model_dump()
    yaml_payload = semantic_fields_to_yaml(
        {
            "name": config["name"],
            "building_id_col": config.get("building_id_col"),
            "num_floors_col": config.get("num_floors_col"),
            "fields": [field.model_dump(by_alias=False) for field in payload.fields],
        }
    )
    content = yaml.safe_dump(yaml_payload, sort_keys=False)
    return Response(content=content, media_type="application/x-yaml")
