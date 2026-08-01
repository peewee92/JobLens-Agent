"""v1 API router aggregation.

Each feature area (health, jobs, profiles, ...) is its own sub-router
included here. The prefix /api/v1 is applied in app/main.py.
"""
from fastapi import APIRouter

from app.api.v1.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
