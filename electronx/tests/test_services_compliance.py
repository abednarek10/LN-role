"""Compliance linter (v1.1: allowlist, flag ids, every-numeral R04) + template rendering and selection."""
from __future__ import annotations

import re

import pytest

from ignition.services import compliance as C
from ignition.services import outreach as O

FOOT = C.footer()
VOCAB = {"first_name", "account_name", "rep_name", "hub", "iso", "event_peak_price", "event_hours", "event_date",
         "regime_label", "exposure_line", "contract_suggestion", "forecast_line", "walkthrough_cta", "disclaimer",
         "market_quality_line"}


def body(text: str) -> str:
    return f"{text}\n\n{FOOT}"


def rules_of(res, level=None):
    return {f["rule"] for f in res["flags"] if level is None or f["level"] == level}


def test_clean_draft_passes():
    res = C.lint("HB_NORTH recap", body("Hi Ana, a short factual recap of the week at HB_NORTH."))
    assert res["passed"] and res["flags"] == []


@pytest.mark.parametrize("text, phrase", [
    ("This hedge is guaranteed to work.", "guaranteed"),
    ("A risk-free way to manage load.", "risk-free"),
    ("You CAN'T LOSE with daily peaks.", "can't lose"),
    ("You can’t lose here.", "can't lose"),             # curly quote normalized
    ("It is   risk \n free.", "risk free"),                  # whitespace normalized
    ("A very profitable desk.", "profitable"),
    ("Prices will spike again on Tuesday.", "prices will spike"),
])
def test_banned_phrases_block(text, phrase):
    res = C.lint("Subject", body(text))
    assert not res["passed"]
    assert any(f["phrase"] == phrase and f["level"] == "block" and f["rule"] == "R02_BANNED_PHRASE_BLOCK" for f in res["flags"])


@pytest.mark.parametrize("text", [
    "Serving our not-for-profit co-op members.",
    "As a nonprofit cooperative, members own the utility.",
    "Your non-profit board reviews the hedge policy.",
    "The parent company guarantee is on file with onboarding.",
    "We reviewed the profit and loss statement format.",
])
def test_allowlist_neutralizes_false_positives(text):
    res = C.lint("Co-op recap", body(text))
    assert res["passed"], res["flags"]
    assert "R02_BANNED_PHRASE_BLOCK" not in rules_of(res)


def test_allowlist_does_not_hide_real_claims():
    res = C.lint("Recap", body("Our not-for-profit members can lock in a profit here."))
    assert not res["passed"] and any(f["phrase"] == "profit" for f in res["flags"])


def test_banned_in_subject_blocks_and_word_boundaries():
    assert not C.lint("Guaranteed savings inside", body("Hello."))["passed"]
    res = C.lint("Profitability review", body("Prophets and profiteers aside."))  # no whole-word 'profit'
    assert res["passed"] and "R02_BANNED_PHRASE_BLOCK" not in rules_of(res)


def test_caution_flags_do_not_block_and_have_ids():
    res = C.lint("An opportunity", body("We can protect the evening ramp."))
    assert res["passed"]
    phrases = {f["phrase"] for f in res["flags"] if f["level"] == "caution"}
    assert {"opportunity", "protect"} <= phrases
    assert all({"id", "rule", "phrase", "level", "message"} <= set(f) for f in res["flags"])
    assert len({f["id"] for f in res["flags"]}) == len(res["flags"])


def test_footer_required_and_excluded_from_matching():
    res = C.lint("Recap", "Hello, a recap.")
    assert not res["passed"] and "R01_FOOTER_REQUIRED" in rules_of(res, "block")
    altered = "Hello.\n\n" + FOOT.replace("substantial risk", "some risk")
    assert not C.lint("Recap", altered)["passed"]
    assert C.lint("Recap", body("Hello."))["flags"] == []


def test_every_numeral_must_come_from_facts():
    facts = {"event_peak_price": "$4,800", "event_hours": 9, "event_date": "Oct 2, 2026",
             "forecast_line": "a daily peak of $1,650/MWh at HB_HOUSTON on Oct 7"}
    ok = C.lint("x", body("Peak $4,800/MWh over 9 hours on Oct 2, 2026; forecast $1,650/MWh on Oct 7."), facts, strict=True)
    assert ok["passed"] and "R04_COMPUTED_FACTS_ONLY" not in rules_of(ok)
    bad = C.lint("x", body("Peak $9,999/MWh for 14 hours; desks saw 40% swings across 250 MW."), facts, strict=True)
    invented = {f["phrase"] for f in bad["flags"] if f["rule"] == "R04_COMPUTED_FACTS_ONLY"}
    assert {"9999", "14", "40", "250"} <= invented and not bad["passed"]
    human = C.lint("x", body("Peak $4,800/MWh; I can do 30 minutes on Thursday."), facts)
    assert human["passed"] and any(f["phrase"] == "30" and f["level"] == "caution" for f in human["flags"])
    tmpl = C.lint("x", body("A 20-minute walkthrough."), facts, allowed_text="A 20-minute walkthrough.", strict=True)
    assert tmpl["passed"]  # numbers in the approved template text are allowed
    assert C.numerals("SP15 and NP15 hubs") == set()  # digits inside hub names are not figures


def test_templates_use_only_contract_placeholders_and_render_cleanly():
    facts = {k: f"<{k}>" for k in VOCAB} | {"disclaimer": FOOT}
    for t in O.templates():
        used = set(re.findall(r"\{(\w+)\}", t["subject"] + t["body"]))
        assert used <= VOCAB, (t["template_id"], used - VOCAB)
        out = O.render(t["subject"], facts) + O.render(t["body"], facts)
        assert not re.search(r"\{\w+\}", out), t["template_id"]
        assert t["body"].rstrip().endswith("{disclaimer}"), t["template_id"]


def test_template_selection_stage_first_then_specificity():
    sel = lambda *a: O.select_template(*a)["template_id"]  # noqa: E731
    assert sel("volatility", "REP", "hurt", "scarcity", "FUNDED") == "VOL_REP_FUNDED"
    assert sel("volatility", "PROP", "opportunity", "scarcity", "FUNDED") == "VOL_PROP_FUNDED_MQ"
    assert sel("volatility", "FUND", "opportunity", "scarcity", "KYC_APPROVED") == "VOL_FUND_KYC_APPROVED_MQ"
    assert sel("volatility", "CI_LOAD", "hurt", "scarcity", "FUNDED") == "VOL_FUNDED_HURT"     # stage beats segment
    assert sel("volatility", "STORAGE", "opportunity", "scarcity", "KYC_APPROVED") == "VOL_KYC_APPROVED_OPP"
    # no stage-specific template → stageless, most specific
    assert sel("volatility", "REP", "hurt", "scarcity", "FIRST_TRADE") == "VOL_REP_SCARCITY"
    assert sel("volatility", "REP", "hurt", "winter_peak", "QUALIFIED") == "VOL_REP_ANY"
    assert sel("volatility", "REP", "opportunity", "negative_price", "SIGNED") == "VOL_GENERIC_OPP"
    assert sel("activation", "PROP", "opportunity", "scarcity", "FUNDED") == "ACT_FUNDED_NO_API_PROP"
    assert sel("activation", "REP", "hurt", "scarcity", "FUNDED") == "ACT_FUNDED_NO_TRADE"
    assert sel("qbr", "FUND", "opportunity", "scarcity", "ACTIVE") == "QBR_GENERIC"


def test_every_template_renders_from_real_facts_and_passes_lint(client):
    """Real computed facts → every template renders fully and has no blocking flag."""
    from ignition.services import cache

    st = cache.get_state()
    acc = st.accounts
    rep = int(acc[(acc["segment"] == "REP") & (acc["hub"] == "HB_HOUSTON")].index[0])
    facts, meta = O.build_facts(st, rep, "volatility", "ERCOT-HB_HOUSTON-20261002")
    assert facts["event_peak_price"] == "$4,800" and facts["event_hours"] == 9
    assert facts["regime_label"] == "scarcity pricing" and facts["disclaimer"] == FOOT
    assert not facts["exposure_line"].endswith(".") and "$" not in facts["exposure_line"]
    assert "HB_HOUSTON" in facts["market_quality_line"] and "two-sided uptime" in facts["market_quality_line"]
    assert meta["market_quality"]["event_uptime_pct"] > 50
    for t in O.templates():
        s, b = O.render(t["subject"], facts), O.render(t["body"], facts)
        assert "{" not in s + b
        res = C.lint(s, b, facts, allowed_text=f"{s}\n{b}")
        assert res["passed"], (t["template_id"], [f for f in res["flags"] if f["level"] == "block"])


def test_negative_price_event_hours_are_negative_hours(client):
    from ignition.services import cache

    st = cache.get_state()
    acc = st.accounts
    aid = int(acc[(acc["isos"].map(lambda x: "CAISO" in x)) & (acc["stage"] == "FUNDED")].index[0])
    facts, meta = O.build_facts(st, aid, "volatility", "CAISO-SP15-20261003")
    trig = next(t for t in st.triggers if t["trigger_id"] == "CAISO-SP15-20261003")
    assert facts["event_hours"] == trig["neg_hours"] == 14 and facts["regime_label"] == "negative pricing"
