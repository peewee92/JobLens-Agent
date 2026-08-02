"""Composition Root.

This module only assembles the application: create the FastAPI app and
register routers / lifecycle. Business logic does NOT belong here.
"""
from fastapi import FastAPI

from app.api.error_handlers import register_exception_handlers
from app.api.v1.router import api_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="JobLens Backend",
        version="0.1.0",
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
