"""GIS API router."""

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from dependencies import get_workspace
from models.semantic_fields import SemanticField
from services.globi_columns import (
    GLOBI_COLUMN_ROLES,
    mappings_to_semantic_field_cols,
    suggest_column_mappings,
)
from services.gis_parser import (
    build_cleaned_csv,
    build_cleaned_geojson,
    drop_incomplete_rows,
    export_columns,
    parse_gis_upload,
    validate_dataset,
)
from services.semantic_transform import apply_semantic_fields_to_rows, build_enriched_properties
from services.gis_session import (
    get_column_mappings,
    get_dataset,
    mark_validated,
    set_column_mappings,
    set_dataset,
    set_validated_columns,
)
from services.workspace import ProjectWorkspace

router = APIRouter(prefix="/api/gis", tags=["gis"])


class CleanRequest(BaseModel):
    column_mappings: dict[str, str | None] = Field(default_factory=dict)
    validate_columns: list[str] = Field(default_factory=list)
    drop_incomplete_rows: bool = False


class EnrichedExportRequest(BaseModel):
    name: str = "Semantic Fields"
    building_id_col: str | None = None
    num_floors_col: str | None = None
    fields: list[SemanticField] = Field(default_factory=list)


def _serialize_columns(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": column["name"],
            "dataType": column["data_type"],
            "uniqueValues": column.get("unique_values", []),
            "sampleValues": column.get("sample_values", []),
            "nullable": column.get("nullable", False),
            "nullCount": column.get("null_count", 0),
        }
        for column in columns
    ]


def _serialize_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    output_columns = dataset.get("output_columns") or export_columns(
        dataset.get("column_mappings", {}),
        dataset.get("validated_columns", []),
    )
    return {
        "filename": dataset.get("filename"),
        "rowCount": dataset.get("row_count", 0),
        "validated": dataset.get("validated", False),
        "cleaned": dataset.get("cleaned", False),
        "droppedRowCount": dataset.get("dropped_row_count", 0),
        "sourceFormat": dataset.get("source_format"),
        "columns": _serialize_columns(dataset.get("columns", [])),
        "columnMappings": dataset.get("column_mappings", {}),
        "validatedColumns": dataset.get("validated_columns", []),
        "outputColumns": output_columns,
        "semanticFieldCols": mappings_to_semantic_field_cols(dataset.get("column_mappings", {})),
    }


@router.get("/column-roles")
async def get_column_roles():
    """Get canonical GloBI column roles for mapping."""
    return {"roles": GLOBI_COLUMN_ROLES}


@router.post("/upload")
async def upload_gis_file(file: UploadFile, workspace: ProjectWorkspace = Depends(get_workspace)):
    """Upload and validate GIS file."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required.")

    content = await file.read()
    try:
        dataset = parse_gis_upload(file.filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {exc}") from exc

    column_names = [column["name"] for column in dataset.get("columns", [])]
    dataset["column_mappings"] = suggest_column_mappings(column_names)
    dataset["validated_columns"] = [
        dataset["column_mappings"][role["key"]]
        for role in GLOBI_COLUMN_ROLES
        if role.get("recommended") and dataset["column_mappings"].get(role["key"])
    ]
    dataset["validated"] = False

    set_dataset(workspace, dataset)
    return _serialize_dataset(dataset)


@router.get("/columns")
async def get_gis_columns(workspace: ProjectWorkspace = Depends(get_workspace)):
    """Get available columns from uploaded GIS data."""
    dataset = get_dataset(workspace)
    if dataset is None:
        return {"columns": [], "dataset": None, "roles": GLOBI_COLUMN_ROLES}

    return {
        "columns": _serialize_columns(dataset.get("columns", [])),
        "dataset": _serialize_dataset(dataset),
        "roles": GLOBI_COLUMN_ROLES,
        "columnMappings": get_column_mappings(workspace),
    }


@router.post("/preview")
async def preview_transformation(workspace: ProjectWorkspace = Depends(get_workspace)):
    """Preview transformation rule application."""
    dataset = get_dataset(workspace)
    if dataset is None:
        raise HTTPException(status_code=400, detail="Upload GIS data first.")

    return {
        "rowCount": dataset.get("row_count", 0),
        "columns": _serialize_columns(dataset.get("columns", [])),
        "sampleRows": dataset.get("rows", [])[:5],
        "columnMappings": dataset.get("column_mappings", {}),
    }


@router.post("/clean")
async def clean_gis_data(request: CleanRequest, workspace: ProjectWorkspace = Depends(get_workspace)):
    """Validate mapped GloBI columns and optionally drop incomplete rows."""
    dataset = get_dataset(workspace)
    if dataset is None:
        raise HTTPException(status_code=400, detail="Upload GIS data first.")

    dataset["column_mappings"] = request.column_mappings
    dataset["validated_columns"] = request.validate_columns
    set_column_mappings(workspace, request.column_mappings)
    set_validated_columns(workspace, request.validate_columns)

    validation = validate_dataset(
        dataset,
        column_mappings=request.column_mappings,
        validate_columns=request.validate_columns,
    )

    should_drop = request.drop_incomplete_rows and bool(request.validate_columns)
    has_null_issues = validation["incomplete_row_count"] > 0 or any(
        "contains missing values" in issue for issue in validation["issues"]
    )

    if should_drop and has_null_issues:
        dataset = drop_incomplete_rows(dataset, request.validate_columns)
        if dataset.get("row_count", 0) == 0:
            validation = {
                **validation,
                "valid": False,
                "issues": ["No rows remain after dropping incomplete records."],
                "incomplete_row_count": 0,
                "dropped_row_count": dataset.get("dropped_row_count", 0),
            }
        else:
            validation = validate_dataset(
                dataset,
                column_mappings=request.column_mappings,
                validate_columns=request.validate_columns,
            )
            validation["dropped_row_count"] = dataset.get("dropped_row_count", 0)

    if validation["valid"]:
        dataset["output_columns"] = export_columns(
            request.column_mappings,
            request.validate_columns,
        )
        dataset["validated"] = True
        mark_validated(workspace, True)
    else:
        dataset["validated"] = False
        mark_validated(workspace, False)

    set_dataset(workspace, dataset)

    return {
        "dataset": _serialize_dataset(dataset),
        "validation": validation,
        "semanticFieldCols": mappings_to_semantic_field_cols(request.column_mappings),
    }


@router.get("/export")
async def export_cleaned_dataset(workspace: ProjectWorkspace = Depends(get_workspace)):
    """Download the cleaned dataset after validation."""
    dataset = get_dataset(workspace)
    if dataset is None:
        raise HTTPException(status_code=400, detail="Upload GIS data first.")
    if not dataset.get("validated"):
        raise HTTPException(status_code=400, detail="Validate the dataset before exporting.")

    source_format = dataset.get("source_format", "geojson")
    base_name = Path(str(dataset.get("filename", "buildings"))).stem

    if source_format == "geojson":
        if not dataset.get("features"):
            raise HTTPException(
                status_code=400,
                detail="Original GeoJSON geometry was not retained. Re-upload the GeoJSON file.",
            )
        content = json.dumps(build_cleaned_geojson(dataset), indent=2)
        filename = f"{base_name}-cleaned.geojson"
        media_type = "application/geo+json"
    else:
        content = build_cleaned_csv(dataset)
        filename = f"{base_name}-cleaned.csv"
        media_type = "text/csv"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export-enriched")
async def export_enriched_dataset(
    request: EnrichedExportRequest,
    save: bool = False,
    workspace: ProjectWorkspace = Depends(get_workspace),
):
    """Download GIS data with deterministic semantic fields applied.

    With ``?save=true`` the file is written into the project instead
    (``<gis dir>/buildings.geojson`` or ``.csv``), where norway-globi reads the stock.
    """
    dataset = get_dataset(workspace)
    if dataset is None:
        raise HTTPException(status_code=400, detail="Upload GIS data first.")
    if not dataset.get("validated"):
        raise HTTPException(status_code=400, detail="Validate GIS data before exporting enriched GIS.")

    fields = [field.model_dump(by_alias=False) for field in request.fields]
    core_columns = export_columns(
        dataset.get("column_mappings", {}),
        dataset.get("validated_columns", []),
    )
    enriched_rows = apply_semantic_fields_to_rows(dataset.get("rows", []), fields)

    source_format = dataset.get("source_format", "geojson")
    base_name = Path(str(dataset.get("filename", "buildings"))).stem

    if source_format == "geojson":
        if not dataset.get("features"):
            raise HTTPException(
                status_code=400,
                detail="Original GeoJSON geometry was not retained. Re-upload the GeoJSON file.",
            )

        features = []
        for index, feature in enumerate(dataset.get("features", [])):
            row = enriched_rows[index] if index < len(enriched_rows) else {}
            properties = build_enriched_properties(row, fields, core_columns)
            features.append(
                {
                    "type": "Feature",
                    "geometry": feature.get("geometry"),
                    "properties": properties,
                }
            )

        content = json.dumps({"type": "FeatureCollection", "features": features}, indent=2)
        filename = f"{base_name}-with-semantic-fields.geojson"
        media_type = "application/geo+json"
    else:
        semantic_columns = [field["name"] for field in fields if field.get("type") == "deterministic"]
        output_columns = sorted(set(core_columns + semantic_columns))
        buffer_rows = []
        for row in enriched_rows:
            buffer_rows.append({column: row.get(column, "") for column in output_columns})

        dataset_copy = {
            **dataset,
            "rows": buffer_rows,
            "output_columns": output_columns,
        }
        content = build_cleaned_csv(dataset_copy)
        filename = f"{base_name}-with-semantic-fields.csv"
        media_type = "text/csv"

    if save:
        target = workspace.path("gis_dir") / (
            "buildings.geojson" if source_format == "geojson" else "buildings.csv"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return {"path": target.relative_to(workspace.root).as_posix(), "bytes": len(content)}

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
