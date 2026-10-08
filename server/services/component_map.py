"""Component map validation and tree helpers."""

from itertools import product
from typing import Any


def _collect_selectors(node: Any, path: str = "") -> list[dict[str, Any]]:
    selectors: list[dict[str, Any]] = []

    if isinstance(node, dict):
        if "selector" in node and isinstance(node["selector"], dict):
            selector = node["selector"]
            selectors.append(
                {
                    "path": path or "root",
                    "source_fields": selector.get("source_fields", []),
                    "suffix": selector.get("suffix"),
                }
            )

        for key, value in node.items():
            if key == "selector":
                continue
            child_path = f"{path}.{key}" if path else key
            selectors.extend(_collect_selectors(value, child_path))

    return selectors


def _get_node_at_path(component_map: dict[str, Any], path: str) -> dict[str, Any] | None:
    if not path:
        return component_map

    node: Any = component_map
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, dict) else None


def get_selector_at_path(component_map: dict[str, Any], path: str) -> dict[str, Any] | None:
    node = _get_node_at_path(component_map, path)
    if not node or "selector" not in node:
        return None
    selector = node["selector"]
    return selector if isinstance(selector, dict) else None


def set_selector_at_path(
    component_map: dict[str, Any],
    path: str,
    source_fields: list[str],
    suffix: str | None = None,
) -> dict[str, Any]:
    updated = _deep_copy(component_map)
    node = _get_node_at_path(updated, path)
    if node is None:
        raise ValueError(f"component path '{path}' not found")

    selector: dict[str, Any] = {"source_fields": source_fields}
    if suffix:
        selector["suffix"] = suffix
    node["selector"] = selector
    return updated


def remove_selector_at_path(component_map: dict[str, Any], path: str) -> dict[str, Any]:
    updated = _deep_copy(component_map)
    node = _get_node_at_path(updated, path)
    if node is None:
        return updated
    node.pop("selector", None)
    return updated


def remove_child_selectors(component_map: dict[str, Any], path: str) -> dict[str, Any]:
    updated = _deep_copy(component_map)
    node = _get_node_at_path(updated, path)
    if node is None:
        return updated

    for key, value in list(node.items()):
        if key == "selector":
            continue
        if isinstance(value, dict):
            _strip_selectors(value)

    return updated


def _strip_selectors(node: Any) -> None:
    if not isinstance(node, dict):
        return
    node.pop("selector", None)
    for key, value in list(node.items()):
        if isinstance(value, dict):
            _strip_selectors(value)


def _deep_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _deep_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_deep_copy(item) for item in value]
    return value


def validate_component_map(
    component_map: dict[str, Any], semantic_field_names: list[str]
) -> dict[str, Any]:
    errors: list[str] = []
    selectors = _collect_selectors(component_map)
    known_fields = set(semantic_field_names)

    for selector in selectors:
        if not selector["source_fields"]:
            errors.append(f"{selector['path']}: selector has no source fields.")
        for field_name in selector["source_fields"]:
            if field_name not in known_fields:
                errors.append(
                    f"{selector['path']}: semantic field '{field_name}' is not defined."
                )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "selectors": selectors,
    }


def preview_selector_names(
    source_fields: list[str],
    semantic_fields: list[dict[str, Any]],
    suffix: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    field_options = {
        field["name"]: field.get("options", [])
        for field in semantic_fields
        if field.get("name")
    }
    option_lists = [field_options.get(name, [name]) for name in source_fields]
    if not option_lists:
        return {"count": 0, "samples": []}

    names: list[str] = []
    for combo in product(*option_lists):
        parts = list(combo)
        if suffix:
            parts.append(suffix)
        names.append("_".join(str(part) for part in parts))

    unique_names = sorted(set(names))
    return {
        "count": len(unique_names),
        "samples": unique_names[:limit],
    }


def generate_component_names(
    component_map: dict[str, Any], semantic_fields: list[dict[str, Any]]
) -> list[str]:
    field_options = {
        field["name"]: field.get("options", [])
        for field in semantic_fields
        if field.get("options")
    }
    names: list[str] = []

    for selector in _collect_selectors(component_map):
        preview = preview_selector_names(
            selector["source_fields"],
            semantic_fields,
            selector.get("suffix"),
            limit=10_000,
        )
        names.extend(preview["samples"])

    return sorted(set(names))
