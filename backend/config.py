"""Runtime configuration for the workbench backend.

Local-first defaults: SQLite file in ``data/workbench.db``. Set ``WORKBENCH_DB_URL``
to point at Postgres (``postgresql+psycopg://user:pw@host/db``) without touching
any application code — SQLAlchemy handles the dialect switch.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = ROOT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_SQLITE_PATH: Path = DATA_DIR / "workbench.db"
DATABASE_URL: str = os.environ.get(
    "WORKBENCH_DB_URL",
    f"sqlite:///{DEFAULT_SQLITE_PATH}",
)

# Baseline OKR segment used for the primary progress view.
DEFAULT_OKR_SEGMENT: str = os.environ.get("WORKBENCH_OKR_SEGMENT", "Concerts_NA_2026")

# Random seed for the synthetic data generator — keep it fixed so reviewers see
# the same numbers as the README screenshots.
SEED: int = int(os.environ.get("WORKBENCH_SEED", "42"))

# Frontend is served from ``frontend/`` when the backend is launched with
# ``uvicorn backend.main:app``. Override for a mounted CDN.
FRONTEND_DIR: Path = Path(os.environ.get("WORKBENCH_FRONTEND_DIR", ROOT_DIR / "frontend"))
