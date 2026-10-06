"""Compliance linter + template rendering (no leftover placeholders)."""
from __future__ import annotations

import re

import pytest

from ignition.services import compliance as C
from ignition.services import outreach as O

FOOT = C.footer()
VOCAB = {"first_name", "account_name", "rep_name", "hub", "iso", "event_peak_price", "event_hours", "event_date",
         "regime_label", "exposure_line", "contract_suggestion", "forecast_line", "walkthrough_cta", "disclaimer"}


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
    ("Serving our not-for-profit co-op members.", "profit"),  # hyphen = word boundary (documented false positive)
    ("Prices will spike again on Tuesday.", "prices will spike"),
])
def test_banned_phrases_block(text, phrase):
    res = C.lint("Subject", body(text))
    assert not res["passed"]
    assert any(f["phrase"] == phrase and f["level"] == "block" and f["rule"] == "R02_BANNED_PHRASE_BLOCK" for f in res["flags"])


def test_banned_in_subject_blocks_and_word_boundaries():
    assert not C.lint("Guaranteed savings inside", body("Hello."))["passed"]
    res = C.lint("Profitability review", body("Prophets and profiteers aside."))  # no whole-word 'profit'
    assert res["passed"] and "R02_BANNED_PHRASE_BLOCK" not in rules_of(res)


def test_caution_flags_do_not_block():
    res = C.lint("An opportunity", body("We can protect the evening ramp."))
    assert res["passed"]
    phrases = {f["phrase"] for f in res["flags"] if f["level"] == "caution"}
    assert {"opportunity", "protect"} <= phrases
    assert all({"rule", "phrase", "level", "message"} <= set(f) for f in res["flags"])


def test_footer_required_and_excluded_from_matching():
    res = C.lint("Recap", "Hello, a recap.")
    assert not res["passed"] and "R01_FOOTER_REQUIRED" in rules_of(res, "block")
    altered = "Hello.\n\n" + FOOT.replace("substantial risk", "some risk")
    assert not C.lint("Recap", altered)["passed"]
    # the footer itself contains 'recommendation' and 'CFTC approval' but is excluded from matching
    assert C.lint("Recap", body("Hello."))["flags"] == []


def test_unverified_dollar_figures_flagged():
    facts = {"event_peak_price": "$4,800", "forecast_line": "a daily peak of $1,650/MWh"}
    ok = C.lint("x", body("Peak $4,800/MWh; forecast $1,650/MWh."), facts)
    assert ok["passed"] and "R04_COMPUTED_FACTS_ONLY" not in rules_of(ok)
    bad = C.lint("x", body("Peak $4,800/MWh; you would have made $25,000."), facts)
    assert any(f["rule"] == "R04_COMPUTED_FACTS_ONLY" and f["phrase"] == "$25,000" and f["level"] == "caution" for f in bad["flags"])


def test_templates_use_only_contract_placeholders_and_render_cleanly():
    facts = {k: f"<{k}>" for k in VOCAB} | {"disclaimer": FOOT}
    for t in O.templates():
        used = set(re.findall(r"\{(\w+)\}", t["subject"] + t["body"]))
        assert used <= VOCAB, (t["template_id"], used - VOCAB)
        out = O.render(t["subject"], facts) + O.render(t["body"], facts)
        assert not re.search(r"\{\w+\}", out), t["template_id"]
        assert t["body"].rstrip().endswith("{disclaimer}"), t["template_id"]


def test_template_selection_specificity_and_fallback():
    assert O.select_template("volatility", "REP", "hurt", "scarcity", None)["template_id"] == "VOL_REP_SCARCITY"
    assert O.select_template("volatility", "REP", "hurt", "winter_peak", None)["template_id"] == "VOL_REP_ANY"
    assert O.select_template("volatility", "PROP", "opportunity", "negative_price", None)["template_id"] == "VOL_PROP_ANY"
    assert O.select_template("volatility", "REP", "opportunity", "negative_price", None)["template_id"] == "VOL_GENERIC_OPP"
    assert O.select_template("activation", "PROP", "opportunity", "scarcity", "FUNDED")["template_id"] == "ACT_FUNDED_NO_API_PROP"
    assert O.select_template("activation", "REP", "hurt", "scarcity", "FUNDED")["template_id"] == "ACT_FUNDED_NO_TRADE"
    assert O.select_template("qbr", "FUND", "opportunity", "scarcity", "ACTIVE")["template_id"] == "QBR_GENERIC"


def test_every_template_renders_from_real_facts_and_passes_lint(client):
    """Real computed facts → every template renders fully and has no blocking flag."""
    from ignition.services import cache

    st = cache.get_state()
    acc = st.accounts
    rep = int(acc[(acc["segment"] == "REP") & acc["isos"].map(lambda x: "ERCOT" in x)].index[0])
    facts, _ = O.build_facts(st, rep, "volatility", "ERCOT-HB_HOUSTON-20261002")
    assert facts["event_peak_price"] == "$4,800" and facts["event_hours"] == 9
    assert facts["regime_label"] == "scarcity pricing" and facts["disclaimer"] == FOOT
    assert not facts["exposure_line"].endswith(".") and "$" not in facts["exposure_line"]
    for t in O.templates():
        s, b = O.render(t["subject"], facts), O.render(t["body"], facts)
        assert "{" not in s + b
        res = C.lint(s, b, facts)
        assert res["passed"], (t["template_id"], [f for f in res["flags"] if f["level"] == "block"])
