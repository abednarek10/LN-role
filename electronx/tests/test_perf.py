"""Every GET endpoint answers in < 300 ms after warm-up on the seeded DB (CTO §7)."""
from __future__ import annotations

import time

import pytest

BUDGET_MS = 300
PATHS = [
    "/api/health",
    "/api/meta",
    "/api/ceo/weekly",
    "/api/ceo/weekly.md",
    "/api/pulse/hubs?iso=ERCOT&hours=168",
    "/api/pulse/hubs",
    "/api/pulse/triggers",
    "/api/pulse/triggers/ERCOT-HB_HOUSTON-20261002/accounts",
    "/api/pulse/history",
    "/api/activation/queue?limit=50",
    "/api/activation/queue?limit=50&segment=REP&iso=ERCOT",
    "/api/scoring/model",
    "/api/funnel",
    "/api/funnel?segment=UTILITY",
    "/api/funnel/friction/0.md",
    "/api/segments",
    "/api/liquidity?iso=ERCOT",
    "/api/liquidity?iso=PJM&tenor=HOURLY",
    "/api/team/scorecards",
    "/api/team/comp-plans",
    "/api/marketing/roi?months=6",
    "/api/accounts?limit=50",
    "/api/accounts?q=energy&limit=8",
    "/api/accounts/1",
    "/api/accounts/300",
]


@pytest.mark.parametrize("path", PATHS)
def test_get_under_budget(client, path):
    assert client.get(path).status_code == 200  # warm once
    t0 = time.perf_counter()
    r = client.get(path)
    ms = (time.perf_counter() - t0) * 1000
    assert r.status_code == 200
    assert ms < BUDGET_MS, f"{path} took {ms:.0f} ms"


def test_comp_sim_default_under_budget(client):
    client.post("/api/team/comp-sim", json={"plan_id": "activation_adv"})
    t0 = time.perf_counter()
    assert client.post("/api/team/comp-sim", json={"plan_id": "activation_adv"}).status_code == 200
    assert (time.perf_counter() - t0) * 1000 < BUDGET_MS
