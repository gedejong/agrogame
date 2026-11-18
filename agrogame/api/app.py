"""FastAPI application factory."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def create_app():  # type: ignore[no-untyped-def]
    """Create and configure the FastAPI application."""
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse

    from agrogame.api.routes import router
    from agrogame.events import EventHandlerError

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

    @app.exception_handler(EventHandlerError)
    async def _simulation_error(
        request: Request, exc: EventHandlerError
    ) -> JSONResponse:
        """A simulation handler raised (#606): 500 naming handler and event.

        The traceback, with the handler's own exception chained, goes to the
        server log only. The session is not rolled back (docs/api.md).
        """
        logger.error(
            "%s %s failed: %s", request.method, request.url.path, exc, exc_info=exc
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": str(exc),
                "handler": exc.handler,
                "event_type": exc.event_type,
            },
        )

    return app
