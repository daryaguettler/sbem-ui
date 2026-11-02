"""Inspect one building: trace it from its GIS row to the library records it uses."""

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from dependencies import get_workspace
from models.semantic_fields import SemanticField
from services import component_library as lib
from services.gis_session import get_dataset
from services.inspect import InspectError, inspect_building
from services.workspace import ProjectWorkspace

router = APIRouter(prefix="/api/inspect", tags=["inspect"])


class InspectRequest(BaseModel):
    building_id: str | None = None
    id_column: str
    fields: list[SemanticField] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    component_map: dict[str, Any] | None = None
    n: int = 500
    seed: int | None = 0


def _with_existence(workspace: ProjectWorkspace, tree: dict[str, Any], parts: list[dict[str, Any]]) -> None:
    """Mark each record name as existing or not; leave `exists` as None if the library can't be read."""
    types = {node["path"]: node["componentType"] for node in tree["nodes"]}
    names_by_type: dict[str, set[str]] = defaultdict(set)
    for part in parts:
        part["componentType"] = types.get(part["path"])
        for record in part["records"]:
            if part["componentType"] and record["name"]:
                names_by_type[part["componentType"]].add(record["name"])

    found: dict[tuple[str, str], bool] = {}
    try:
        client = workspace.prisma_client()
        client.connect()
        try:
            for component_type, names in names_by_type.items():
                for name, exists in lib.check_existence(client, component_type, sorted(names)).items():
                    found[(component_type, name)] = exists
        finally:
            client.disconnect()
    except Exception:  # an unreadable library still leaves the trace useful
        found = {}

    for part in parts:
        for record in part["records"]:
            record["exists"] = found.get((part["componentType"], record["name"]))


@router.post("/building")
async def inspect_building_endpoint(
    payload: InspectRequest, request: Request, workspace: ProjectWorkspace = Depends(get_workspace)
):
    dataset = get_dataset(workspace) or {}
    try:
        result = inspect_building(
            dataset.get("rows", []),
            payload.id_column,
            payload.building_id,
            [field.model_dump(by_alias=False) for field in payload.fields],
            payload.config,
            payload.component_map,
            payload.n,
            payload.seed,
        )
    except InspectError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _with_existence(workspace, request.app.state.component_tree, result["parts"])
    return result
