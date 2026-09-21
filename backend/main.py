"""FastAPI application entrypoint.

Run locally:
    uvicorn backend.main:app --reload

The app also serves the static single-page frontend at ``/`` for a
zero-tooling demo — open ``http://localhost:8000`` after starting the server.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import FRONTEND_DIR
from .database import create_all
from .routers import elasticity as elasticity_router
from .routers import events as events_router
from .routers import okr as okr_router
from .routers import scenarios as scenario_router


@asynccontextmanager
async def _lifespan(_app: FastAPI):  # pragma: no cover - trivial
    create_all()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Ticketmaster Market & Pricing Strategy Workbench",
        version="0.1.0",
        description=(
            "A strategy manager's cockpit for prioritizing markets, pricing "
            "tickets, and simulating OKR impact across a tour."
        ),
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(events_router.router)
    app.include_router(elasticity_router.router)
    app.include_router(scenario_router.router)
    app.include_router(okr_router.router)

    if FRONTEND_DIR.exists():
        app.mount(
            "/static",
            StaticFiles(directory=FRONTEND_DIR),
            name="static",
        )

        @app.get("/", include_in_schema=False)
        def _root() -> FileResponse:
            return FileResponse(FRONTEND_DIR / "index.html")

    return app


app = create_app()
