"""FastAPI routers package."""
from __future__ import annotations

from backend.routers.health import router as health_router
from backend.routers.skill_packs import router as skill_packs_router
from backend.routers.sessions import router as sessions_router
from backend.routers.reports import router as reports_router
from backend.routers.events import router as events_router
from backend.routers.docs import router as docs_router
from backend.routers.livekit import router as livekit_router
from backend.routers.recall import router as recall_router

__all__ = [
    "health_router",
    "skill_packs_router",
    "sessions_router",
    "reports_router",
    "events_router",
    "docs_router",
    "livekit_router",
    "recall_router",
]
