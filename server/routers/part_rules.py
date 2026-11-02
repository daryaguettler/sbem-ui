"""Part rules API router: compile them, import them from an existing map, list the parts."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_workspace
from services import part_rules
from services.workspace import ProjectWorkspace

router = APIRouter(prefix="/api/part-rules", tags=["part-rules"])


@router.get("/parts")
async def get_parts() -> dict[str, Any]:
    """Every leaf part a rule decides, with its library type and group."""
    return {
        "parts": [
            {"path": path, "type": part_rules._type(path), "group": part_rules._group_of(path)}
            for path in part_rules.parts()
        ]
    }


@router.post("/compile")
async def compile_rules(workspace: ProjectWorkspace = Depends(get_workspace)) -> dict[str, Any]:
    """Rebuild the component map and generated records from the saved rules."""
    return part_rules.compile_project(workspace)


@router.post("/import")
async def import_rules(workspace: ProjectWorkspace = Depends(get_workspace)) -> dict[str, Any]:
    """Rules inferred from the project's current component map and library (not saved)."""
    component_map = workspace.read_generated_component_map()
    if not component_map:
        raise HTTPException(status_code=400, detail="This project has no component map to import from.")
    db = workspace.prisma_client()
    db.connect()
    try:
        rules, notes = part_rules.infer(component_map, workspace.read_semantic_fields(), db)
    finally:
        db.disconnect()
    return {"rules": rules, "notes": notes}


@router.post("/baseline")
async def baseline_rules(workspace: ProjectWorkspace = Depends(get_workspace)) -> dict[str, Any]:
    """Rules where every part uses the library's first archetype (not saved)."""
    db = workspace.prisma_client()
    db.connect()
    try:
        return {"rules": part_rules.baseline(db)}
    finally:
        db.disconnect()
