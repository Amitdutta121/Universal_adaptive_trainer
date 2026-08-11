"""HTTP routers."""

from app.web.routes.api import router as api_router
from app.web.routes.pages import router as pages_router

__all__ = ["api_router", "pages_router"]
