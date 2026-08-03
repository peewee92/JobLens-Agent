"""v1 API router aggregation.

Each feature area (health, jobs, profiles, ...) is its own sub-router
included here. The prefix /api/v1 is applied in app/main.py.
"""
from fastapi import APIRouter

from app.api.v1.career_context import router as career_context_router
from app.api.v1.health import router as health_router
from app.api.v1.job_imports import router as job_imports_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.profile_evals import router as profile_evals_router
from app.api.v1.profile_proposals import router as profile_proposals_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(career_context_router, tags=["career-context"])
api_router.include_router(job_imports_router, tags=["job-imports"])
api_router.include_router(jobs_router, tags=["jobs"])
api_router.include_router(profile_proposals_router, tags=["profile-proposals"])
api_router.include_router(profile_evals_router, tags=["profile-evals"])
