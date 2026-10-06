"""Runtime configuration for Ignition.

Local-first defaults: SQLite file at ``electronx/data/ignition.db``. Set
``IGNITION_DB_URL`` to point at Postgres (``postgresql+psycopg://user:pw@host/db``)
without touching application code; all datetimes are naive UTC and all column
types are portable.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR: Path = Path(__file__).resolve().parent.parent  # .../electronx
PACKAGE_DIR: Path = Path(__file__).resolve().parent  # .../electronx/ignition
CONTENT_DIR: Path = PACKAGE_DIR / "content"
DATA_DIR: Path = ROOT_DIR / "data"

DEFAULT_SQLITE_PATH: Path = DATA_DIR / "ignition.db"


def _default_db_url() -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_SQLITE_PATH}"


DATABASE_URL: str = os.environ.get("IGNITION_DB_URL") or _default_db_url()

# Random seed for the synthetic data generator — fixed so every reviewer sees
# the same numbers as the docs and screenshots.
SEED: int = int(os.environ.get("IGNITION_SEED", "42"))

# Optional: enables the Claude outreach engine; absent -> template fallback.
ANTHROPIC_API_KEY: str | None = os.environ.get("ANTHROPIC_API_KEY") or None

# Frontend is served from ``electronx/frontend`` by default.
FRONTEND_DIR: Path = Path(os.environ.get("FRONTEND_DIR", str(ROOT_DIR / "frontend")))
