"""Component map API router."""

from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from services.component_map import (
    generate_component_names,
    preview_selector_names,
    remove_child_selectors,
    set_selector_at_path,
    validate_component_map,
)
from dependencies import get_workspace
from services.globi_component_map import check_against_library
from services.template_loader import list_yaml_templates, load_yaml_template
from services.workspace import ProjectWorkspace

router = APIRouter(prefix="/api/component-map", tags=["component-map"])


class ComponentMapValidationRequest(BaseModel):
    component_map: dict[str, Any]
    semantic_fields: list[dict[str, Any]] = Field(default_factory=list)


class SelectorPreviewRequest(BaseModel):
    source_fields: list[str]
    suffix: str | None = None
    semantic_fields: list[dict[str, Any]] = Field(default_factory=list)
    limit: int = 20


class SelectorUpdateRequest(BaseModel):
    component_map: dict[str, Any]
    path: str
    source_fields: list[str]
    suffix: str | None = None
    collapse_children: bool = False


@router.get("/")
async def get_component_map():
    """Get component map."""
    return {"components": []}


@router.post("/")
async def create_component_map(payload: ComponentMapValidationRequest):
    """Create or update component map."""
    field_names = [field.get("name") for field in payload.semantic_fields if field.get("name")]
    result = validate_component_map(payload.component_map, field_names)
    if not result["valid"]:
        raise HTTPException(status_code=400, detail=result)
    return {
        "component_map": payload.component_map,
        "generated_names": generate_component_names(payload.component_map, payload.semantic_fields),
    }


@router.get("/templates")
async def get_component_map_templates():
    """Get available component map templates."""
    return {"templates": list_yaml_templates("component_maps")}


@router.get("/templates/{template_name}")
async def get_component_map_template(template_name: str):
    """Get a specific component map template."""
    return load_yaml_template("component_maps", template_name)


@router.post("/validate")
async def validate_component_map_endpoint(payload: ComponentMapValidationRequest):
    """Validate component map against semantic fields."""
    field_names = [field.get("name") for field in payload.semantic_fields if field.get("name")]
    result = validate_component_map(payload.component_map, field_names)
    generated_names = generate_component_names(payload.component_map, payload.semantic_fields)
    return {**result, "generated_names": generated_names}


@router.post("/preview-selector")
async def preview_selector_endpoint(payload: SelectorPreviewRequest):
    """Preview generated component names for a single selector."""
    return preview_selector_names(
        payload.source_fields,
        payload.semantic_fields,
        payload.suffix,
        payload.limit,
    )


@router.post("/update-selector")
async def update_selector_endpoint(payload: SelectorUpdateRequest):
    """Apply a selector update and optionally collapse child selectors."""
    updated = set_selector_at_path(
        payload.component_map,
        payload.path,
        payload.source_fields,
        payload.suffix,
    )
    if payload.collapse_children:
        updated = remove_child_selectors(updated, payload.path)
    return {"component_map": updated}


@router.post("/export")
async def export_component_map(payload: ComponentMapValidationRequest) -> Response:
    """Export component map as YAML."""
    content = yaml.safe_dump(payload.component_map, sort_keys=False)
    return Response(content=content, media_type="application/x-yaml")


@router.post("/check")
async def check_component_map(
    n_tests: int = 200, workspace: ProjectWorkspace = Depends(get_workspace)
):
    """Resolve sampled semantic-field combinations of the saved map against the project db."""
    component_map = workspace.read_generated_component_map()
    if not component_map:
        raise HTTPException(status_code=400, detail="Save the component map first.")
    return check_against_library(
        component_map,
        workspace.read_semantic_fields(),
        workspace.components_db_path,
        n_tests=min(max(n_tests, 1), 2000),
    )
