"""Claude engine: parsing + fallbacks, with a fake client (the real API is never called)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from ignition.services import compliance
from ignition.services import outreach as O

HOUSTON = "ERCOT-HB_HOUSTON-20261002"


class FakeClient:
    def __init__(self, text=None, stop_reason="end_turn", exc=None):
        self.calls = []
        self._text, self._stop, self._exc = text, stop_reason, exc
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        if self._exc:
            raise self._exc
        blocks = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=self._text or "")]
        return SimpleNamespace(stop_reason=self._stop, content=blocks)


@pytest.fixture()
def fake(monkeypatch):
    def install(**kw):
        c = FakeClient(**kw)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
        monkeypatch.setattr(O, "_claude_client", lambda: c)
        return c
    return install


@pytest.fixture()
def rep_account(client):
    accts = client.get(f"/api/pulse/triggers/{HOUSTON}/accounts?view=all").json()["accounts"]
    return next(a for a in accts if a["segment"] == "REP" and not a["suppressed"] and a["stage"] == "FUNDED")["account_id"]


@pytest.fixture()
def cleanup_drafts():
    from sqlalchemy import delete, func, select

    from ignition.database import SessionLocal
    from ignition.models import OutreachDraft
    from ignition.services import cache

    with SessionLocal() as s:
        mx = s.execute(select(func.max(OutreachDraft.id))).scalar() or 0
    yield
    with SessionLocal() as s:
        s.execute(delete(OutreachDraft).where(OutreachDraft.id > mx))
        s.commit()
        cache.refresh(s, "outreach_drafts")


def test_parse_claude():
    assert O.parse_claude("Subject: Hello there\n\nBody line 1\nline 2") == ("Hello there", "Body line 1\nline 2")
    assert O.parse_claude("  Subject: X  \n \nY") == ("X", "Y")
    assert O.parse_claude("no subject here") is None
    assert O.parse_claude("Subject: only") is None


def test_claude_output_used_when_clean(client, fake, rep_account, cleanup_drafts):
    good = ("Subject: HB_HOUSTON on Oct 2, 2026: a short recap\n\nHi there,\n\nPrices at HB_HOUSTON reached $4,800/MWh on Oct 2, 2026. "
            "Happy to walk your team through how a daily-peak contract settles.\n\nMaya\n\n" + compliance.footer())
    c = fake(text=good)
    r = client.post("/api/outreach/draft", json={"account_id": rep_account, "trigger_id": HOUSTON, "kind": "volatility"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["engine"] == "claude" and d["subject"] == "HB_HOUSTON on Oct 2, 2026: a short recap"
    assert d["compliance"]["passed"] is True
    kw = c.calls[0]
    assert kw["model"] == "claude-opus-5-5" and kw["betas"] == ["server-side-fallback-2026-07-01"]
    assert kw["fallbacks"] == "default" and kw["output_config"] == {"effort": "low"} and kw["max_tokens"] == 4000
    assert "use ONLY the facts" in kw["system"]
    import json
    payload = json.loads(kw["messages"][0]["content"])
    assert set(payload) == {"template", "facts", "banned_phrases"} and payload["facts"]["event_peak_price"] == "$4,800"


def test_invented_numbers_fall_back_to_template(client, fake, rep_account, cleanup_drafts):
    """CTO B1: invented $, hours and % in a Claude draft → blocked → template."""
    bad = ("Subject: HB_HOUSTON recap\n\nPrices at HB_HOUSTON reached $9,999/MWh for 14 hours on Oct 2, 2026, "
           "and desks saw 40% swings.\n\n" + compliance.footer())
    fake(text=bad)
    d = client.post("/api/outreach/draft", json={"account_id": rep_account, "trigger_id": HOUSTON, "kind": "volatility"}).json()
    assert d["engine"] == "template" and "blocked by the linter" in d["facts"]["engine_note"]
    assert "9999" in d["facts"]["engine_note"] and "9,999" not in d["body"]


def test_truncated_output_falls_back(client, fake, rep_account, cleanup_drafts):
    fake(text="Subject: x\n\nHalf a sentence", stop_reason="max_tokens")
    d = client.post("/api/outreach/draft", json={"account_id": rep_account, "trigger_id": HOUSTON, "kind": "volatility"}).json()
    assert d["engine"] == "template" and "truncated" in d["facts"]["engine_note"]


def test_banned_phrase_falls_back_to_template(client, fake, rep_account, cleanup_drafts):
    bad = "Subject: Act now\n\nThis is guaranteed savings for your book.\n\n" + compliance.footer()
    fake(text=bad)
    d = client.post("/api/outreach/draft", json={"account_id": rep_account, "trigger_id": HOUSTON, "kind": "volatility"}).json()
    assert d["engine"] == "template" and d["template_id"] == "VOL_REP_FUNDED"
    assert "blocked by the linter" in d["facts"]["engine_note"]
    assert "guaranteed" not in d["body"].lower().split("illustrative and educational only")[0]
    assert d["compliance"]["passed"] is True


@pytest.mark.parametrize("kw, note", [
    (dict(text="Subject: x\n\ny", stop_reason="refusal"), "refusal"),
    (dict(text="I cannot format this."), "format"),
    (dict(exc=RuntimeError("boom")), "unavailable"),
])
def test_fallbacks(client, fake, rep_account, cleanup_drafts, kw, note):
    fake(**kw)
    d = client.post("/api/outreach/draft", json={"account_id": rep_account, "trigger_id": HOUSTON, "kind": "volatility"}).json()
    assert d["engine"] == "template" and note in d["facts"]["engine_note"]


def test_api_connection_error_falls_back(client, fake, rep_account, cleanup_drafts):
    import anthropic

    try:
        import httpx2 as httpx
    except ImportError:  # pragma: no cover - older SDKs
        import httpx
    fake(exc=anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")))
    d = client.post("/api/outreach/draft", json={"account_id": rep_account, "trigger_id": HOUSTON, "kind": "volatility"}).json()
    assert d["engine"] == "template" and "connection" in d["facts"]["engine_note"]


def test_no_key_means_no_call(client, monkeypatch, rep_account, cleanup_drafts):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(O, "_claude_client", lambda: pytest.fail("Claude must not be called without a key"))
    d = client.post("/api/outreach/draft", json={"account_id": rep_account, "trigger_id": HOUSTON, "kind": "volatility"}).json()
    assert d["engine"] == "template" and "engine_note" not in d["facts"]
