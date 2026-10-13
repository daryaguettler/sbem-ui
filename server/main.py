"""SBEM UI FastAPI Backend."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import (
    artifacts_router,
    assist_router,
    component_library_router,
    component_map_router,
    component_tree_router,
    gis_router,
    prior_trees_router,
    runner_router,
    semantic_fields_router,
    workspace_router,
)
from services.component_tree import get_component_tree
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

app = FastAPI(
    title="SBEM UI API",
    description="Backend API for SBEM modeling interface",
    version="0.1.0",
)

# No project workspace is open until the frontend calls /api/workspace/create or /open.
app.state.workspace = None
# The component tree is static per epinterface version (not per-project), so it's
# computed once at startup rather than per-request.
app.state.component_tree = get_component_tree()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(semantic_fields_router)
app.include_router(artifacts_router)
app.include_router(component_map_router)
app.include_router(component_tree_router)
app.include_router(component_library_router)
app.include_router(prior_trees_router)
app.include_router(gis_router)
app.include_router(workspace_router)
app.include_router(runner_router)
app.include_router(assist_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "SBEM UI API", "version": "0.1.0"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
