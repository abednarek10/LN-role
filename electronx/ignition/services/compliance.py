"""Compliance linter for outreach drafts (spec D7, ``content/compliance_rules.json``; v1.1 CTO B1/B6).

* Case-insensitive, whitespace- and quote-normalized, word-boundary matching
  (hyphens count as boundaries) over subject + body **excluding** the footer.
* ``allowlist_phrases`` spans are removed first, longest first (B6: "not-for-profit",
  "nonprofit", "parent company guarantee" …), so they never trip banned/caution words.
* ``banned_phrases`` → level ``block`` (R02); ``caution_phrases`` → ``caution`` (R03).
* The body must end with ``required_footer`` verbatim, else ``block`` (R01).
* R04 computed facts only (B1): every numeral (prices, hours, %, MW/MWh, dates) in the
  draft must appear in the facts or in the approved template text. ``strict=True``
  (Claude output) makes an unverified numeral a ``block``; otherwise (human edits) a
  ``caution`` the reviewer must clear.
* Extra review flags (``caution``): more than 3 distinct $ figures (M02), > 190 words (R15).

Returns ``{passed, flags:[{id, rule, phrase, level, message}], word_count}``; ``passed`` is
true when no flag has level ``block``. Flag ids are stable per draft text.
"""
from __future__ import annotations

import re
from functools import lru_cache

from .common import content

_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
_MONEY = re.compile(r"-?\$\s?\d[\d,]*(?:\.\d+)?")
_NUMERAL = re.compile(r"(?<![A-Za-z_\d])(\d[\d,]*(?:\.\d+)?)")


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


def strip_allowlist(text: str, allow: list[str]) -> str:
    """Remove allowlisted spans, longest phrase first (so "not-for-profit" wins over "for-profit")."""
    t = normalize(text)
    for ph in sorted(allow or [], key=len, reverse=True):
        t = _pattern(ph).sub(" ", t)
    return t


def find_phrases(text: str, phrases: list[str], allow: list[str] | None = None) -> list[str]:
    t = strip_allowlist(text, allow or [])
    return [ph for ph in phrases if _pattern(ph).search(t)]


def _strip_footer(body: str, foot: str) -> tuple[str, bool]:
    b = (body or "").rstrip()
    if normalize(b).endswith(normalize(foot)):
        idx = b.rfind(foot.strip()[:40])
        return (b[:idx] if idx >= 0 else b), True
    return b, False


def _num_norm(s: str) -> str:
    s = s.replace(",", "").replace("$", "").replace(" ", "").lstrip("-")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def numerals(text: str) -> set[str]:
    """Normalized numerals in ``text`` (word-embedded digits such as SP15 are ignored)."""
    return {_num_norm(m) for m in _NUMERAL.findall(normalize(text)) if _num_norm(m)}


def _fact_numerals(facts: dict) -> set[str]:
    out: set[str] = set()
    for v in facts.values():
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, (int, float)):
            out |= {_num_norm(f"{v:.2f}"), _num_norm(f"{v:.0f}"), _num_norm(str(v))}
        elif isinstance(v, str):
            out |= numerals(v)
    return out


def lint(subject: str, body: str, facts: dict | None = None, cfg: dict | None = None, *,
         allowed_text: str = "", strict: bool = False) -> dict:
    cfg = cfg or rules()
    foot = cfg["required_footer"]
    allow = cfg.get("allowlist_phrases", [])
    flags: list[dict] = []
    text_body, has_footer = _strip_footer(body, foot)
    if not has_footer:
        flags.append({"rule": "R01_FOOTER_REQUIRED", "phrase": None, "level": "block",
                      "message": "Required disclaimer footer is missing or altered; it must end the message verbatim."})
    scope = f"{subject or ''}\n{text_body}"
    for ph in find_phrases(scope, cfg.get("banned_phrases", []), allow):
        flags.append({"rule": "R02_BANNED_PHRASE_BLOCK", "phrase": ph, "level": "block",
                      "message": f"Banned phrase “{ph}” (promissory / advice / endorsement language). Edit and re-lint."})
    for ph in find_phrases(scope, cfg.get("caution_phrases", []), allow):
        flags.append({"rule": "R03_CAUTION_PHRASE_FLAG", "phrase": ph, "level": "caution",
                      "message": f"Caution phrase “{ph}” — reviewer must clear it in context before approval."})
    if facts is not None:
        allowed = _fact_numerals(facts) | numerals(allowed_text)
        unverified = sorted(numerals(scope) - allowed, key=lambda x: (len(x), x))
        for n in unverified:
            flags.append({"rule": "R04_COMPUTED_FACTS_ONLY", "phrase": n, "level": "block" if strict else "caution",
                          "message": f"Number {n} is not in the computed facts or the approved template — "
                                     + ("invented figures are blocked." if strict else "unverified claim; reviewer must confirm.")})
        distinct = {_num_norm(m) for m in _MONEY.findall(scope)}
        if len(distinct) > 3:
            flags.append({"rule": "M02_MAX_PRICE_FIGURES", "phrase": None, "level": "caution",
                          "message": f"{len(distinct)} distinct price figures (max 3)."})
    words = len(re.findall(r"\b\w[\w'-]*\b", text_body))
    if words > 190:
        flags.append({"rule": "R15_LENGTH", "phrase": None, "level": "caution",
                      "message": f"{words} words excluding the footer (> 190): likely contains unrequested claims."})
    for i, f in enumerate(flags, start=1):
        f["id"] = f"{f['rule'].split('_')[0]}-{i}"
    return {"passed": not any(f["level"] == "block" for f in flags), "flags": flags, "word_count": words}


def add_flag(flags: list[dict], rule: str, level: str, message: str, phrase=None) -> None:
    flags.append({"rule": rule, "phrase": phrase, "level": level, "message": message,
                  "id": f"{rule.split('_')[0]}-{len(flags) + 1}"})
