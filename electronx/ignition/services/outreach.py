"""Outreach drafts (spec D7, contract notes #7/#10): template + optional Claude.

Flow: ``draft`` (computed facts → template → optional Claude rewrite → lint →
persist ``pending_review``) → ``approve`` (409 unless lint passed) → ``queue``
(409 unless approved; logs an ``activities`` row stamped AS_OF and refreshes
app state so the Activation Queue re-ranks).

Guardrails
* Facts are computed from data only (prices, hours, dates, forecast); Claude
  receives facts + the rendered template and must not add numbers.
* Claude runs only when ``ANTHROPIC_API_KEY`` is set; any API error, refusal,
  unparseable output or a *blocked* lint result falls back to the template.
* Every draft — template or Claude — goes through the same linter.
"""
from __future__ import annotations

import json
import os
import re

import pandas as pd

from .. import definitions as D
from ..models import Activity, OutreachDraft
from . import compliance, volatility
from .common import AS_OF_TS, content, fmt_date_long, fmt_price, num, ts_str

KINDS = ("volatility", "activation", "qbr")
CLAUDE_MODEL = "claude-opus-5-5"
SYSTEM_PROMPT = (
    "You are a compliance-aware sales writer for ElectronX, a CFTC-regulated electricity derivatives exchange. "
    "Rewrite the provided outreach template into a short, specific email for the named contact. "
    "Rules: use ONLY the facts provided in the JSON; never invent or change prices, numbers, dates, hubs, sizes or forecasts; "
    "add no figures that are not in the facts. No investment, trading or hedging advice; never tell the reader what to buy, "
    "sell, size or when to trade; no promissory, performance, savings or urgency language; never use any banned phrase listed. "
    "Offer a walkthrough; the decision is always the recipient's. Keep the body at or under 150 words before the disclaimer. "
    "Return exactly: 'Subject: <subject>' then a blank line then the body. "
    "The body must end with the exact disclaimer text from the facts, verbatim and unchanged."
)

_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_CONTRACT = {
    "HOURLY": "the {hub} HOURLY contract (1 MWh per contract, one delivery hour)",
    "DAILY_PEAK": "the {hub} DAILY_PEAK contract (16 MWh: 1 MW across the 16 on-peak hours)",
    "WEEKLY_PEAK": "the {hub} WEEKLY_PEAK contract (80 MWh: 1 MW across five on-peak days)",
}
_STAGE_ALIAS = {"AT_RISK": "DORMANT"}


class OutreachError(ValueError):
    """Bad request (422)."""


class NotFound(LookupError):
    """Unknown account / trigger / draft (404)."""


class Conflict(RuntimeError):
    """Workflow state violation (409)."""


# ---------------------------------------------------------------------------
# Template selection
# ---------------------------------------------------------------------------
def templates() -> list[dict]:
    return content("outreach_templates")


def select_template(kind: str, segment: str, direction: str | None, regime: str | None, stage: str | None,
                    tpls: list[dict] | None = None) -> dict | None:
    """Most specific template for (kind, segment, direction, regime, stage); '*' is a wildcard."""
    best, best_score = None, -1
    for t in tpls or templates():
        if t["kind"] != kind:
            continue
        score = 0
        ok = True
        for field, val, w in (("segment", segment, 8), ("direction", direction, 4), ("regime", regime, 2), ("stage", stage, 1)):
            tv = t.get(field, "*")
            if tv == "*":
                continue
            if tv != val:
                ok = False
                break
            score += w
        if ok and score > best_score:
            best, best_score = t, score
    return best


def render(text: str, facts: dict) -> str:
    def sub(m):
        k = m.group(1)
        if k not in facts or facts[k] is None:
            raise OutreachError(f"template placeholder {{{k}}} has no fact")
        return str(facts[k])
    return _PLACEHOLDER.sub(sub, text)


# ---------------------------------------------------------------------------
# Facts (computed from data only)
# ---------------------------------------------------------------------------
def _first_name(frames, account_id: int) -> str:
    c = frames.contacts[frames.contacts["account_id"] == account_id]
    if not len(c):
        return "there"
    c = c.sort_values(["is_champion", "id"], ascending=[False, True])
    return str(c.iloc[0]["name"]).split()[0]


def _forecast_line(frames, hub: str) -> tuple[str, dict | None]:
    fc = frames.price_forecasts
    f = fc[fc["hub"] == hub]
    if not len(f):
        return f"No model forecast is available for {hub} this week.", None
    top = f.sort_values("forecast_peak_lmp", ascending=False).iloc[0]
    issued = pd.Timestamp(top["issued_at"])
    line = (f"the 5-day model forecast issued {issued.strftime('%b')} {issued.day} shows a daily peak of "
            f"{fmt_price(top['forecast_peak_lmp'])}/MWh at {hub} on {pd.Timestamp(top['date']).strftime('%b')} {pd.Timestamp(top['date']).day}; "
            "forecasts are model estimates and can change.")
    line = line[0].upper() + line[1:]
    return line, {"forecast_peak_lmp": float(top["forecast_peak_lmp"]), "forecast_date": pd.Timestamp(top["date"]).date().isoformat()}


def _event_for(state, row, trigger_id: str | None) -> dict | None:
    """Live trigger by id, else the account's live trigger, else its latest historical event."""
    if trigger_id:
        t = next((x for x in state.triggers if x["trigger_id"] == trigger_id), None)
        if t is None:
            ev = state.frames.volatility_events
            e = ev[ev["trigger_id"] == trigger_id]
            if not len(e):
                raise NotFound(f"trigger {trigger_id} not found")
            r = e.iloc[0]
            return {"trigger_id": r["trigger_id"], "hub": r["hub"], "iso": r["iso"], "regime": r["regime"],
                    "peak_lmp": float(r["peak_lmp"]), "hours": int(r["spike_hours"]), "start_ts": r["start_ts"], "live": False}
        hours = t["neg_hours"] if t["regime"] == "negative_price" else t["spike_hours"]
        return {"trigger_id": t["trigger_id"], "hub": t["hub"], "iso": t["iso"], "regime": t["regime"],
                "peak_lmp": float(t["peak_lmp"]), "hours": int(hours), "start_ts": t["start_ts"], "live": True}
    isos = set(row["isos"])
    live = [t for t in state.triggers if t["iso"] in isos and pd.Timestamp(t["start_ts"]) < AS_OF_TS]
    if live:
        own = [t for t in live if t["hub"] == row["hub"]]
        return _event_for(state, row, max(own or live, key=lambda t: t["severity"])["trigger_id"])
    ev = state.frames.volatility_events
    ev = ev[ev["iso"].isin(isos)].sort_values("start_ts")
    if len(ev):
        return _event_for(state, row, ev.iloc[-1]["trigger_id"])
    return None


def build_facts(state, account_id: int, kind: str, trigger_id: str | None) -> tuple[dict, dict]:
    """(template facts, meta) for an account. Raises NotFound / OutreachError."""
    acc = state.accounts
    if account_id not in acc.index:
        raise NotFound(f"account {account_id} not found")
    row = acc.loc[account_id].to_dict()
    msg = content("segment_messaging")["segments"].get(row["segment"], {})
    event = _event_for(state, row, trigger_id) if (kind == "volatility" or trigger_id or row["stage"] in ("TARGET", "QUALIFIED")) else None
    if kind == "volatility" and event is None:
        raise OutreachError("no volatility event in the account's exposure ISOs")
    hub = event["hub"] if event else row["hub"]
    iso = event["iso"] if event else row["primary_iso"]
    regime = event["regime"] if event else ("negative_price" if row["primary_iso"] == "CAISO" and row["segment"] == "IPP" else "scarcity")
    direction = volatility.exposure_direction(row["segment"], regime, bool(row["is_liquidity_partner"]))
    line = volatility.exposure_line(row["segment"], hub, regime, bool(row["is_liquidity_partner"]))
    line = line.rstrip(". ")
    line = line[0].lower() + line[1:] if line else line
    product = msg.get("first_product", "DAILY_PEAK")
    forecast_line, fc = _forecast_line(state.frames, hub)
    facts = {
        "first_name": _first_name(state.frames, account_id),
        "account_name": row["name"],
        "rep_name": row["rep_name"] or "The ElectronX team",
        "hub": hub,
        "iso": iso,
        "event_peak_price": fmt_price(event["peak_lmp"]) if event else None,
        "event_hours": event["hours"] if event else None,
        "event_date": fmt_date_long(event["start_ts"]) if event else None,
        "regime_label": D.REGIME_LABELS[regime].lower(),
        "exposure_line": line,
        "contract_suggestion": _CONTRACT.get(product, _CONTRACT["DAILY_PEAK"]).format(hub=hub),
        "forecast_line": forecast_line,
        "walkthrough_cta": ("If a 20-minute walkthrough with your trading or risk lead would help, reply with two times "
                            "that suit and I will send an invite."),
        "disclaimer": compliance.footer(),
    }
    meta = {"account": row, "event": event, "direction": direction, "regime": regime, "forecast": fc, "product": product}
    return facts, meta


def _template_for(kind: str, row: dict, direction: str, regime: str) -> tuple[dict, str]:
    """Resolve the template, applying stage fallbacks; returns (template, effective kind)."""
    stage = _STAGE_ALIAS.get(row["stage"], row["stage"])
    if kind == "activation":
        t = select_template("activation", row["segment"], direction, regime, stage)
        if t is not None and t.get("stage", "*") in (stage, "*"):
            return t, "activation"
        if row["stage"] in ("ACTIVE", "EXPANDING"):
            return select_template("qbr", row["segment"], direction, regime, "*"), "qbr"
        return select_template("volatility", row["segment"], direction, regime, None), "volatility"
    t = select_template(kind, row["segment"], direction, regime, stage if kind != "volatility" else None)
    return t, kind


# ---------------------------------------------------------------------------
# Claude engine
# ---------------------------------------------------------------------------
def _claude_client():  # separated so tests can monkeypatch a fake
    import anthropic

    return anthropic.Anthropic(timeout=20.0, max_retries=1)


def parse_claude(text: str) -> tuple[str, str] | None:
    m = re.match(r"\s*Subject:\s*(.+?)\s*\n\s*\n(.*)\Z", text or "", re.S)
    if not m:
        return None
    subj, body = m.group(1).strip(), m.group(2).strip()
    return (subj, body) if subj and body else None


def claude_rewrite(subject: str, body: str, facts: dict) -> tuple[tuple[str, str] | None, str]:
    """(parsed (subject, body) or None, note)."""
    try:
        import anthropic
    except Exception as exc:  # noqa: BLE001
        return None, f"anthropic SDK unavailable: {exc}"
    try:
        client = _claude_client()
        resp = client.beta.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "low"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps({
                "template": f"Subject: {subject}\n\n{body}",
                "facts": facts,
                "banned_phrases": compliance.rules().get("banned_phrases", []),
            })}],
        )
        if resp.stop_reason == "refusal":
            return None, "Claude declined (refusal); template used"
        text = "".join(b.text for b in resp.content if b.type == "text")
    except anthropic.APIConnectionError as exc:
        return None, f"Claude connection error; template used ({type(exc).__name__})"
    except anthropic.RateLimitError:
        return None, "Claude rate-limited; template used"
    except anthropic.APIStatusError as exc:
        return None, f"Claude API error {getattr(exc, 'status_code', '?')}; template used"
    except Exception as exc:  # noqa: BLE001 - last resort: never fail a draft on the LLM
        return None, f"Claude unavailable ({type(exc).__name__}); template used"
    parsed = parse_claude(text)
    if parsed is None:
        return None, "Claude output not in 'Subject:' format; template used"
    return parsed, "claude"


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------
def _public_facts(facts: dict, meta: dict, template_id: str, kind: str) -> dict:
    out = {k: v for k, v in facts.items() if k != "disclaimer"}
    ev = meta.get("event")
    out.update({
        "kind": kind, "template_id": template_id, "segment": meta["account"]["segment"],
        "direction": meta["direction"], "regime": meta["regime"],
        "trigger_id": ev["trigger_id"] if ev else None,
        "event_peak_lmp": num(ev["peak_lmp"], 2) if ev else None,
        "event_start_ts": ts_str(ev["start_ts"]) if ev else None,
        "forecast_peak_lmp": meta["forecast"]["forecast_peak_lmp"] if meta.get("forecast") else None,
        "forecast_date": meta["forecast"]["forecast_date"] if meta.get("forecast") else None,
        "first_product": meta["product"],
    })
    return out


def create_draft(state, session, account_id: int, kind: str, trigger_id: str | None = None) -> dict:
    if kind not in KINDS:
        raise OutreachError(f"kind must be one of {KINDS}")
    facts, meta = build_facts(state, account_id, kind, trigger_id)
    row = meta["account"]
    tpl, eff_kind = _template_for(kind, row, meta["direction"], meta["regime"])
    if tpl is None:
        raise OutreachError(f"no {kind} template for segment {row['segment']} / stage {row['stage']}")
    if eff_kind == "volatility" and meta.get("event") is None:
        facts, meta = build_facts(state, account_id, "volatility", trigger_id)
    subject, body = render(tpl["subject"], facts), render(tpl["body"], facts)
    pub = _public_facts(facts, meta, tpl["template_id"], eff_kind)
    if eff_kind != kind:
        pub["template_fallback"] = f"no {kind} template for stage {row['stage']}; used {eff_kind}"
    engine = "template"
    if os.environ.get("ANTHROPIC_API_KEY"):
        parsed, note = claude_rewrite(subject, body, facts)
        if parsed is not None:
            lint_c = compliance.lint(parsed[0], parsed[1], facts)
            if lint_c["passed"]:
                subject, body, engine = parsed[0], parsed[1], "claude"
            else:
                blocked = ", ".join(f["phrase"] or f["rule"] for f in lint_c["flags"] if f["level"] == "block")
                pub["engine_note"] = f"Claude draft blocked by the linter ({blocked}); template used"
        else:
            pub["engine_note"] = note
    lint = compliance.lint(subject, body, facts)
    flags = list(lint["flags"])
    # audience / cadence rules (R07, R14) for volatility outreach
    if eff_kind == "volatility":
        if row["stage"] == "TARGET":
            flags.append({"rule": "R07_ELIGIBLE_AUDIENCE_ONLY", "phrase": None, "level": "block",
                          "message": "Eligibility not screened (TARGET stage): volatility outreach is limited to qualified commercial/institutional accounts."})
        lt = row.get("last_trig_ts")
        if lt is not None and pd.notna(lt) and (AS_OF_TS - pd.Timestamp(lt)).total_seconds() / 86400 < D.TRIGGER_COOLDOWN_D:
            flags.append({"rule": "R14_CADENCE_LIMITS", "phrase": None, "level": "block",
                          "message": f"A triggered sequence was already sent on {pd.Timestamp(lt).date().isoformat()} (max 1 per {D.TRIGGER_COOLDOWN_D} days)."})
    passed = not any(f["level"] == "block" for f in flags)
    ev = meta.get("event")
    trig = ev["trigger_id"] if (ev and eff_kind == "volatility") else None
    rep_id = row["rep_id"]
    d = OutreachDraft(
        account_id=int(account_id), rep_id=int(rep_id) if pd.notna(rep_id) else None, trigger_id=trig,
        created_at=D.AS_OF, subject=subject[:300], body=body, engine=engine,
        status="pending_review",
        compliance_flags=json.dumps({"passed": passed, "flags": flags, "kind": eff_kind, "template_id": tpl["template_id"]}),
    )
    session.add(d)
    session.commit()
    session.refresh(d)
    return {"draft_id": d.id, "account_id": int(account_id), "kind": eff_kind, "trigger_id": trig,
            "template_id": tpl["template_id"], "subject": subject, "body": body, "engine": engine,
            "facts": pub, "compliance": {"passed": passed, "flags": flags}, "status": d.status}


def _get(session, draft_id: int) -> OutreachDraft:
    d = session.get(OutreachDraft, draft_id)
    if d is None:
        raise NotFound(f"draft {draft_id} not found")
    return d


def _meta(d: OutreachDraft) -> dict:
    try:
        m = json.loads(d.compliance_flags or "{}")
    except json.JSONDecodeError:
        m = {}
    if isinstance(m, list):  # tolerate a bare flag list
        m = {"flags": m, "passed": not any(f.get("level") == "block" for f in m)}
    return m


def approve(session, draft_id: int) -> dict:
    d = _get(session, draft_id)
    m = _meta(d)
    if not m.get("passed", False):
        raise Conflict("draft has blocking compliance flags; edit and re-lint before approval")
    if d.status in ("queued", "sent"):
        raise Conflict(f"draft is already {d.status}")
    if d.status == "rejected":
        raise Conflict("draft was rejected")
    d.status = "approved"
    session.commit()
    return {"draft_id": d.id, "status": d.status}


def queue(session, draft_id: int) -> dict:
    d = _get(session, draft_id)
    if d.status != "approved":
        raise Conflict(f"draft must be approved before queueing (status: {d.status})")
    kind = _meta(d).get("kind") or ("volatility" if d.trigger_id else "activation")
    act = Activity(account_id=d.account_id, rep_id=d.rep_id, ts=D.AS_OF,
                   kind="triggered_email" if d.trigger_id else "email", outcome="none",
                   trigger_id=d.trigger_id, sequence="volatility" if d.trigger_id else kind)
    session.add(act)
    d.status = "queued"
    session.commit()
    return {"draft_id": d.id, "status": d.status, "activity_id": act.id, "account_id": d.account_id,
            "trigger_id": d.trigger_id, "logged_at": ts_str(D.AS_OF)}


def get_draft(session, draft_id: int) -> dict:
    d = _get(session, draft_id)
    m = _meta(d)
    return {"draft_id": d.id, "account_id": d.account_id, "trigger_id": d.trigger_id, "subject": d.subject, "body": d.body,
            "engine": d.engine, "status": d.status, "created_at": ts_str(d.created_at), "kind": m.get("kind"),
            "compliance": {"passed": m.get("passed", False), "flags": m.get("flags", [])}}
