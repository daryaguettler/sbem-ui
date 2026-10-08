"""GIS dataset storage, backed by the currently-open project workspace.

Preserves the previous in-memory-dict function signatures (get/set/mark/etc.) so
callers in routers/gis.py don't need to change -- only the storage backend does.
"""

from typing import Any

from services.workspace import ProjectWorkspace


def get_dataset(workspace: ProjectWorkspace) -> dict[str, Any] | None:
    return workspace.read_gis_dataset()


def set_dataset(workspace: ProjectWorkspace, dataset: dict[str, Any]) -> None:
    workspace.write_gis_dataset(dataset)


def clear_dataset(workspace: ProjectWorkspace) -> None:
    workspace.clear_gis_dataset()


def mark_validated(workspace: ProjectWorkspace, validated: bool = True) -> None:
    dataset = get_dataset(workspace)
    if dataset is not None:
        dataset["validated"] = validated
        set_dataset(workspace, dataset)


def set_column_mappings(workspace: ProjectWorkspace, column_mappings: dict[str, str | None]) -> None:
    dataset = get_dataset(workspace)
    if dataset is not None:
        dataset["column_mappings"] = column_mappings
        set_dataset(workspace, dataset)


def get_column_mappings(workspace: ProjectWorkspace) -> dict[str, str | None]:
    dataset = get_dataset(workspace)
    if dataset is None:
        return {}
    return dataset.get("column_mappings", {})


def set_validated_columns(workspace: ProjectWorkspace, validated_columns: list[str]) -> None:
    dataset = get_dataset(workspace)
    if dataset is not None:
        dataset["validated_columns"] = validated_columns
        set_dataset(workspace, dataset)
