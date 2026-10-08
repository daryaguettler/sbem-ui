"""Prior trees API router.

The editor keeps a whole `semantic_priors.RegionConfig` in the browser, so most
of these endpoints take that config plus the project's semantic fields and answer
a question about them: what can I condition on, what would this prior look like,
is it valid, what does it produce. The GIS rows they read come from the open
workspace, never from the request body.
"""

from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from dependencies import get_workspace
from models.semantic_fields import SemanticField
from services.gis_session import get_dataset
from services.prior_trees import (
    DEFAULT_MIN_COUNT,
    DEFAULT_SEPARATOR,
    PriorTreeError,
    condition_preview,
    conditioning_candidates,
    dependency_payload,
    enriched_rows,
    generate_prior,
    preview_scenarios,
    sample_prior_tree,
    scenario_targets,
    suggest_registry,
    validate_prior_tree,
)
from services.template_loader import list_yaml_templates, load_yaml_template
from services.workspace import ProjectWorkspace

router = APIRouter(prefix="/api/prior-trees", tags=["prior-trees"])


class SemanticFieldsBody(BaseModel):
    """The semantic fields as the editor currently has them (not yet saved to disk)."""

    fields: list[SemanticField] = Field(default_factory=list)


class PriorTreeValidationRequest(SemanticFieldsBody):
    config: dict[str, Any] = Field(default_factory=dict)
    required_targets: list[str] = Field(default_factory=list)


class GeneratePriorRequest(SemanticFieldsBody):
    target: str
    target_values: list[str] = Field(default_factory=list)
    condition_on: list[str] = Field(default_factory=list)
    method: str = "uniform"
    observed_column: str | None = None
    dtype: str = "categorical"
    min_count: int = DEFAULT_MIN_COUNT
    separator: str = DEFAULT_SEPARATOR


class ConditionPreviewRequest(SemanticFieldsBody):
    condition_on: list[str] = Field(default_factory=list)
    separator: str = DEFAULT_SEPARATOR


class SamplePriorRequest(SemanticFieldsBody):
    config: dict[str, Any] = Field(default_factory=dict)
    n: int = 1000
    seed: int | None = 0


class RegistrySuggestionRequest(SemanticFieldsBody):
    config: dict[str, Any] = Field(default_factory=dict)


def _fields(body: SemanticFieldsBody) -> list[dict[str, Any]]:
    return [field.model_dump(by_alias=False) for field in body.fields]


def _rows(workspace: ProjectWorkspace, body: SemanticFieldsBody) -> list[dict[str, Any]]:
    """The project's GIS rows with deterministic semantic fields applied."""
    return enriched_rows(get_dataset(workspace), _fields(body))


@router.get("/")
async def get_prior_trees(workspace: ProjectWorkspace = Depends(get_workspace)):
    """The prior config saved in the open project."""
    return {"config": workspace.read_priors()}


@router.get("/templates")
async def get_prior_tree_templates():
    """Get available prior tree templates."""
    return {"templates": list_yaml_templates("prior_trees")}


@router.get("/templates/{template_name}")
async def get_prior_tree_template(template_name: str):
    """Get a specific prior tree template."""
    return load_yaml_template("prior_trees", template_name)


@router.post("/fields")
async def get_conditioning_fields(
    body: SemanticFieldsBody, workspace: ProjectWorkspace = Depends(get_workspace)
):
    """Every field a prior can condition on, with how it's distributed in the GIS data."""
    dataset = get_dataset(workspace)
    fields = _fields(body)
    return {
        "candidates": conditioning_candidates(dataset, fields),
        "rowCount": len(dataset.get("rows", [])) if dataset else 0,
        "hasGisData": dataset is not None,
        "gisValidated": bool(dataset and dataset.get("validated")),
    }


@router.post("/condition-preview")
async def preview_conditioning(
    body: ConditionPreviewRequest, workspace: ProjectWorkspace = Depends(get_workspace)
):
    """How many table rows a choice of conditioning fields produces, before generating."""
    return condition_preview(_rows(workspace, body), body.condition_on, body.separator)


@router.post("/generate")
async def generate_prior_endpoint(
    body: GeneratePriorRequest, workspace: ProjectWorkspace = Depends(get_workspace)
):
    """Generate one field's prior from the chosen conditioning fields."""
    try:
        return generate_prior(
            target=body.target,
            target_values=body.target_values,
            condition_on=body.condition_on,
            rows=_rows(workspace, body),
            method=body.method,
            observed_column=body.observed_column,
            dtype=body.dtype,
            min_count=body.min_count,
            separator=body.separator,
        )
    except PriorTreeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/registry-suggestions")
async def get_registry_suggestions(
    body: RegistrySuggestionRequest, workspace: ProjectWorkspace = Depends(get_workspace)
):
    """Registry entries for fields the config references but hasn't declared yet."""
    candidates = conditioning_candidates(get_dataset(workspace), _fields(body))
    return {"fields": suggest_registry(body.config, candidates)}


@router.post("/validate")
async def validate_prior_tree_endpoint(payload: PriorTreeValidationRequest):
    """Validate the config against the real sampling models plus the project's needs."""
    return validate_prior_tree(payload.config, payload.required_targets)


@router.post("/dependencies")
async def get_dependencies(payload: PriorTreeValidationRequest):
    """The prior tree's sampling order and edges, for the graph view."""
    return dependency_payload(payload.config)


@router.post("/sample")
async def sample_prior(
    body: SamplePriorRequest, workspace: ProjectWorkspace = Depends(get_workspace)
):
    """Sample the config over the project's own buildings and summarize the draws."""
    try:
        return sample_prior_tree(body.config, _rows(workspace, body), body.n, body.seed)
    except PriorTreeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/scenario-targets")
async def get_scenario_targets(payload: PriorTreeValidationRequest):
    """Features a scenario can override or branch on, with their declared values."""
    return {"targets": scenario_targets(payload.config)}


@router.post("/scenarios/preview")
async def preview_scenarios_endpoint(
    body: SamplePriorRequest, workspace: ProjectWorkspace = Depends(get_workspace)
):
    """Sample one baseline, then apply every scenario to it and report the differences."""
    try:
        return preview_scenarios(body.config, _rows(workspace, body), body.n, body.seed)
    except PriorTreeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/export")
async def export_prior_tree(payload: PriorTreeValidationRequest) -> Response:
    """Export prior tree as YAML."""
    content = yaml.safe_dump(payload.config, sort_keys=False)
    return Response(content=content, media_type="application/x-yaml")
