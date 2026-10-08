"""Shared backend helpers."""

from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"


def resolve_template_path(category: str, template_name: str) -> Path:
    """Resolve a template path safely within a category directory."""
    category_dir = (TEMPLATES_DIR / category).resolve()
    template_path = (category_dir / template_name).resolve()

    if category_dir not in template_path.parents and template_path != category_dir:
        raise HTTPException(status_code=400, detail="Invalid template path")
    if not template_path.exists() or template_path.suffix not in {".yml", ".yaml"}:
        raise HTTPException(status_code=404, detail="Template not found")

    return template_path


def load_yaml_template(category: str, template_name: str) -> dict[str, Any]:
    """Load a YAML template from disk."""
    template_path = resolve_template_path(category, template_name)
    with template_path.open() as handle:
        return yaml.safe_load(handle) or {}


def list_yaml_templates(category: str) -> list[dict[str, str]]:
    """List YAML templates for a category."""
    category_dir = TEMPLATES_DIR / category
    templates: list[dict[str, str]] = []

    if not category_dir.exists():
        return templates

    for template_file in sorted(category_dir.glob("*.yml")):
        try:
            with template_file.open() as handle:
                template_data = yaml.safe_load(handle) or {}
            templates.append(
                {
                    "name": str(template_data.get("Name", template_file.stem)),
                    "filename": template_file.name,
                    "description": str(template_data.get("description", "")),
                }
            )
        except Exception as exc:
            print(f"Error loading template {template_file}: {exc}")

    return templates
