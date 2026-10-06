"""Canonical definitions — the single source of truth (spec §B, §C, §A D2–D5).

Every view, service, memo and comp calculation imports from here. Changing a
number here changes it everywhere; never re-declare these elsewhere.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
# ---------------------------------------------------------------------------
# Time anchors (naive UTC)
# ---------------------------------------------------------------------------
AS_OF: datetime = datetime(2026, 10, 5)  # Monday 00:00; data runs through Sun 10-04 23:00
AS_OF_DATE: date = AS_OF.date()
WEEK_END: date = date(2026, 10, 2)  # default week_end (Friday close)
HISTORY_START: datetime = datetime(2026, 1, 5)  # exchange launch; hourly prices start here
FORECAST_DAYS: int = 5

# ---------------------------------------------------------------------------
# Activity / activation definitions (D2, D3)
# ---------------------------------------------------------------------------
ACTIVE_MIN_DAYS: int = 4  # distinct trading days in trailing ACTIVE_LOOKBACK_D calendar days
ACTIVE_LOOKBACK_D: int = 30
AT_RISK_DAYS: tuple[int, int] = (1, 3)
DORMANT_MIN_FUNDED_D: int = 30  # Dormant only after being funded >= 30 d
QUALIFYING_CONTRACTS: int = 10
ACTIVATION_WINDOW_D: int = 60  # model label horizon
COHORT_FIRST_TRADE_D: int = 30  # CEO cohort activation window
ADV_WINDOW_TD: int = 20  # trailing trading days (weekdays) for ADV
ACTIVE_RATE_MIN_AGE_D: int = 20  # active rate denominator: funded accounts older than this
SMALL_COHORT_N: int = 20
EXPANDING_MIN_ACTIVE_D: int = 60
EXPANDING_ADV_MULT: float = 1.5
STALL_FUNDED_NO_TRADE_D: int = 21  # CEO "stalled accounts"

# ---------------------------------------------------------------------------
# Segments, sides
# ---------------------------------------------------------------------------
SEGMENTS: dict[str, dict[str, str]] = {
    "IPP": {"label": "Independent Power Producer", "side": "hedger"},
    "STORAGE": {"label": "Battery Storage Operator", "side": "hedger"},
    "REP": {"label": "Retail Electric Provider", "side": "hedger"},
    "CI_LOAD": {"label": "C&I / Large Load", "side": "hedger"},
    "UTILITY": {"label": "Utility / Co-op / Muni", "side": "hedger"},
    "DATACENTER": {"label": "Data Center Developer", "side": "hedger"},
    "PROP": {"label": "Proprietary Trading Firm", "side": "speculator"},
    "FUND": {"label": "Hedge Fund / Asset Manager", "side": "speculator"},
}
SEGMENT_CODES: list[str] = list(SEGMENTS)
SIDES: list[str] = ["hedger", "speculator", "liquidity_partner"]
HEDGER_SEGMENTS: frozenset[str] = frozenset(s for s, v in SEGMENTS.items() if v["side"] == "hedger")
SPECULATOR_SEGMENTS: frozenset[str] = frozenset(
    s for s, v in SEGMENTS.items() if v["side"] == "speculator"
)

# ---------------------------------------------------------------------------
# Markets
# ---------------------------------------------------------------------------
ISOS: dict[str, list[str]] = {
    "ERCOT": ["HB_NORTH", "HB_HOUSTON", "HB_WEST"],
    "PJM": ["PJM_WESTERN_HUB"],
    "CAISO": ["SP15", "NP15"],
    "MISO": ["MISO_INDIANA_HUB"],
}
ISO_CODES: list[str] = list(ISOS)
HUBS: list[str] = [h for hubs in ISOS.values() for h in hubs]
HUB_ISO: dict[str, str] = {h: iso for iso, hubs in ISOS.items() for h in hubs}
MAIN_HUB: dict[str, str] = {
    "ERCOT": "HB_NORTH",
    "PJM": "PJM_WESTERN_HUB",
    "CAISO": "SP15",
    "MISO": "MISO_INDIANA_HUB",
}
# Rough UTC offset used only for intraday price shapes in the generator.
ISO_UTC_OFFSET_H: dict[str, int] = {"ERCOT": -5, "PJM": -4, "CAISO": -7, "MISO": -5}

TENORS: dict[str, float] = {"HOURLY": 1.0, "DAILY_PEAK": 16.0, "WEEKLY_PEAK": 80.0}  # MWh/contract
SPREAD_TENORS: list[str] = ["HOURLY", "DAILY_PEAK"]

FEE_TAKER_PER_CONTRACT: float = 0.25
FEE_MAKER_PER_CONTRACT: float = 0.10

# ---------------------------------------------------------------------------
# Funnel
# ---------------------------------------------------------------------------
STAGES: list[str] = [
    "TARGET",
    "QUALIFIED",
    "SIGNED",
    "KYC_APPROVED",
    "FUNDED",
    "FIRST_TRADE",
    "ACTIVE",
    "EXPANDING",
    "AT_RISK",
    "DORMANT",
]
ACTIVE_STAGES: frozenset[str] = frozenset({"ACTIVE", "EXPANDING"})
PRE_TRADE_STAGES: frozenset[str] = frozenset({"SIGNED", "KYC_APPROVED", "FUNDED"})
PRE_SIGN_STAGES: frozenset[str] = frozenset({"TARGET", "QUALIFIED"})

ONBOARDING_STEPS: list[str] = [
    "contract_signed",
    "platform_account_created",
    "first_login",
    "kyc_submitted",
    "kyc_info_requested",  # repeatable
    "kyc_approved",
    "bank_linked",
    "funded",
    "api_key_created",  # optional; PROP/FUND
    "order_ticket_opened",
    "first_order",
    "order_rejected",  # optional
    "first_trade",
    "activated",
]
# Main (non-optional, non-repeatable) path used for "steps completed".
MAIN_PATH_STEPS: list[str] = [
    "contract_signed",
    "platform_account_created",
    "first_login",
    "kyc_submitted",
    "kyc_approved",
    "bank_linked",
    "funded",
    "order_ticket_opened",
    "first_order",
    "first_trade",
    "activated",
]
STEP_LABELS: dict[str, str] = {
    "contract_signed": "Contract signed",
    "platform_account_created": "Platform account created",
    "first_login": "First login",
    "kyc_submitted": "KYC submitted",
    "kyc_info_requested": "KYC info requested",
    "kyc_approved": "KYC approved",
    "bank_linked": "Bank linked",
    "funded": "Funded",
    "api_key_created": "API key created",
    "order_ticket_opened": "Order ticket opened",
    "first_order": "First order",
    "order_rejected": "Order rejected",
    "first_trade": "First trade",
    "activated": "Activated (Active)",
}

CHANNELS: list[str] = [
    "Industry Conferences",
    "Webinars & Education",
    "Content & SEO",
    "LinkedIn Paid",
    "Partner Referrals",
    "Outbound Prospecting",
    "Liquidity Partner Intros",
]

REP_ROLES: list[str] = ["AE", "STRATEGIC", "REVOPS", "MARKETING"]
QUOTA_ROLES: frozenset[str] = frozenset({"AE", "STRATEGIC"})

ACTIVITY_KINDS: list[str] = [
    "email",
    "call",
    "meeting",
    "demo",
    "webinar",
    "linkedin",
    "triggered_email",
    "walkthrough",
    "qbr",
]
ACTIVITY_OUTCOMES: list[str] = ["none", "reply", "meeting_booked", "no_show"]
PERSONAS: list[str] = ["TRADER", "RISK", "CFO", "OPS", "EXEC"]

REGIMES: list[str] = ["scarcity", "negative_price", "winter_peak", "elevated_vol"]
REGIME_LABELS: dict[str, str] = {
    "scarcity": "Scarcity pricing",
    "negative_price": "Negative pricing",
    "winter_peak": "Winter peak",
    "elevated_vol": "Elevated volatility",
}
DRAFT_STATUSES: list[str] = ["pending_review", "approved", "queued", "sent", "rejected"]

# ---------------------------------------------------------------------------
# Activation Queue parameters (D4, CRO memo §2)
# ---------------------------------------------------------------------------
EXPECTED_ADV_PRIOR: dict[str, float] = {  # contracts/day once active
    "PROP": 400.0,
    "FUND": 150.0,
    "REP": 100.0,
    "STORAGE": 80.0,
    "IPP": 60.0,
    "UTILITY": 40.0,
    "DATACENTER": 30.0,
    "CI_LOAD": 20.0,
}
K_STAGE: dict[str, float] = {
    "TARGET": 0.10,
    "QUALIFIED": 0.15,
    "SIGNED": 0.25,  # KYC stall
    "KYC_APPROVED": 0.25,
    "FUNDED": 0.35,  # funded / no trade
    "FIRST_TRADE": 0.30,
    "ACTIVE": 0.10,
    "EXPANDING": 0.10,
    "AT_RISK": 0.20,
    "DORMANT": 0.15,
}
URGENCY_BASE: float = 1.0
URGENCY_TRIGGER: float = 1.5  # vol trigger in account's ISO within 72h, exposed segment
URGENCY_STALL: float = 1.25
URGENCY_FORECAST: float = 1.2  # forecast peak <= 5 d out
URGENCY_CAP: float = 2.0
BALANCE_WEIGHT_HEDGER: float = 1.15  # while hedger share of Active < target
TRIGGER_COOLDOWN_D: int = 14  # max 1 triggered sequence per account per 14 d
TOUCH_SUPPRESS_D: int = 5  # exclude accounts touched in last 5 days from trigger lists

# ---------------------------------------------------------------------------
# 2026 targets (CEO, spec §C)
# ---------------------------------------------------------------------------
TARGETS_2026: dict[str, object] = {
    "signed_cum": 420,
    "funded_cum": 260,
    "active_rate": 0.70,  # of funded accounts older than 20 days
    "cohort_activation_30d_start": 0.55,  # Q3 cohorts
    "cohort_activation_30d_end": 0.70,  # Q4 cohorts
    "cohort_activation_30d": 0.70,
    "median_days_funded_to_first_trade": 10,
    "adv_contracts": 25_000,
    "adv_notional_usd": 3_000_000,
    "hedger_share_active": 0.50,  # minimum
    "speculator_share_adv": (0.40, 0.65),
    "top5_adv_share": 0.45,  # maximum
    "spread_usd_mwh": {"ERCOT": 0.75, "PJM": 1.50, "CAISO": 1.50, "MISO": 1.50},  # maximum
    "uptime_pct": {"ERCOT": 95.0, "PJM": 85.0, "CAISO": 85.0, "MISO": 85.0},  # minimum
    "net_adv_retention": 1.20,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def segment_side(code: str, is_liquidity_partner: bool = False) -> str:
    """'hedger' | 'speculator' | 'liquidity_partner' for a segment code."""
    if is_liquidity_partner:
        return "liquidity_partner"
    try:
        return SEGMENTS[code]["side"]
    except KeyError as exc:  # pragma: no cover - defensive
        raise ValueError(f"unknown segment {code!r}") from exc


def segment_label(code: str) -> str:
    return SEGMENTS[code]["label"]


def hub_iso(hub: str) -> str:
    return HUB_ISO[hub]


def parse_isos(csv: str | None) -> list[str]:
    """Split an ``exposure_isos`` CSV into a clean list."""
    if not csv:
        return []
    return [p.strip() for p in str(csv).split(",") if p.strip()]


def is_trading_day(d: date | datetime) -> bool:
    """Exchange trading days are weekdays (holidays are not modelled)."""
    return d.weekday() < 5


def trading_days_back(end: date, n: int) -> list[date]:
    """The ``n`` weekdays strictly before ``end`` (oldest first)."""
    out: list[date] = []
    d = end - timedelta(days=1)
    while len(out) < n:
        if is_trading_day(d):
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def adv_window(end: date, n: int = ADV_WINDOW_TD, inclusive: bool = False) -> tuple[date, date]:
    """(first_day, last_day) of the trailing-``n``-trading-day window.

    ``inclusive=True`` treats ``end`` itself as the last day when it is a
    trading day (use for a Friday ``week_end``); otherwise the window ends the
    trading day before ``end`` (use for ``AS_OF`` Monday 00:00).
    """
    anchor = end + timedelta(days=1) if inclusive else end
    days = trading_days_back(anchor, n)
    return days[0], days[-1]


def activity_state(trading_days_30: int) -> str:
    """Health bucket from distinct trading days in the trailing 30 days."""
    if trading_days_30 >= ACTIVE_MIN_DAYS:
        return "active"
    if trading_days_30 >= AT_RISK_DAYS[0]:
        return "at_risk"
    return "dormant"


def is_active(trading_days_30: int) -> bool:
    return trading_days_30 >= ACTIVE_MIN_DAYS


def classify_stage(
    *,
    signed: bool,
    qualified: bool,
    kyc_approved: bool,
    funded: bool,
    has_traded: bool,
    trading_days_30: int,
    ever_active: bool,
    expanding: bool = False,
) -> str:
    """Single stage rule used by the seed and by any recomputation.

    * ACTIVE / EXPANDING  ⇔ ``trading_days_30 >= ACTIVE_MIN_DAYS``.
    * Funded but never traded stays ``FUNDED`` (the "funded-not-trading" stall);
      its *health* is dormant once funded >= 30 d (see :func:`activity_state`).
    * Traded, 1–3 days in trailing 30: ``FIRST_TRADE`` if never Active yet,
      else ``AT_RISK``. Traded before, 0 days in trailing 30: ``DORMANT``.
    """
    if not signed:
        return "QUALIFIED" if qualified else "TARGET"
    if not kyc_approved:
        return "SIGNED"
    if not funded:
        return "KYC_APPROVED"
    if not has_traded:
        return "FUNDED"
    if is_active(trading_days_30):
        return "EXPANDING" if expanding else "ACTIVE"
    if trading_days_30 >= AT_RISK_DAYS[0]:
        return "AT_RISK" if ever_active else "FIRST_TRADE"
    return "DORMANT"


def trigger_id_for(iso: str, hub: str, start: datetime | date) -> str:
    """Canonical trigger id, e.g. ``ERCOT-HB_HOUSTON-20260702``."""
    return f"{iso}-{hub}-{start:%Y%m%d}"


def stage_order(stage: str) -> int:
    return STAGES.index(stage)
