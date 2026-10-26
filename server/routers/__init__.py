"""API routers for SBEM UI."""

from .artifacts import router as artifacts_router
from .semantic_fields import router as semantic_fields_router
from .component_map import router as component_map_router
from .component_tree import router as component_tree_router
from .component_library import router as component_library_router
from .prior_trees import router as prior_trees_router
from .gis import router as gis_router
from .workspace import router as workspace_router
from .norway import router as runner_router
from .assist import router as assist_router
from .inspect import router as inspect_router

__all__ = [
    "artifacts_router",
    "semantic_fields_router",
    "component_map_router",
    "component_tree_router",
    "component_library_router",
    "prior_trees_router",
    "gis_router",
    "workspace_router",
    "runner_router",
    "assist_router",
    "inspect_router",
]
