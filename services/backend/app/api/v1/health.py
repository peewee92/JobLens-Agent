"""Health check endpoint.

No business value, but proves: Python env OK, FastAPI OK, Router OK,
App startup OK, Test Client OK.
"""
from fastapi import APIRouter, Depends, Response

from app.api.v1.schemas.system_readiness import SystemReadinessResponse
from app.repositories.sqlalchemy_system_readiness import SystemReadinessProbe
from app.db.session import engine

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "joblens-backend"}


def get_readiness_probe() -> SystemReadinessProbe:
    return SystemReadinessProbe(engine)


@router.get(
    "/readiness",
    response_model=SystemReadinessResponse,
    responses={503: {"model": SystemReadinessResponse, "description": "Database or migrations not ready"}},
)
def readiness(
    response: Response,
    probe: SystemReadinessProbe = Depends(get_readiness_probe),
) -> SystemReadinessResponse:
    result = probe.execute()
    response.status_code = 200 if result.ready else 503
    response.headers["Cache-Control"] = "no-store"
    return SystemReadinessResponse.from_result(result)
