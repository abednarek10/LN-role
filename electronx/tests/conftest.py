"""Shared fixtures for the Ignition test-suite.

The DB URL is pointed at a throw-away SQLite file *before* any ``ignition``
module is imported, then seeded once per session. Fixtures for other agents:

* ``engine``  — seeded SQLAlchemy engine (session scope)
* ``session`` — a fresh ORM session per test (rolled back + closed)
* ``frames``  — ``repo.Frames`` with every table as a DataFrame (session scope)
* ``seeded_tables`` — the in-memory tables the seed wrote (session scope)
* ``model_bundle`` — trained propensity model (session scope)
* ``client``  — FastAPI ``TestClient`` for ``ignition.main.app`` (skips if absent)
"""
from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

_TMP_DIR = tempfile.mkdtemp(prefix="ignition-test-")
os.environ["IGNITION_DB_URL"] = os.environ.get("IGNITION_TEST_DB_URL") or f"sqlite:///{_TMP_DIR}/ignition_test.db"
atexit.register(shutil.rmtree, _TMP_DIR, ignore_errors=True)

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def seeded_tables():
    from ignition import seed
    from ignition.database import engine as eng

    return seed.seed(eng)


@pytest.fixture(scope="session")
def engine(seeded_tables):
    from ignition.database import engine as eng

    yield eng


@pytest.fixture()
def session(engine):
    from ignition.database import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture(scope="session")
def frames(engine):
    from ignition import repo
    from ignition.database import SessionLocal

    with SessionLocal() as s:
        return repo.load_all(s, refresh=True)


@pytest.fixture(scope="session")
def model_bundle(frames):
    from ignition.services.propensity import train_model

    return train_model(frames)


@pytest.fixture(scope="session")
def client(engine):
    try:
        from ignition.main import app
    except ModuleNotFoundError as exc:
        if exc.name in ("ignition.main",):
            pytest.skip("ignition.main not implemented yet")
        raise
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c
