"""Health check endpoint.

No business value, but proves: Python env OK, FastAPI OK, Router OK,
App startup OK, Test Client OK.
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "joblens-backend"}
