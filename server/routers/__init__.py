"""API routers for SBEM UI."""

from .artifacts import router as artifacts_router
from .semantic_fields import router as semantic_fields_router
from .component_map import router as component_map_router
from .component_tree import router as component_tree_router
from .component_library import router as component_library_router
from .prior_trees import router as prior_trees_router
from .gis import router as gis_router
from .globi_files import router as globi_files_router
from .workspace import router as workspace_router
from .assist import router as assist_router
from .schedule_variability import router as schedule_variability_router
from .inspect import router as inspect_router
from .flat_model import router as flat_model_router
from .sampling import router as sampling_router
from .part_rules import router as part_rules_router
from .component_priors import router as component_priors_router

__all__ = [
    "artifacts_router",
    "semantic_fields_router",
    "component_map_router",
    "component_tree_router",
    "component_library_router",
    "prior_trees_router",
    "gis_router",
    "globi_files_router",
    "workspace_router",
    "assist_router",
    "schedule_variability_router",
    "inspect_router",
    "flat_model_router",
    "sampling_router",
    "part_rules_router",
    "component_priors_router",
]
