from __future__ import annotations

from fastapi import APIRouter

from tbot_sheduler.api.health import router as health_router
from tbot_sheduler.api.webapp import router as webapp_router
from tbot_sheduler.api.booking import router as booking_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(webapp_router)
api_router.include_router(booking_router)
