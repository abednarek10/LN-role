"""Ignition API — FastAPI app (``uvicorn ignition.main:app``).

Lifespan: create tables, seed if empty, warm caches (frames → model → scores →
triggers → account context → default payloads). The frontend is served from
``/static`` with ``index.html`` at ``/``.
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from contextlib import asynccontextmanager

import numpy as np
import pandas as pd
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import definitions as D
from .config import DATABASE_URL, FRONTEND_DIR
from .database import SessionLocal, create_all, engine
from .routers import (accounts, activation, ceo, funnel, liquidity, marketing, meta, outreach, pulse, scoring,
                      segments, team)
from .schemas import Health
from .services import cache

log = logging.getLogger("ignition")


def _clean(o):
    """JSON-safe: NaN/inf -> None, numpy/pandas scalars -> Python."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.generic):
        return _clean(o.item())
    if o is pd.NaT:
        return None
    return o


class SafeJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(_clean(content), ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.perf_counter()
    create_all(engine)
    from .seed import seed_if_empty

    if seed_if_empty(engine):
        log.info("seeded empty database")
    with SessionLocal() as s:
        cache.warm(s)
    if os.environ.get("IGNITION_SKIP_PRECOMPUTE") != "1":
        cache.precompute(cache.STATE)
    cache.STATE.timings["startup_s"] = round(time.perf_counter() - t0, 2)
    log.info("Ignition warm in %.1fs", time.perf_counter() - t0)
    yield


app = FastAPI(
    title="Ignition — ElectronX Activation & Revenue OS",
    version="1.0.0",
    description="Synthetic data — illustrative. All accounts, prices and volumes are invented.",
    lifespan=lifespan,
    default_response_class=SafeJSONResponse,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def timing_header(request: Request, call_next):
    t0 = time.perf_counter()
    resp = await call_next(request)
    resp.headers["X-Response-Time-ms"] = f"{(time.perf_counter() - t0) * 1000:.1f}"
    resp.headers["X-Synthetic-Data"] = "illustrative"
    return resp


@app.get("/api/health", response_model=Health, tags=["meta"])
def health():
    return {"status": "ok", "as_of": D.AS_OF_DATE.isoformat(), "db": DATABASE_URL.split("://")[0],
            "warmed": cache.STATE.frames is not None, "version": cache.STATE.version,
            "claude_enabled": bool(os.environ.get("ANTHROPIC_API_KEY"))}


for r in (meta, ceo, pulse, activation, scoring, funnel, segments, liquidity, team, marketing, accounts, outreach):
    app.include_router(r.router, prefix="/api")


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):  # pragma: no cover - safety net
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": f"internal error: {type(exc).__name__}"})


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return FileResponse(FRONTEND_DIR / "favicon.svg", media_type="image/svg+xml")
