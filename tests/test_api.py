"""End-to-end tests via FastAPI's TestClient over a seeded temp SQLite DB."""
from __future__ import annotations


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_events_overview_has_expected_shape(client):
    r = client.get("/api/events/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["event_count"] >= 10  # seed builds ~15 events
    ev = body["events"][0]
    assert 0 <= ev["market_opportunity_score"] <= 100
    assert ev["gross_revenue"] >= 0
    assert 0 <= ev["sell_through"] <= 1


def test_overview_filters_by_city(client):
    r = client.get("/api/events/overview?city=chicago")
    assert r.status_code == 200
    body = r.json()
    for e in body["events"]:
        assert "chicago" in e["city"].lower()


def test_elasticity_endpoint_returns_fit(client):
    overview = client.get("/api/events/overview").json()
    event_id = overview["events"][0]["event_id"]
    r = client.get(f"/api/events/{event_id}/elasticity")
    assert r.status_code == 200
    body = r.json()
    assert body["sample_size"] > 30
    assert -3.0 < body["beta_1"] < 0.0  # sane elastic-goods slope
    assert body["r_squared"] >= 0
    assert len(body["price_grid_predictions"]) >= 20


def test_scenario_zero_move_leaves_revenue_flat(client):
    overview = client.get("/api/events/overview").json()
    ids = [e["event_id"] for e in overview["events"][:3]]
    r = client.post(
        "/api/scenario/simulate",
        json={
            "event_ids": ids,
            "price_adjustment_type": "percent",
            "price_adjustment_value": 0.0,
            "add_extra_show": False,
        },
    )
    assert r.status_code == 200
    body = r.json()
    # Design contract: 0% move and no extra shows ⇒ scenario ≈ baseline.
    assert abs(body["delta_revenue"]) < max(1000.0, body["baseline_revenue"] * 0.02)
    assert body["extra_show_events_added"] == 0


def test_scenario_price_hike_moves_revenue_and_okr(client):
    overview = client.get("/api/events/overview").json()
    ids = [e["event_id"] for e in overview["events"][:5]]
    r = client.post(
        "/api/scenario/simulate",
        json={
            "event_ids": ids,
            "price_adjustment_type": "percent",
            "price_adjustment_value": 8.0,
            "add_extra_show": False,
        },
    )
    body = r.json()
    assert body["okr_segment"] == "Concerts_NA_2026"
    assert body["okr_progress_delta_pts"] != 0.0
    # Any nonzero price move should register some revenue delta.
    assert body["delta_revenue"] != 0.0


def test_scenario_extra_show_lifts_revenue(client):
    overview = client.get("/api/events/overview").json()
    ids = [e["event_id"] for e in overview["events"][:3]]
    r = client.post(
        "/api/scenario/simulate",
        json={
            "event_ids": ids,
            "price_adjustment_type": "percent",
            "price_adjustment_value": 0.0,
            "add_extra_show": True,
        },
    )
    body = r.json()
    assert body["extra_show_events_added"] >= 1
    assert body["scenario_revenue"] > body["baseline_revenue"]


def test_okr_summary(client):
    r = client.get("/api/okr/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["default_segment"] == "Concerts_NA_2026"
    segments = {s["segment"]: s for s in body["segments"]}
    na = segments["Concerts_NA_2026"]
    assert na["annual_revenue_target"] > 0
    assert 0 <= na["revenue_progress_pct"] <= 5  # generous upper bound
    assert na["events_counted"] >= 10
