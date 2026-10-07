"""Volatility trigger engine: seeded event detection, rule unit tests, exposure."""
from __future__ import annotations

from datetime import datetime, timedelta

import json
import re

import numpy as np
import pandas as pd
import pytest

from ignition import definitions as D
from ignition.config import CONTENT_DIR
from ignition.services import volatility as V


def _series(hub: str, values, start=datetime(2026, 8, 1)) -> pd.DataFrame:
    ts = pd.date_range(start, periods=len(values), freq="h")
    return pd.DataFrame({"hub": hub, "ts": ts, "iso": D.HUB_ISO[hub], "lmp": np.asarray(values, dtype=float)})


def _base(n=24 * 40, level=30.0, seed=0):
    rng = np.random.default_rng(seed)
    hours = np.arange(n) % 24
    return level * (1 + 0.3 * np.sin(hours / 24 * 2 * np.pi)) * np.exp(rng.normal(0, 0.05, n))


@pytest.fixture(scope="module")
def triggers(frames):
    return V.detect_triggers(frames.market_prices, D.AS_OF, frames.price_forecasts)


# ---------------------------------------------------------------------------
# Seeded demo event
# ---------------------------------------------------------------------------
def test_seeded_event_detected_with_houston_highest(triggers):
    assert triggers, "expected live triggers at AS_OF"
    top = triggers[0]
    assert top["hub"] == "HB_HOUSTON"
    assert top["trigger_id"] == "ERCOT-HB_HOUSTON-20261002"
    assert top["regime"] == "scarcity"
    assert top["peak_lmp"] == 4800.0
    assert 6 <= top["spike_hours"] <= 9
    assert top["start_ts"] == datetime(2026, 10, 2, 15)
    assert top["forward_risk"] is True and top["forecast_peak_lmp"] >= V.ISO_FLOOR["ERCOT"]
    by_hub = {t["hub"]: t for t in triggers}
    assert "HB_NORTH" in by_hub and by_hub["HB_NORTH"]["severity"] < top["severity"]
    assert all(t["severity"] <= top["severity"] for t in triggers)
    severities = [t["severity"] for t in triggers]
    assert severities == sorted(severities, reverse=True)


def test_mild_caiso_negative_trigger(triggers):
    caiso = [t for t in triggers if t["iso"] == "CAISO"]
    assert caiso and all(t["regime"] == "negative_price" for t in caiso)
    sp = next(t for t in caiso if t["hub"] == "SP15")
    assert sp["neg_hours"] >= V.NEG_MIN_HOURS and sp["peak_lmp"] < 0
    assert sp["severity"] < 70  # mild relative to the ERCOT scarcity event


def test_no_spurious_triggers(triggers):
    hubs = {t["hub"] for t in triggers}
    assert hubs <= {"HB_HOUSTON", "HB_NORTH", "SP15", "NP15"}
    assert {"PJM_WESTERN_HUB", "MISO_INDIANA_HUB", "HB_WEST"}.isdisjoint(hubs)


def test_peak_ratio_and_event_id(triggers):
    by_hub = {t["hub"]: t for t in triggers}
    hou, nor = by_hub["HB_HOUSTON"], by_hub["HB_NORTH"]
    assert hou["event_id"] == nor["event_id"] == "ERCOT-20261002"
    assert hou["peak_ratio_basis"] == "p99_30d"
    assert hou["peak_ratio"] == pytest.approx(hou["peak_lmp"] / hou["p99_30d"], rel=1e-3)
    assert hou["peak_ratio"] > nor["peak_ratio"] > 10  # Houston reads as the strongest
    assert max(t["peak_ratio"] for t in triggers if t["peak_ratio_basis"] == "p99_30d") == hou["peak_ratio"]
    sp = by_hub["SP15"]
    assert sp["event_id"] == "CAISO-20261003"
    assert sp["peak_ratio_basis"] in ("neg_hours", "p1_30d")
    if sp["peak_ratio_basis"] == "neg_hours":
        assert sp["peak_ratio"] == sp["neg_hours"] == 14


def test_trigger_payload_shape(triggers):
    keys = {"trigger_id", "event_id", "hub", "iso", "regime", "severity", "spike_hours", "neg_hours", "vol_z",
            "peak_lmp", "peak_ratio", "peak_ratio_basis", "p99_30d", "peak_ts", "start_ts", "end_ts", "forward_risk"}
    for t in triggers:
        assert keys <= set(t)
        assert 0 <= t["severity"] <= 100
        assert t["start_ts"] <= t["end_ts"] < D.AS_OF


def test_no_look_ahead(frames):
    before = V.detect_triggers(frames.market_prices, datetime(2026, 10, 2, 14), frames.price_forecasts)
    assert not any(t["trigger_id"] == "ERCOT-HB_HOUSTON-20261002" for t in before)
    p = frames.market_prices
    trimmed = p[p["ts"] < pd.Timestamp(D.AS_OF)]
    assert V.detect_triggers(trimmed, D.AS_OF) == V.detect_triggers(p, D.AS_OF)


def test_hub_stats(frames):
    st = V.hub_stats(frames.market_prices, "HB_HOUSTON", D.AS_OF)
    assert set(st) >= {"last", "avg_30d", "p99_30d", "max_72h", "min_72h", "spike_hours_72h", "vol_z"}
    assert st["max_72h"] == 4800.0 and st["spike_hours_72h"] >= 6
    calm = V.hub_stats(frames.market_prices, "PJM_WESTERN_HUB", D.AS_OF)
    assert calm["spike_hours_72h"] == 0 and calm["max_72h"] < V.ISO_FLOOR["PJM"]


# ---------------------------------------------------------------------------
# Rule unit tests on hand-built series
# ---------------------------------------------------------------------------
def test_flat_series_no_trigger():
    df = _series("HB_NORTH", [30.0] * (24 * 40))
    as_of = df["ts"].max() + timedelta(hours=1)
    assert V.detect_triggers(df, as_of) == []
    st = V.hub_stats(df, "HB_NORTH", as_of)
    assert st["vol_z"] == 0.0 and st["spike_hours_72h"] == 0
    assert V.detect_historical_events(df) == []


def test_noisy_calm_series_no_trigger():
    df = _series("PJM_WESTERN_HUB", _base())
    assert V.detect_triggers(df, df["ts"].max() + timedelta(hours=1)) == []


def test_three_spike_hours_fire_scarcity():
    vals = _base()
    vals[-10:-7] = [1500, 2600, 1800]
    df = _series("HB_HOUSTON", vals)
    trig = V.detect_triggers(df, df["ts"].max() + timedelta(hours=1))
    assert len(trig) == 1
    t = trig[0]
    assert t["regime"] == "scarcity" and t["spike_hours"] == 3 and t["peak_lmp"] == 2600
    assert t["trigger_id"].startswith("ERCOT-HB_HOUSTON-")


def test_two_spike_hours_are_not_scarcity():
    """S < 3 never fires the spike rule; a vol-only trigger is labelled elevated_vol."""
    vals = _base()
    vals[-10:-8] = [1500, 2600]
    df = _series("HB_HOUSTON", vals)
    trig = V.detect_triggers(df, df["ts"].max() + timedelta(hours=1))
    assert all(t["regime"] == "elevated_vol" and t["spike_hours"] == 2 for t in trig)
    assert all(t["vol_z"] >= V.VOL_Z_FIRE for t in trig)


def test_spike_below_iso_floor_does_not_fire_in_ercot():
    vals = _base()
    vals[-10:-6] = [600, 700, 800, 650]  # big but below the $1,000 ERCOT floor
    df = _series("HB_NORTH", vals)
    trig = V.detect_triggers(df, df["ts"].max() + timedelta(hours=1))
    assert all(t["regime"] != "scarcity" for t in trig)


def test_winter_regime():
    vals = _base(level=45)
    vals[-20:-16] = [320, 480, 610, 400]
    df = _series("PJM_WESTERN_HUB", vals, start=datetime(2026, 1, 2))
    t = V.detect_triggers(df, df["ts"].max() + timedelta(hours=1))[0]
    assert t["regime"] == "winter_peak"


def test_caiso_negative_hours_fire():
    vals = _base(level=40)
    idx = np.arange(len(vals) - 60, len(vals) - 46)
    vals[idx] = -8.0
    df = _series("SP15", vals)
    t = V.detect_triggers(df, df["ts"].max() + timedelta(hours=1))
    assert t and t[0]["regime"] == "negative_price" and t[0]["neg_hours"] == 14 and t[0]["peak_lmp"] == -8.0
    # negatives outside CAISO do not count
    df2 = _series("PJM_WESTERN_HUB", vals)
    assert all(x["regime"] != "negative_price" for x in V.detect_triggers(df2, df2["ts"].max() + timedelta(hours=1)))


def test_forward_only_trigger():
    df = _series("HB_WEST", _base())
    as_of = df["ts"].max() + timedelta(hours=1)
    fc = pd.DataFrame({"hub": ["HB_WEST"] * 2, "iso": ["ERCOT"] * 2,
                       "date": [as_of.normalize(), as_of.normalize() + timedelta(days=2)],
                       "forecast_peak_lmp": [120.0, 1500.0], "forecast_avg_lmp": [40.0, 300.0],
                       "issued_at": [as_of] * 2})
    t = V.detect_triggers(df, as_of, fc)
    assert len(t) == 1 and t[0]["forward_risk"] and t[0]["spike_hours"] == 0
    fc_far = fc.assign(date=fc["date"] + timedelta(days=10))
    assert V.detect_triggers(df, as_of, fc_far) == []


def test_severity_soft_cap_orders_saturated_events():
    a = _base()
    b = _base()
    a[-12:-3] = 4800.0
    b[-12:-5] = 3500.0
    ta = V.detect_triggers(_series("HB_HOUSTON", a), _series("HB_HOUSTON", a)["ts"].max() + timedelta(hours=1))[0]
    tb = V.detect_triggers(_series("HB_NORTH", b), _series("HB_NORTH", b)["ts"].max() + timedelta(hours=1))[0]
    assert 90 < ta["severity"] <= 100 and tb["severity"] < ta["severity"]


# ---------------------------------------------------------------------------
# Historical events & exposure
# ---------------------------------------------------------------------------
def test_historical_events_match_table(frames):
    ev = V.detect_historical_events(frames.market_prices)
    ids = [e["trigger_id"] for e in ev]
    assert ids == list(frames.volatility_events["trigger_id"])
    assert "ERCOT-HB_HOUSTON-20260702" in ids
    live = {t["trigger_id"] for t in V.detect_triggers(frames.market_prices, D.AS_OF, frames.price_forecasts)}
    assert {"ERCOT-HB_HOUSTON-20261002", "ERCOT-HB_NORTH-20261002"} <= live & set(ids)


@pytest.mark.parametrize(
    "segment,regime,expected",
    [
        ("REP", "scarcity", "hurt"),
        ("CI_LOAD", "scarcity", "hurt"),
        ("DATACENTER", "winter_peak", "hurt"),
        ("UTILITY", "scarcity", "hurt"),
        ("STORAGE", "scarcity", "opportunity"),
        ("PROP", "scarcity", "opportunity"),
        ("FUND", "elevated_vol", "opportunity"),
        ("IPP", "scarcity", "opportunity"),
        ("IPP", "negative_price", "hurt"),
        ("STORAGE", "negative_price", "opportunity"),
    ],
)
def test_exposure_direction(segment, regime, expected):
    assert V.exposure_direction(segment, regime) == expected


def test_exposure_line_plain_english():
    for seg in D.SEGMENT_CODES:
        for regime in D.REGIMES:
            line = V.exposure_line(seg, "HB_HOUSTON", regime)
            assert "HB_HOUSTON" in line and "$" not in line and len(line) < 220
            assert "{" not in line
    assert "Liquidity partner" in V.exposure_line("PROP", "SP15", "negative_price", is_liquidity_partner=True)


def _all_exposure_lines() -> set[str]:
    lines = set()
    for seg in D.SEGMENT_CODES:
        for regime in D.REGIMES:
            for hub in D.HUBS:
                lines.add(V.exposure_line(seg, hub, regime))
                lines.add(V.exposure_line(seg, hub, regime, is_liquidity_partner=True))
    lines.add(V._DEFAULT_LINE.format(hub="HB_NORTH", iso="ERCOT", regime_lc="scarcity pricing"))
    return lines


def test_exposure_lines_pass_compliance_phrases():
    """Neutral exposure descriptions: no banned/caution phrase, no promissory verbs."""
    cfg = json.loads((CONTENT_DIR / "compliance_rules.json").read_text())
    phrases = cfg["banned_phrases"] + cfg["caution_phrases"] + ["lock in", "locked in", "locking", "protect",
                                                                  "secure", "guarantee", "should", "recommend"]
    allow = sorted(cfg.get("allowlist_phrases", []), key=len, reverse=True)
    hits = []
    for line in _all_exposure_lines():
        text = " ".join(line.lower().replace("’", "'").split())
        for a in allow:
            text = text.replace(a.lower(), " ")
        for ph in phrases:
            if re.search(r"(?<![\w-])" + re.escape(ph.lower()) + r"(?![\w-])", text):
                hits.append((ph, line))
    assert not hits, hits


def test_exposure_helpers():
    assert V.is_exposed("ERCOT,PJM", "PJM") and not V.is_exposed("ERCOT", "CAISO")
    big = V.exposure_score("REP", 2000, 90)
    small = V.exposure_score("REP", 5, 90)
    assert big > small > 0
    # v1.1 X6: own hub = full score, ISO-only exposure × 0.6, capped at 100
    full = V.exposure_score("STORAGE", 100, 80, hub_match=True)
    assert V.exposure_score("STORAGE", 100, 80, hub_match=False) == pytest.approx(round(full * 0.6, 1), abs=0.11)
    assert V.exposure_score("REP", 50_000, 100) == 100.0


def test_exposure_table_hub_specific(frames, triggers):
    hou = next(t for t in triggers if t["hub"] == "HB_HOUSTON")
    tab = V.exposure_table(frames.accounts, hou)
    acc = frames.accounts.set_index("id")
    assert len(tab) and tab["account_id"].is_unique
    assert all("ERCOT" in D.parse_isos(acc.at[a, "exposure_isos"]) for a in tab["account_id"])
    not_exposed = acc[~acc["exposure_isos"].str.contains("ERCOT")].index
    assert not set(tab["account_id"]) & set(not_exposed)
    assert (tab["hub_match"] == (tab["account_id"].map(acc["hub"]) == "HB_HOUSTON")).all()
    assert (tab["hub"] == tab["account_id"].map(acc["hub"])).all()  # rows show the account's own hub
    assert tab["exposure_score"].between(0, 100).all()


def test_event_exposure_counts_distinct_accounts(frames, triggers):
    ercot = [t for t in triggers if t["iso"] == "ERCOT"]
    ev = V.event_exposure(frames.accounts, ercot)
    assert set(ev["event_id"]) == {"ERCOT-20261002"}
    assert ev["account_id"].is_unique
    per_hub = sum(len(V.exposure_table(frames.accounts, t)) for t in ercot)
    assert len(ev) < per_hub  # the per-hub lists double count
    n_ercot = frames.accounts["exposure_isos"].str.contains("ERCOT").sum()
    assert len(ev) == n_ercot


def test_trigger_cohort_lift_from_frames(frames):
    lift = V.trigger_cohort_lift(frames.accounts, frames.activities, frames.trades, frames.volatility_events)
    assert lift["triggered"]["activated_14d_rate"] > lift["untriggered"]["activated_14d_rate"]
    assert 1.8 <= lift["lift_x"] <= 3.0
