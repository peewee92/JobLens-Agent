"""Compose user workspace routers without admin, model credentials, or public demo endpoints."""
from __future__ import annotations

from typing import Mapping

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse, Response

from app.api.error_handlers import register_exception_handlers
from app.api.v1 import (
    application_workspaces, career_agent, career_context, health, job_imports,
    job_preparation, job_requirements, jobs, match_batch, match_blockers,
    match_improvement, match_ranking, match_review, profile_proposals,
    recommendation_coverage, requirement_batch, semantic_calls,
    target_cohort_gaps, user_feedback, workbench,
)
from app.cloud.boundary import PrivateWorkspaceBoundary
from app.db.context import DatabaseContext

# A distinct composition root means new maintenance routers never become public by default.
WORKSPACE_ROUTERS = (
    health, workbench, career_context, jobs, job_imports, job_requirements, job_preparation,
    match_batch, match_blockers, match_improvement, match_ranking, match_review,
    recommendation_coverage, requirement_batch, profile_proposals, semantic_calls,
    career_agent, application_workspaces, target_cohort_gaps, user_feedback,
)


def create_private_app(workspaces: Mapping[str, DatabaseContext], secret: bytes) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    register_exception_handlers(app)
    for module in WORKSPACE_ROUTERS:
        app.include_router(module.router, prefix="/api/v1")

    @app.get("/api/v1/workspace-access", status_code=204)
    async def workspace_access():
        # The boundary has already selected an invited account, without a database query.
        return Response(status_code=204)

    @app.exception_handler(RequestValidationError)
    async def private_validation(_request, _error):
        return JSONResponse({"error": {"code": "request_validation_error",
                                      "message": "资料格式不正确，请返回页面核对。"}}, status_code=422)

    app.add_middleware(PrivateWorkspaceBoundary, workspaces=workspaces, secret=secret)
    return app
