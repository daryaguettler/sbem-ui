"""Component library API router: CRUD over real epinterface component records,
stored in the open workspace's components-lib.db."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dependencies import get_workspace
from services import component_library as lib
from services.workspace import ProjectWorkspace

router = APIRouter(prefix="/api/component-library", tags=["component-library"])


class CheckExistenceRequest(BaseModel):
    names: list[str]


def _client(workspace: ProjectWorkspace):
    client = workspace.prisma_client()
    client.connect()
    return client


@router.get("/types")
async def get_types():
    return {"types": lib.list_component_types()}


@router.get("/schema/{component_type}")
async def get_schema(component_type: str):
    try:
        return lib.get_component_type_schema(component_type)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{component_type}/records")
async def list_records(component_type: str, workspace: ProjectWorkspace = Depends(get_workspace)):
    client = _client(workspace)
    try:
        return {"records": lib.list_records(client, component_type)}
    except AttributeError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown component type: {component_type!r}") from exc
    finally:
        client.disconnect()


@router.get("/{component_type}/records/{name}")
async def get_record(component_type: str, name: str, workspace: ProjectWorkspace = Depends(get_workspace)):
    client = _client(workspace)
    try:
        record = lib.get_record(client, component_type, name)
    except AttributeError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown component type: {component_type!r}") from exc
    finally:
        client.disconnect()
    if record is None:
        raise HTTPException(status_code=404, detail=f"{component_type} record {name!r} not found.")
    return record


@router.post("/{component_type}/records")
async def create_record(
    component_type: str, payload: dict[str, Any], workspace: ProjectWorkspace = Depends(get_workspace)
):
    client = _client(workspace)
    try:
        return lib.create_record(client, component_type, payload)
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        client.disconnect()


@router.put("/{component_type}/records/{name}")
async def update_record(
    component_type: str,
    name: str,
    payload: dict[str, Any],
    workspace: ProjectWorkspace = Depends(get_workspace),
):
    client = _client(workspace)
    try:
        return lib.update_record(client, component_type, name, payload)
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        client.disconnect()


@router.delete("/{component_type}/records/{name}")
async def delete_record(component_type: str, name: str, workspace: ProjectWorkspace = Depends(get_workspace)):
    client = _client(workspace)
    try:
        lib.delete_record(client, component_type, name)
    except AttributeError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown component type: {component_type!r}") from exc
    finally:
        client.disconnect()
    return {"deleted": True}


@router.post("/{component_type}/check-existence")
async def check_existence(
    component_type: str,
    payload: CheckExistenceRequest,
    workspace: ProjectWorkspace = Depends(get_workspace),
):
    client = _client(workspace)
    try:
        return {"existence": lib.check_existence(client, component_type, payload.names)}
    finally:
        client.disconnect()
