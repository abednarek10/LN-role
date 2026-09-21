"""Shared pytest fixtures — build a temp SQLite database seeded fresh per session.

We override the ``WORKBENCH_DB_URL`` env var *before* importing anything from
``backend``, so both the ORM engine and the FastAPI app pick up the temp path.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def tmp_db_path() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="workbench-test-")) / "test.db"
    os.environ["WORKBENCH_DB_URL"] = f"sqlite:///{tmp}"
    return tmp


@pytest.fixture(scope="session")
def seeded_db(tmp_db_path: Path):
    # Import lazily so the env var is honoured.
    from backend.database import SessionLocal, create_all
    from backend.seed import seed

    create_all()
    db = SessionLocal()
    try:
        seed(db)
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(seeded_db):
    from fastapi.testclient import TestClient
    from backend.main import app

    return TestClient(app)
