"""Compliance linter for outreach drafts (spec D7, ``content/compliance_rules.json``).

* Case-insensitive, whitespace- and quote-normalized, word-boundary matching
  (hyphens count as boundaries) over subject + body **excluding** the footer.
* ``banned_phrases`` → level ``block`` (R02); ``caution_phrases`` → ``caution`` (R03).
* The body must end with ``required_footer`` verbatim, else ``block`` (R01).
* Extra review flags (``caution``): $ figures not present in the facts (R04),
  more than 3 distinct price figures (M02), > 190 words excluding footer (R15).

Returns ``{passed, flags:[{rule, phrase, level, message}]}``; ``passed`` is
true when no flag has level ``block``.
"""
from __future__ import annotations

import re
from functools import lru_cache

from .common import content

_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
_MONEY = re.compile(r"-?\$\s?\d[\d,]*(?:\.\d+)?")


def rules() -> dict:
    return content("compliance_rules")


def footer() -> str:
    return rules()["required_footer"]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").translate(_QUOTES)).strip()


@lru_cache(maxsize=None)
def _pattern(phrase: str) -> re.Pattern:
    p = re.escape(normalize(phrase).lower()).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![\w]){p}(?![\w])", re.IGNORECASE)


def find_phrases(text: str, phrases: list[str]) -> list[str]:
    t = normalize(text)
    return [ph for ph in phrases if _pattern(ph).search(t)]


def _strip_footer(body: str, foot: str) -> tuple[str, bool]:
    b = (body or "").rstrip()
    nb, nf = normalize(b), normalize(foot)
    if nb.endswith(nf):
        idx = b.rfind(foot.strip()[:40])
        return (b[:idx] if idx >= 0 else b), True
    return b, False


def _money_norm(s: str) -> str:
    return s.replace(" ", "").replace(",", "").rstrip("0").rstrip(".") if "." in s else s.replace(" ", "").replace(",", "")


def lint(subject: str, body: str, facts: dict | None = None, cfg: dict | None = None) -> dict:
    cfg = cfg or rules()
    foot = cfg["required_footer"]
    flags: list[dict] = []
    text_body, has_footer = _strip_footer(body, foot)
    if not has_footer:
        flags.append({"rule": "R01_FOOTER_REQUIRED", "phrase": None, "level": "block",
                      "message": "Required disclaimer footer is missing or altered; it must end the message verbatim."})
    scope = f"{subject or ''}\n{text_body}"
    for ph in find_phrases(scope, cfg.get("banned_phrases", [])):
        flags.append({"rule": "R02_BANNED_PHRASE_BLOCK", "phrase": ph, "level": "block",
                      "message": f"Banned phrase “{ph}” (promissory / advice / endorsement language). Edit and re-lint."})
    for ph in find_phrases(scope, cfg.get("caution_phrases", [])):
        flags.append({"rule": "R03_CAUTION_PHRASE_FLAG", "phrase": ph, "level": "caution",
                      "message": f"Caution phrase “{ph}” — reviewer must clear it in context before approval."})
    if facts is not None:
        allowed = {_money_norm(m) for v in facts.values() if isinstance(v, str) for m in _MONEY.findall(v)}
        allowed |= {_money_norm(f"${abs(v):,.2f}") for v in facts.values() if isinstance(v, (int, float))}
        found = _MONEY.findall(scope)
        unverified = sorted({m for m in found if _money_norm(m.lstrip("-")) not in {a.lstrip("-") for a in allowed}})
        for m in unverified:
            flags.append({"rule": "R04_COMPUTED_FACTS_ONLY", "phrase": m, "level": "caution",
                          "message": f"Dollar figure {m} is not in the computed facts — unverified claim."})
        distinct = {_money_norm(m) for m in found}
        if len(distinct) > 3:
            flags.append({"rule": "M02_MAX_PRICE_FIGURES", "phrase": None, "level": "caution",
                          "message": f"{len(distinct)} distinct price figures (max 3)."})
    words = len(re.findall(r"\b\w[\w'-]*\b", text_body))
    if words > 190:
        flags.append({"rule": "R15_LENGTH", "phrase": None, "level": "caution",
                      "message": f"{words} words excluding the footer (> 190): likely contains unrequested claims."})
    return {"passed": not any(f["level"] == "block" for f in flags), "flags": flags, "word_count": words}
