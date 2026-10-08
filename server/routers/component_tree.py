"""Component tree API router: serves the real epinterface component graph."""

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/component-tree", tags=["component-tree"])


@router.get("/")
async def get_component_tree(request: Request):
    """Return the cached component tree computed once at app startup."""
    return request.app.state.component_tree
