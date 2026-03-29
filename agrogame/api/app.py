"""FastAPI application factory."""

from __future__ import annotations


def create_app():  # type: ignore[no-untyped-def]
    """Create and configure the FastAPI application."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from agrogame.api.routes import router

    app = FastAPI(
        title="AgroGame API",
        description="REST API for the AgroGame farming simulation",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app
