"""In-process application state: computed once at startup, refreshed after writes.

* ``frames``  — every table as a DataFrame (``repo.load_all``, itself cached).
* ``bundle``  — trained propensity model (≈2 s; trained once per process).
* ``scores``  — ``score_accounts`` at AS_OF for every non-LP account.
* ``triggers``— live volatility triggers at AS_OF (prices + forecasts).
* ``health``  — ``features.account_health`` at AS_OF.
* ``accounts``— the per-account context table (``common.build_account_table``).
* ``memo``    — derived response payloads keyed by endpoint + params.

Writes (outreach queue → ``activities``) call :func:`refresh`, which reloads the
touched tables and rebuilds everything derived from them. Model and scores are
kept: features read ``ts < AS_OF`` and a queued touch is stamped ``AS_OF``, so
scores are unchanged by construction; urgency/suppression read ``ts <= AS_OF``.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from .. import definitions as D
from .. import repo
from . import features, propensity, volatility
from .common import build_account_table

_LOCK = threading.RLock()


@dataclass
class AppState:
    frames: Any = None
    bundle: Any = None
    scores: pd.DataFrame | None = None
    triggers: list[dict] = field(default_factory=list)
    health: pd.DataFrame | None = None
    accounts: pd.DataFrame | None = None
    memo: dict = field(default_factory=dict)
    version: int = 0
    warmed_at: float = 0.0
    timings: dict = field(default_factory=dict)

    def cached(self, key, fn: Callable[[], Any]):
        """Memoize a derived payload until the next refresh."""
        hit = self.memo.get(key)
        if hit is not None:
            return hit
        with _LOCK:
            hit = self.memo.get(key)
            if hit is None:
                hit = fn()
                self.memo[key] = hit
            return hit


STATE = AppState()


def _derive(state: AppState) -> None:
    """Rebuild everything that depends on frames (not the model)."""
    f = state.frames
    t0 = time.perf_counter()
    state.triggers = volatility.detect_triggers(f.market_prices, D.AS_OF, f.price_forecasts)
    state.health = features.account_health(f, D.AS_OF)
    state.accounts = build_account_table(f, state.scores, state.health, D.AS_OF)
    state.memo = {}
    state.version += 1
    state.timings["derive_s"] = round(time.perf_counter() - t0, 3)


def warm(session, retrain: bool = False) -> AppState:
    """Load frames, train (once) and score, detect triggers, build context."""
    with _LOCK:
        t0 = time.perf_counter()
        STATE.frames = repo.load_all(session, refresh=True)
        if STATE.bundle is None or retrain:
            t1 = time.perf_counter()
            STATE.bundle = propensity.train_model(STATE.frames)
            STATE.timings["train_s"] = round(time.perf_counter() - t1, 3)
        STATE.scores = propensity.score_accounts(STATE.bundle, STATE.frames, D.AS_OF)
        _derive(STATE)
        STATE.warmed_at = time.time()
        STATE.timings["warm_s"] = round(time.perf_counter() - t0, 3)
        return STATE


# Which tables each memoized payload (by key prefix) reads. A refresh drops only
# the payloads whose inputs changed; unknown prefixes are always dropped.
MEMO_DEPENDS: dict[str, set[str]] = {
    "queue_rows": {"activities", "trades", "accounts", "onboarding_events"},
    "queue": {"activities", "trades", "accounts", "onboarding_events"},
    "nba_ctx": {"activities", "trades", "accounts"},
    "pulse_triggers": {"activities", "accounts"},
    "pulse_accounts": {"activities", "accounts"},
    "pulse_hubs": {"market_prices", "price_forecasts"},
    "pulse_history": {"activities", "volatility_events", "trades", "accounts"},
    "ceo_base": {"trades", "accounts", "spread_snapshots"},
    "ceo_snap": {"trades", "accounts", "spread_snapshots"},
    "ceo_weekly": {"activities", "trades", "accounts", "spread_snapshots", "onboarding_events"},
    "funnel_base": {"onboarding_events", "accounts"},
    "funnel": {"onboarding_events", "accounts", "trades"},
    "friction": {"onboarding_events", "accounts", "trades"},
    "segments": {"trades", "accounts"},
    "liquidity": {"spread_snapshots"},
    "scorecards": {"activities", "trades", "accounts"},
    "comp_inputs": {"trades", "accounts"},
    "comp_pay": {"trades", "accounts"},
    "comp_sim": {"trades", "accounts"},
    "marketing": {"marketing_spend", "accounts", "trades"},
    "accounts": {"trades", "accounts"},
    "acct360": {"activities", "outreach_drafts", "trades", "accounts", "contacts", "onboarding_events"},
    "model_report": set(),
}
ACCOUNT_TABLE_INPUTS = {"accounts", "activities", "trades", "onboarding_events", "contacts", "reps"}


def refresh(session, *tables: str) -> AppState:
    """Reload ``tables`` after a write and rebuild only what depends on them."""
    with _LOCK:
        changed = set(tables)
        repo.invalidate_cache(*tables)
        STATE.frames = repo.load_all(session)
        if not changed or changed & ACCOUNT_TABLE_INPUTS:
            STATE.health = features.account_health(STATE.frames, D.AS_OF)
            STATE.accounts = build_account_table(STATE.frames, STATE.scores, STATE.health, D.AS_OF)
        if not changed or changed & {"market_prices", "price_forecasts"}:
            STATE.triggers = volatility.detect_triggers(STATE.frames.market_prices, D.AS_OF, STATE.frames.price_forecasts)
        keep = {}
        for k, v in STATE.memo.items():
            deps = MEMO_DEPENDS.get(k[0]) if isinstance(k, tuple) else None
            if changed and deps is not None and not (deps & changed):
                keep[k] = v
        STATE.memo = keep
        STATE.version += 1
        return STATE


def get_state(session=None) -> AppState:
    """The warmed state; warms lazily (e.g. in tests that skip the lifespan)."""
    if STATE.frames is None:
        if session is None:
            from ..database import SessionLocal

            with SessionLocal() as s:
                return warm(s)
        return warm(session)
    return STATE


def precompute(state: AppState) -> None:
    """Fill the memo for the default (unfiltered) payloads so first hits are fast."""
    from . import accounts as acct_svc
    from . import activation, ceo, funnel, liquidity, marketing, pulse, segments, team

    activation.queue(state)
    pulse.triggers_payload(state)
    for tr in state.triggers:
        pulse.trigger_accounts(state, tr["trigger_id"])
    pulse.history(state)
    for iso in list(D.ISOS) + [None]:
        pulse.hubs(state, iso, 168)
    ceo.weekly(state)
    funnel.funnel(state)
    segments.segments(state)
    for iso in D.ISOS:
        liquidity.liquidity(state, iso, None)
    team.scorecards(state)
    team.simulate(state, None, None)
    marketing.roi(state, 6)
    acct_svc.list_accounts(state)
