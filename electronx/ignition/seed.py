"""Synthetic data generator for Ignition (spec §C/§D, CTO memo §3).

Usage::

    python -m ignition.seed --reset      # drop & re-create tables, then seed
    python -m ignition.seed              # seed only if the DB is empty
    python -m ignition.seed --report     # print calibration vs targets

Design — the data embeds causal structure the product must *find*:

* A latent propensity ``z`` per account (segment + lead source + rep skill +
  size + an observable-ish quality factor ``u`` + pure noise) drives signing,
  funnel speed, drop-off, first-trade hazard and trading intensity.
  ``u`` leaks into observable proxies (other-exchange account, redlines,
  champion/stakeholders, meetings, demo, reply rate, first-login lag, API key).
* Triggered volatility outreach multiplies the funded→first-trade hazard for
  14 days (``TRIGGER_HAZARD_MULT``) and is assigned at random among exposed,
  eligible accounts, so the triggered-vs-untriggered cohort lift is causal.
* Spreads follow ``a + b/sqrt(active_accounts)`` per hub (+ noise, + widening
  on event days).
* Friction: KYC info-request loops (UTILITY, CI_LOAD), slow bank→funded
  (DATACENTER), slow funded→first order for hedgers without a walkthrough,
  frequent order rejections (FUND).
* Seeded demo event: ERCOT HB_HOUSTON (peak $4,800) + HB_NORTH from
  2026-10-02 15:00, mild CAISO SP15 negatives on the last weekend, ERCOT
  forecast peak on 2026-10-07.

All draws come from ``numpy.random.default_rng(SEED)``; ``AS_OF`` is fixed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from . import definitions as D
from .config import SEED
from .database import Base, create_all
from .models import (
    Account,
    Activity,
    Contact,
    MarketingSpend,
    MarketPrice,
    OnboardingEvent,
    PriceForecast,
    Rep,
    SpreadSnapshot,
    Trade,
    VolatilityEvent,
)
from .services import volatility as vol

# ---------------------------------------------------------------------------
# Tunable generator parameters
# ---------------------------------------------------------------------------
N_ACCOUNTS = 600
N_SIGNED = 332  # incl. liquidity partners
N_LP = 12
SEGMENT_COUNTS = {
    "CI_LOAD": 120,
    "IPP": 90,
    "REP": 72,
    "UTILITY": 72,
    "STORAGE": 60,
    "DATACENTER": 48,
    "PROP": 72,
    "FUND": 66,
}
SEG_EFFECT = {
    "PROP": 1.1,
    "FUND": 0.7,
    "STORAGE": 0.55,
    "REP": 0.35,
    "IPP": 0.05,
    "DATACENTER": -0.15,
    "CI_LOAD": -0.45,
    "UTILITY": -0.55,
}
LEAD_EFFECT = {
    "Partner Referrals": 0.55,
    "Liquidity Partner Intros": 0.35,
    "Industry Conferences": 0.15,
    "Webinars & Education": 0.15,
    "Content & SEO": 0.0,
    "Outbound Prospecting": -0.10,
    "LinkedIn Paid": -0.45,
}
STALL_MULT = 2.3  # scales every onboarding stall probability
WALKTHROUGH_MULT = 3.2  # hedger funded->first-order hazard after a live walkthrough
REVIVE_P = 0.6  # stalled onboarding resumes after a long pause
TRIGGER_PROB = 0.6  # share of eligible exposed accounts an AE sequenced
TRIGGER_HAZARD_MULT = 3.6
NATURAL_EVENT_MULT = 1.2
SIZE_SCALE = 1.0
TENOR_CONTRACT_SCALE = {"DAILY_PEAK": 0.12, "WEEKLY_PEAK": 0.03}  # fewer, larger-MWh contracts
LP_DAILY = [3200, 1850, 700, 400, 280, 220, 180, 140, 115, 95, 80, 65]

ISO_MIX = {
    "STORAGE": {"ERCOT": 0.6, "CAISO": 0.25, "PJM": 0.1, "MISO": 0.05},
    "DATACENTER": {"ERCOT": 0.45, "PJM": 0.35, "MISO": 0.1, "CAISO": 0.1},
    "REP": {"ERCOT": 0.62, "PJM": 0.28, "MISO": 0.05, "CAISO": 0.05},
    "UTILITY": {"PJM": 0.35, "MISO": 0.4, "ERCOT": 0.15, "CAISO": 0.1},
    "IPP": {"CAISO": 0.35, "ERCOT": 0.35, "PJM": 0.15, "MISO": 0.15},
    "CI_LOAD": {"ERCOT": 0.3, "PJM": 0.35, "MISO": 0.2, "CAISO": 0.15},
    "PROP": {"ERCOT": 0.5, "PJM": 0.3, "CAISO": 0.1, "MISO": 0.1},
    "FUND": {"ERCOT": 0.45, "PJM": 0.3, "CAISO": 0.15, "MISO": 0.1},
}
HUB_MIX = {
    "ERCOT": {"HB_NORTH": 0.45, "HB_HOUSTON": 0.35, "HB_WEST": 0.20},
    "PJM": {"PJM_WESTERN_HUB": 1.0},
    "CAISO": {"SP15": 0.6, "NP15": 0.4},
    "MISO": {"MISO_INDIANA_HUB": 1.0},
}
STATES = {
    "ERCOT": ["TX"],
    "PJM": ["PA", "NJ", "MD", "VA", "OH", "IL", "DE"],
    "CAISO": ["CA"],
    "MISO": ["IN", "MI", "MN", "IL", "LA", "IA", "WI"],
}
FIN_STATES = ["NY", "IL", "CT", "TX", "NY", "IL"]
SIZE_MEDIAN_MW = {
    "CI_LOAD": 25,
    "IPP": 200,
    "REP": 400,
    "UTILITY": 800,
    "STORAGE": 100,
    "DATACENTER": 150,
    "PROP": 120,
    "FUND": 150,
}
LOAD_FACTOR = {
    "CI_LOAD": 0.7,
    "IPP": 0.3,
    "REP": 0.55,
    "UTILITY": 0.55,
    "STORAGE": 0.12,
    "DATACENTER": 0.85,
    "PROP": 0.5,
    "FUND": 0.5,
}
DAILY_SIZE_MIN = {  # contracts per trading day scale (×(1+Lomax(1.6)))
    "PROP": 150,
    "FUND": 75,
    "REP": 60,
    "STORAGE": 45,
    "IPP": 38,
    "UTILITY": 28,
    "DATACENTER": 20,
    "CI_LOAD": 14,
}
KYC_LOOP_LAMBDA = {
    "UTILITY": 1.5,
    "CI_LOAD": 1.3,
    "DATACENTER": 0.6,
    "FUND": 0.6,
    "IPP": 0.5,
    "REP": 0.5,
    "STORAGE": 0.4,
    "PROP": 0.3,
}
KYC_LOOP_DROP = {"UTILITY": 0.15, "CI_LOAD": 0.13}
REDLINE_LAMBDA = {"UTILITY": 3.0, "CI_LOAD": 2.0, "DATACENTER": 2.0, "PROP": 0.8, "FUND": 0.8}
REJECT_PROB = {"FUND": 0.45, "PROP": 0.12}

REPS = [
    # id, name, role, region, quota_funded_annual, quota_adv, start_date, skill
    (1, "Maya Castillo", "AE", "ERCOT", 24, 2500.0, date(2025, 9, 15), 0.20),
    (2, "Ben Okafor", "AE", "PJM", 24, 2500.0, date(2025, 10, 1), 0.00),
    (3, "Priya Raman", "AE", "CAISO", 24, 2000.0, date(2025, 10, 15), 0.10),
    (4, "Tom Lindqvist", "AE", "MISO", 24, 2000.0, date(2026, 3, 2), -0.15),
    (5, "Dana Whitfield", "STRATEGIC", "National", 18, 6000.0, date(2025, 9, 1), 0.15),
    (6, "Luis Moreno", "REVOPS", "National", 0, 0.0, date(2025, 10, 1), 0.0),
    (7, "Hannah Cho", "REVOPS", "National", 0, 0.0, date(2026, 2, 2), 0.0),
    (8, "Grace Adeyemi", "MARKETING", "National", 0, 0.0, date(2025, 9, 1), 0.0),
]
AE_BY_ISO = {"ERCOT": 1, "PJM": 2, "CAISO": 3, "MISO": 4}
STRATEGIC_ID = 5
REVOPS_IDS = (6, 7)
MARKETING_ID = 8

# Injected historical events: (iso, hub, start, [hourly prices])
INJECTED_EVENTS = [
    ("PJM", "PJM_WESTERN_HUB", datetime(2026, 1, 26, 12), "cold"),
    ("MISO", "MISO_INDIANA_HUB", datetime(2026, 1, 27, 12), "cold"),
    ("ERCOT", "HB_NORTH", datetime(2026, 2, 16, 12), [1250, 1900, 2400, 1700, 1150]),
    ("ERCOT", "HB_HOUSTON", datetime(2026, 2, 16, 13), [1100, 1500, 1350]),
    ("CAISO", "SP15", datetime(2026, 4, 11, 16), "neg"),
    ("CAISO", "NP15", datetime(2026, 4, 11, 16), "neg"),
    ("CAISO", "SP15", datetime(2026, 5, 2, 16), "neg"),
    ("ERCOT", "HB_NORTH", datetime(2026, 5, 12, 21), [1100, 1650, 2050, 1300]),
    ("ERCOT", "HB_HOUSTON", datetime(2026, 6, 1, 20), [1150, 1900, 2350, 1500]),
    ("ERCOT", "HB_WEST", datetime(2026, 6, 17, 21), [1200, 2100, 2600, 1500]),
    ("PJM", "PJM_WESTERN_HUB", datetime(2026, 6, 24, 19), [280, 420, 560, 360]),
    ("MISO", "MISO_INDIANA_HUB", datetime(2026, 7, 15, 20), [270, 390, 470, 300]),
    ("ERCOT", "HB_WEST", datetime(2026, 7, 20, 21), [1100, 1750, 2200, 1250]),
    ("ERCOT", "HB_NORTH", datetime(2026, 8, 5, 21), [1250, 1900, 2500, 1600]),
    ("PJM", "PJM_WESTERN_HUB", datetime(2026, 8, 12, 19), [300, 470, 610, 380]),
    ("ERCOT", "HB_HOUSTON", datetime(2026, 9, 3, 21), [1200, 2050, 2800, 1700]),
    ("CAISO", "SP15", datetime(2026, 9, 8, 1), [300, 560, 820, 390]),
    ("ERCOT", "HB_NORTH", datetime(2026, 9, 17, 21), [1150, 1700, 2100, 1250]),
    ("ERCOT", "HB_HOUSTON", datetime(2026, 7, 2, 21), [1500, 2400, 3300, 3900, 2800, 1700]),
    ("ERCOT", "HB_NORTH", datetime(2026, 7, 2, 22), [1150, 1800, 1300]),
    ("PJM", "PJM_WESTERN_HUB", datetime(2026, 7, 21, 19), [310, 480, 650, 520]),
    ("ERCOT", "HB_NORTH", datetime(2026, 8, 18, 21), [1300, 2200, 3200, 2500, 1400]),
    ("ERCOT", "HB_HOUSTON", datetime(2026, 8, 18, 21), [1200, 1900, 2700, 1600]),
    ("CAISO", "SP15", datetime(2026, 8, 26, 1), [290, 640, 900, 410]),
    ("CAISO", "NP15", datetime(2026, 8, 26, 1), [270, 520, 760]),
    ("MISO", "MISO_INDIANA_HUB", datetime(2026, 9, 9, 20), [280, 450, 520, 330]),
    # Demo event (spec §D): HB_HOUSTON strongest, HB_NORTH, sympathetic HB_WEST.
    ("ERCOT", "HB_HOUSTON", datetime(2026, 10, 2, 15), [2200, 2900, 3600, 4300, 4800, 4500, 3900, 3100, 2400]),
    ("ERCOT", "HB_NORTH", datetime(2026, 10, 2, 15), [2200, 2600, 3100, 3500, 3300, 2800, 2300]),
    ("ERCOT", "HB_WEST", datetime(2026, 10, 2, 16), [180, 260, 340, 410, 380, 300, 220]),
]
DEMO_EVENT_START = datetime(2026, 10, 2, 15)

# ---------------------------------------------------------------------------
# Names (fictional)
# ---------------------------------------------------------------------------
PREFIXES = """Lone Star|Mesa Grande|Kestrel|Red Mesa|Cedar Ridge|Juniper|Granite Peak|Ironwood|Prairie Wind|
Caddo Bend|Palo Verde Flats|Sandhill|Cottonwood|Gulf Breeze|Big Thicket|Allegheny Ridge|Laurel Highlands|
Keystone Valley|Ohio Bend|Wabash Crossing|Hoosier Prairie|North Woods|Driftless|Delta Bayou|Sierra Vista|Mojave Sun|
Tehachapi Pass|Central Valley|Redwood Coast|Sequoia Grove|Owens Lake|Pacific Crest|Sonoran|Harbor Point|Clearwater|
Silver Creek|Copper Canyon|Eagle Pass|Falcon Ridge|Heron Bay|Osprey Point|Willow Creek|Aspen Grove|Birchwood|
Stonebridge|Riverbend|High Plains|Windmill Flats|Thunder Basin|Starlight|Bright Plains|Meridian Point|Polaris|
Vantage Peak|Halcyon|Cardinal Rock|Merlin|Peregrine|Harrier|Goshawk|Sparrowhawk|Corvid|Ibis|Albatross|Tern Island|
Plover|Avocet|Larkspur|Foxglove|Yarrow|Sagebrush|Mesquite Draw|Agave|Ocotillo|Tamarack|Hemlock Hollow|Basswood|
Ridgeline|Tidewater|Piedmont Run|Cumberland Gap|Ozark Hollow|Black Prairie|Flint Hills|Smoky Hill|Blackland|
Hill Country|Big Bend|Permian Sky|Panhandle Wind|Coastal Bend|Bluewater|Blue Heron|Quarry Hill|Oxbow|Saltgrass|
Lantern Bay|Bramble|Thistle|Cinder Cone|Basalt|Obsidian|Quartzite|Feldspar|Garnet Ridge|Jasper Flats|Onyx|
Topaz Valley|Beryl|Halite|Gypsum Hills|Caliche|Dry Creek|Rattlesnake Butte|Coyote Wells|Pronghorn|Bison Ridge|
Elk Meadow|Moose Lake|Loon Harbor|Pike Rapids|Walleye|Trillium|Bloodroot|Prairie Smoke|Bluestem|Switchgrass|
Little Bluestem|Indiangrass|Buffalo Grass|Gamagrass|Wildrye|Sideoats|Mulberry|Pecan Hollow|Persimmon|Pawpaw|
Sassafras|Hackberry|Catalpa|Sweetgum|Tupelo|Bald Cypress|Live Oak|Post Oak|Blackjack|Shinnery|Chinquapin|
Kingfisher|Nighthawk|Whippoorwill|Bobwhite|Meadowlark|Dickcissel|Bunting|Tanager|Grosbeak|Vireo|Warbler|
Thrasher|Roadrunner|Caracara|Kite Field|Shrike|Phoebe|Killdeer|Sandpiper|Curlew|Godwit|Dunlin|Sanderling|
Turnstone|Skimmer|Anhinga|Spoonbill|Egret|Night Heron|Bittern|Rail Marsh|Gallinule|Coot Lake|Grebe|Merganser|
Goldeneye|Bufflehead|Canvasback|Redhead|Scaup|Teal Pond|Wigeon|Gadwall|Pintail|Shoveler|Brant|Snow Goose""".replace(
    "\n", ""
).split("|")
SUFFIXES = {
    "REP": ["Retail Power", "Energy Services", "Retail Electric", "Home Energy", "Power Retail", "Electric Supply"],
    "IPP": ["Solar", "Wind Partners", "Renewables", "Power Partners", "Generation", "Clean Power", "Solar Farms"],
    "STORAGE": ["Energy Storage", "Battery Partners", "Storage Holdings", "Grid Storage", "Battery Works"],
    "CI_LOAD": ["Manufacturing", "Steel Works", "Chemicals", "Cold Storage", "Industrial Gases", "Paper Mills",
                "Foods", "Plastics", "Logistics", "Cement", "Glassworks", "Aluminum"],
    "UTILITY": ["Electric Cooperative", "Municipal Utility", "Public Power District", "Power Co-op", "Light & Water"],
    "DATACENTER": ["Data Centers", "Digital Campus", "Compute Parks", "Cloud Infrastructure", "Hyperscale Sites"],
    "PROP": ["Trading", "Trading Group", "Quant Trading", "Proprietary Trading", "Markets"],
    "FUND": ["Capital", "Asset Management", "Partners", "Investment Management", "Commodities Fund"],
}
LP_NAMES = [
    "Kestrel Capital Markets", "Northgate Liquidity", "Bramblewood Market Making", "Ironbark Trading",
    "Silverline Quant", "Tamarind Markets", "Corvid Liquidity Partners", "Saltmarsh Capital Markets",
    "Halyard Trading", "Larchmont Quantitative", "Basswood Liquidity", "Driftwood Market Making",
]
FIRST_NAMES = """James|Maria|Robert|Linda|Michael|Sofia|David|Elena|Daniel|Grace|Kevin|Aisha|Brian|Mei|Jason|Fatima|
Ryan|Olivia|Eric|Hannah|Andrew|Chloe|Marcus|Nadia|Carlos|Ingrid|Victor|Leah|Samuel|Rosa|Patrick|Yuki|Derek|Amara|
Trevor|Lucia|Graham|Priyanka|Owen|Camila|Nathan|Sasha|Felix|Tessa|Rahul|Bianca|Colin|Zara|Adrian|Mira|Wesley|
Imani|Gavin|Noor|Elliot|Paloma|Hugo|Selena|Reid|Anika""".replace("\n", "").split("|")
LAST_NAMES = """Alvarez|Bennett|Chen|Delgado|Ellison|Fischer|Garza|Hughes|Ibarra|Jensen|Kowalski|Lindgren|Mendez|
Nakamura|Ortiz|Patel|Quinlan|Rasmussen|Sandoval|Thornton|Underwood|Vasquez|Whitaker|Xiong|Yates|Zamora|Abernathy|
Brennan|Castellanos|Donnelly|Esposito|Fairbanks|Gallagher|Hollis|Iverson|Jaramillo|Kendrick|Lockhart|Morales|
Novak|Oyelaran|Prescott|Ramirez|Sterling|Tanaka|Ulrich|Valdez|Winslow|Yoon|Zeller|Ashford|Beaumont|Calloway|
Dunmore|Everly|Fontaine|Greer|Holloway|Kincaid|Langford|Mercer|Navarro|Pemberton|Rourke|Sato|Tremblay|Voss|
Whitmore|Okonkwo|Banerjee|Haddad|Kovacs|Lindqvist|Moreau|Petrov|Rivera""".replace("\n", "").split("|")
TITLES = {
    "TRADER": ["Head of Trading", "Senior Power Trader", "Portfolio Manager", "Trader, Power & Gas", "Director of Trading"],
    "RISK": ["Chief Risk Officer", "Director of Risk", "Risk Manager", "VP Energy Risk", "Head of Hedging"],
    "CFO": ["CFO", "Treasurer", "VP Finance", "Controller"],
    "OPS": ["Director of Energy Procurement", "Asset Manager", "VP Operations", "Energy Manager", "Plant Director"],
    "EXEC": ["CEO", "President", "COO", "General Manager"],
}
PERSONA_W = {
    "speculator": {"TRADER": 0.45, "RISK": 0.2, "CFO": 0.1, "OPS": 0.1, "EXEC": 0.15},
    "hedger": {"TRADER": 0.12, "RISK": 0.25, "CFO": 0.25, "OPS": 0.25, "EXEC": 0.13},
}
CAMPAIGNS = {
    "Industry Conferences": ["Gulf Coast Power Summit booth", "Grid Markets Week sponsorship", "Energy Risk Forum panel",
                             "Storage & Flexibility Expo booth", "Texas Power Markets Conference"],
    "Webinars & Education": ["Hedging 101 for REPs", "Scarcity Pricing Explained", "Short-Dated Hedges Workshop",
                             "Storage Revenue Stacking Webinar", "Data Center Power Risk Clinic"],
    "Content & SEO": ["Hub price explainer series", "Weekly market wrap", "Contract spec guides", "Volatility atlas"],
    "LinkedIn Paid": ["Sponsored content — hedging", "Lead-gen form — ERCOT", "Retargeting — webinar viewers",
                      "Conversation ads — CFOs"],
    "Partner Referrals": ["FCM referral program", "Energy-advisor referral fees", "Broker introducer program"],
    "Outbound Prospecting": ["SDR sequences — C&I", "Intent-data list — utilities", "Account-based outreach — IPPs"],
    "Liquidity Partner Intros": ["Market-maker program intros", "Prime-broker introductions"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def _choice(rng: np.random.Generator, mapping: dict[str, float]) -> str:
    keys = list(mapping)
    w = np.array([mapping[k] for k in keys], dtype=float)
    return keys[int(rng.choice(len(keys), p=w / w.sum()))]


def _biz(rng: np.random.Generator, dt: datetime, lo: int = 13, hi: int = 22) -> datetime:
    """Move ``dt`` to a weekday business hour (UTC) on/after its date."""
    d = dt.date()
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return datetime(d.year, d.month, d.day, int(rng.integers(lo, hi)), int(rng.integers(0, 60)))


def _weekday_after(d: date) -> date:
    d = d + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _progress(t: datetime | date) -> float:
    if isinstance(t, date) and not isinstance(t, datetime):
        t = datetime(t.year, t.month, t.day)
    span = (D.AS_OF - D.HISTORY_START).total_seconds()
    return float(min(1.0, max(0.0, (t - D.HISTORY_START).total_seconds() / span)))


# ---------------------------------------------------------------------------
# Prices & forecasts
# ---------------------------------------------------------------------------
ISO_LEVEL = {"ERCOT": 31.0, "PJM": 41.0, "CAISO": 44.0, "MISO": 33.0}
HUB_BASIS = {
    "HB_NORTH": 1.0,
    "HB_HOUSTON": 1.04,
    "HB_WEST": 0.90,
    "PJM_WESTERN_HUB": 1.0,
    "SP15": 1.0,
    "NP15": 1.03,
    "MISO_INDIANA_HUB": 1.0,
}


def _ar1(rng, n, phi, sigma):
    e = rng.normal(0.0, sigma, n)
    out = np.empty(n)
    acc = 0.0
    for i in range(n):
        acc = phi * acc + e[i]
        out[i] = acc
    return out


def gen_prices(rng: np.random.Generator) -> pd.DataFrame:
    hours = pd.date_range(D.HISTORY_START, D.AS_OF - timedelta(hours=1), freq="h")
    n = len(hours)
    doy = hours.dayofyear.to_numpy().astype(float)
    utc_h = hours.hour.to_numpy()
    dow = hours.dayofweek.to_numpy()
    days = (hours.normalize() - pd.Timestamp(D.HISTORY_START)).days.to_numpy()
    n_days = int(days.max()) + 1
    frames = []
    for iso, hubs in D.ISOS.items():
        lh = (utc_h + D.ISO_UTC_OFFSET_H[iso]) % 24
        summer = np.exp(-(((doy - 205) / 38) ** 2))
        winter = np.exp(-(((doy - 22) / 22) ** 2))
        if iso == "ERCOT":
            season = 1 + 0.55 * summer + 0.15 * winter
            shape = 0.72 + 0.62 * np.exp(-(((lh - 18) / 3.0) ** 2)) + 0.10 * np.exp(-(((lh - 8) / 2.0) ** 2))
        elif iso in ("PJM", "MISO"):
            season = 1 + 0.40 * summer + 0.45 * winter
            w = winter / (winter + summer + 1e-9)
            win_shape = 0.75 + 0.35 * np.exp(-(((lh - 8) / 1.8) ** 2)) + 0.42 * np.exp(-(((lh - 19) / 2.0) ** 2))
            sum_shape = 0.72 + 0.55 * np.exp(-(((lh - 17) / 3.0) ** 2))
            shape = w * win_shape + (1 - w) * sum_shape
        else:  # CAISO duck curve
            solar = 0.35 + 0.45 * np.exp(-(((doy - 125) / 50) ** 2))
            season = 1 + 0.25 * summer
            shape = 1.0 - solar * np.exp(-(((lh - 12.5) / 2.6) ** 2)) + 0.65 * np.exp(-(((lh - 19.5) / 1.6) ** 2))
        weekend = np.where(dow >= 5, 0.88, 1.0)
        e_iso = _ar1(rng, n, 0.9, 0.075)
        e_day = _ar1(rng, n_days, 0.7, 0.10)[days]
        # ISO-level random summer scarcity hours (ERCOT) — single-hour spikes.
        iso_spike = np.zeros(n)
        if iso == "ERCOT":
            ok = (doy >= 152) & (doy <= 262) & (lh >= 17) & (lh <= 19)
            draw = rng.random(n) < 0.012
            iso_spike = np.where(ok & draw, rng.uniform(1000, 2600, n), 0.0)
        caiso_neg = np.zeros(n, dtype=bool)
        if iso == "CAISO":
            spring = np.exp(-(((doy - 110) / 28) ** 2))
            caiso_neg = ((lh >= 10) & (lh <= 15)) & (rng.random(n) < 0.17 * spring)
        for hub in hubs:
            e_hub = 0.85 * e_iso + 0.53 * _ar1(rng, n, 0.8, 0.05)
            lmp = ISO_LEVEL[iso] * HUB_BASIS[hub] * season * shape * weekend * np.exp(e_hub + e_day)
            lmp = np.where(iso_spike > 0, iso_spike * HUB_BASIS[hub] * rng.uniform(0.85, 1.1, n), lmp)
            neg_here = caiso_neg & (rng.random(n) < 0.85)
            lmp = np.where(neg_here, -rng.uniform(1, 25, n), lmp)
            frames.append(pd.DataFrame({"hub": hub, "ts": hours, "iso": iso, "lmp": lmp}))
    prices = pd.concat(frames, ignore_index=True)
    prices = _inject_events(rng, prices)
    prices["lmp"] = prices["lmp"].round(2)
    return prices


def _inject_events(rng: np.random.Generator, prices: pd.DataFrame) -> pd.DataFrame:
    idx = {hub: g.index.to_numpy() for hub, g in prices.groupby("hub")}
    t0 = pd.Timestamp(D.HISTORY_START)
    lmp = prices["lmp"].to_numpy().copy()
    hubs_all = list(idx)

    def pos(hub, ts):
        return idx[hub][int((pd.Timestamp(ts) - t0) / pd.Timedelta(hours=1))]

    # No random spikes in the final 10 days except the injected ones.
    for hub in hubs_all:
        tail = idx[hub][-240:]
        cap = 600.0 if D.HUB_ISO[hub] == "ERCOT" else 220.0
        lmp[tail] = np.minimum(lmp[tail], cap)
    for iso, hub, start, spec in INJECTED_EVENTS:
        if spec == "cold":  # 3-day cold snap: morning + evening peaks
            for day in range(3):
                for h, lo, hi in ((12, 300, 520), (13, 380, 620), (14, 300, 480), (22, 320, 560), (23, 420, 850), (0, 330, 600)):
                    ts = datetime(start.year, start.month, start.day) + timedelta(days=day + (1 if h == 0 else 0), hours=h)
                    lmp[pos(hub, ts)] = rng.uniform(lo, hi)
        elif spec == "neg":  # weekend of deep midday negatives (local 9-16 → UTC 16-23)
            for day in range(2):
                for h in range(8):
                    ts = start + timedelta(days=day, hours=h)
                    lmp[pos(hub, ts)] = -rng.uniform(8, 45)
        else:
            for k, p in enumerate(spec):
                lmp[pos(hub, start + timedelta(hours=k))] = float(p)
    # Mild CAISO negatives on the last weekend: SP15 7h/day (fires), NP15 4h/day.
    for d in (date(2026, 10, 3), date(2026, 10, 4)):
        for h in range(17, 24):
            lmp[pos("SP15", datetime(d.year, d.month, d.day, h))] = -rng.uniform(3, 18)
        for h in range(18, 22):
            lmp[pos("NP15", datetime(d.year, d.month, d.day, h))] = -rng.uniform(1, 9)
    prices["lmp"] = lmp
    return prices


def gen_forecasts(rng: np.random.Generator, prices: pd.DataFrame) -> list[dict]:
    issued = D.AS_OF - timedelta(hours=6)
    fixed = {
        "HB_HOUSTON": [185, 420, 1650, 960, 215],
        "HB_NORTH": [160, 380, 1320, 840, 190],
        "HB_WEST": [120, 230, 610, 450, 140],
    }
    rows = []
    recent = prices[prices["ts"] >= pd.Timestamp(D.AS_OF - timedelta(days=14))]
    for hub in D.HUBS:
        iso = D.HUB_ISO[hub]
        r = recent[recent["hub"] == hub]["lmp"]
        base_peak = float(r.quantile(0.95))
        base_avg = float(r.clip(lower=0).mean())
        for k in range(D.FORECAST_DAYS):
            day = D.AS_OF_DATE + timedelta(days=k)
            if hub in fixed:
                peak = float(fixed[hub][k])
                avg = round(min(peak * 0.28, base_avg * (1.1 + 0.5 * (peak > 1000))), 2)
            else:
                peak = round(base_peak * rng.uniform(0.85, 1.2), 2)
                avg = round(base_avg * rng.uniform(0.9, 1.1), 2)
            rows.append({"hub": hub, "iso": iso, "date": day, "forecast_peak_lmp": round(peak, 2),
                         "forecast_avg_lmp": round(avg, 2), "issued_at": issued})
    return rows


# ---------------------------------------------------------------------------
# Accounts (static)
# ---------------------------------------------------------------------------
@dataclass
class Acct:
    id: int
    name: str
    segment: str
    side: str
    is_lp: bool
    primary_iso: str
    exposure_isos: list
    hub: str
    hq_state: str
    size_mw: float
    est_annual_mwh: float
    tam_tier: str
    lead_source: str
    rep_id: int | None
    has_other_exchange: bool
    kyc_redlines: int
    u: float
    u_obs: float
    z: float
    p: float
    created_at: datetime | None = None
    signed: bool = False
    signed_at: datetime | None = None
    qualified: bool = False


def gen_accounts(rng: np.random.Generator) -> list[Acct]:
    segs = [s for s, n in SEGMENT_COUNTS.items() for _ in range(n)]
    rng.shuffle(segs)
    prop_idx = [i for i, s in enumerate(segs) if s == "PROP"]
    fund_idx = [i for i, s in enumerate(segs) if s == "FUND"]
    lp_set = set(prop_idx[:10]) | set(fund_idx[:2])
    used_names: set[str] = set()
    lp_names = iter(LP_NAMES)
    prefixes = list(PREFIXES)
    out: list[Acct] = []
    # size ranks for tam tier
    sizes = {}
    for i, seg in enumerate(segs):
        sizes[i] = float(SIZE_MEDIAN_MW[seg] * np.exp(rng.normal(0, 0.8)))
    by_seg = defaultdict(list)
    for i, seg in enumerate(segs):
        by_seg[seg].append(sizes[i])
    q80 = {s: np.quantile(v, 0.8) for s, v in by_seg.items()}
    q40 = {s: np.quantile(v, 0.4) for s, v in by_seg.items()}
    for i, seg in enumerate(segs):
        is_lp = i in lp_set
        side = D.segment_side(seg, is_lp)
        if is_lp:
            name = next(lp_names)
        else:
            for _ in range(200):
                name = f"{prefixes[int(rng.integers(len(prefixes)))]} {SUFFIXES[seg][int(rng.integers(len(SUFFIXES[seg])))]}"
                if name not in used_names:
                    break
        used_names.add(name)
        iso = _choice(rng, ISO_MIX[seg])
        hub = _choice(rng, HUB_MIX[iso])
        exp_isos = [iso]
        multi_p = 0.85 if is_lp else (0.55 if side == "speculator" else 0.18)
        for other in D.ISO_CODES:
            if other != iso and rng.random() < multi_p * (0.6 if other != "ERCOT" else 0.9):
                exp_isos.append(other)
        if is_lp:
            exp_isos = list(D.ISO_CODES) if rng.random() < 0.6 else exp_isos
        state = (FIN_STATES[int(rng.integers(len(FIN_STATES)))] if side != "hedger" and rng.random() < 0.6
                 else STATES[iso][int(rng.integers(len(STATES[iso])))])
        if is_lp:
            lead = "Liquidity Partner Intros" if rng.random() < 0.85 else "Partner Referrals"
        elif side == "speculator":
            lead = _choice(rng, {"Industry Conferences": 0.15, "Webinars & Education": 0.08, "Content & SEO": 0.08,
                                 "LinkedIn Paid": 0.12, "Partner Referrals": 0.17, "Outbound Prospecting": 0.25,
                                 "Liquidity Partner Intros": 0.15})
        else:
            lead = _choice(rng, {"Industry Conferences": 0.18, "Webinars & Education": 0.14, "Content & SEO": 0.12,
                                 "LinkedIn Paid": 0.16, "Partner Referrals": 0.10, "Outbound Prospecting": 0.30})
        size = sizes[i] * (1.5 if lead == "Industry Conferences" else 1.0)
        tier = "A" if size >= q80[seg] else ("B" if size >= q40[seg] else "C")
        if side != "hedger" or (tier == "A" and rng.random() < 0.25):
            rep_id = STRATEGIC_ID if rng.random() < 0.75 else AE_BY_ISO[iso]
        else:
            rep_id = AE_BY_ISO[iso]
        skill = next(r[7] for r in REPS if r[0] == rep_id)
        u = float(rng.normal())
        u_obs = u + float(rng.normal(0, 0.8))  # what proxies (engagement, contacts) actually reflect
        other_p = _sigmoid((0.6 if side != "hedger" else -1.2) + 0.9 * u)
        has_other = bool(rng.random() < other_p) or is_lp
        redlines = int(rng.poisson(REDLINE_LAMBDA.get(seg, 1.0) * math.exp(-0.45 * u)))
        log_size_std = (math.log(size) - math.log(SIZE_MEDIAN_MW[seg])) / 0.8
        z = SEG_EFFECT[seg] + LEAD_EFFECT[lead] + skill + 0.25 * log_size_std + 0.75 * u + 0.55 * float(rng.normal())
        if is_lp:
            z += 2.0
        p = float(_sigmoid(z - 0.1))
        out.append(
            Acct(
                id=i + 1, name=name, segment=seg, side=side, is_lp=is_lp, primary_iso=iso, exposure_isos=exp_isos,
                hub=hub, hq_state=state, size_mw=round(size, 1),
                est_annual_mwh=round(size * 8760 * LOAD_FACTOR[seg] * rng.uniform(0.8, 1.2), 0),
                tam_tier=tier, lead_source=lead, rep_id=rep_id, has_other_exchange=has_other,
                kyc_redlines=redlines, u=u, u_obs=u_obs, z=z, p=p,
            )
        )
    return out


def assign_signing(rng: np.random.Generator, accts: list[Acct]) -> None:
    lps = [a for a in accts if a.is_lp]
    others = [a for a in accts if not a.is_lp]
    w = np.array([math.exp(1.1 * a.z) for a in others])
    chosen = rng.choice(len(others), size=N_SIGNED - len(lps), replace=False, p=w / w.sum())
    chosen_set = set(int(c) for c in chosen)
    lo, hi = datetime(2025, 11, 10), datetime(2026, 10, 2)
    span = (hi - lo).total_seconds()
    for a in lps:
        a.signed = True
        a.signed_at = _biz(rng, datetime(2025, 11, 3) + timedelta(days=float(rng.uniform(0, 45))))
    for k, a in enumerate(others):
        if k in chosen_set:
            a.signed = True
            x = float(rng.random())
            # inverse CDF of density ∝ 0.45 + x on [0, 1] (ramping signings)
            frac = (-0.45 + math.sqrt(0.45**2 + 2 * x * 0.95)) / 1.0
            a.signed_at = _biz(rng, lo + timedelta(seconds=frac * span))
    for a in accts:
        if a.signed:
            a.created_at = _biz(rng, a.signed_at - timedelta(days=max(7.0, float(rng.gamma(2.0, 24.0)))))
            a.qualified = True
        else:
            a.created_at = _biz(rng, datetime(2025, 9, 1) + timedelta(days=float(rng.uniform(0, 385))))
            a.qualified = bool(rng.random() < 0.15 + 0.55 * a.p)
            if not a.qualified and rng.random() < 0.45:
                a.rep_id = None


# ---------------------------------------------------------------------------
# Lifecycle simulation
# ---------------------------------------------------------------------------
class World:
    """Holds generated rows and shared lookups during the simulation."""

    def __init__(self, rng, prices: pd.DataFrame, events: list[dict], seed: int = SEED):
        self.rng = rng
        self.seed = seed
        self.events = events
        self.onboarding: list[dict] = []
        self.activities: list[dict] = []
        self.trades: list[dict] = []
        # price lookups
        t0 = pd.Timestamp(D.HISTORY_START)
        self.t0 = t0
        self.hub_lmp = {h: g.sort_values("ts")["lmp"].to_numpy() for h, g in prices.groupby("hub")}
        day_peak = {}
        for h, g in prices.groupby("hub"):
            arr = g.sort_values("ts")["lmp"].to_numpy()
            nd = len(arr) // 24
            m = arr[: nd * 24].reshape(nd, 24)
            day_peak[h] = np.clip(np.mean(np.sort(m, axis=1)[:, 8:], axis=1), 5.0, None)
        self.day_peak = day_peak
        # event lookups per ISO day
        self.event_days: dict[str, set[date]] = defaultdict(set)
        by_isoday: dict[tuple[str, date], list[dict]] = defaultdict(list)
        for e in events:
            for k in range(0, 4):
                self.event_days[e["iso"]].add(e["start_ts"].date() + timedelta(days=k))
            by_isoday[(e["iso"], e["start_ts"].date())].append(e)
        self.trigger_groups = sorted(
            ((k, sorted(v, key=lambda e: -e["severity"])) for k, v in by_isoday.items()), key=lambda kv: kv[0][1]
        )

    def lmp_at(self, hub: str, ts: datetime) -> float:
        i = int((pd.Timestamp(ts).floor("h") - self.t0) / pd.Timedelta(hours=1))
        arr = self.hub_lmp[hub]
        return float(arr[min(max(i, 0), len(arr) - 1)])

    def peak_at(self, hub: str, d: date) -> float:
        i = (d - D.HISTORY_START.date()).days
        arr = self.day_peak[hub]
        return float(arr[min(max(i, 0), len(arr) - 1)])

    def ev(self, a: Acct, step: str, ts: datetime):
        self.onboarding.append({"account_id": a.id, "ts": ts, "step": step})

    def act(self, a: Acct, rep_id, ts: datetime, kind: str, outcome: str = "none", trigger_id=None, sequence=None):
        if ts < a.created_at:
            ts = a.created_at + timedelta(minutes=30)
        if ts >= D.AS_OF:
            return
        self.activities.append({"account_id": a.id, "rep_id": rep_id, "ts": ts, "kind": kind, "outcome": outcome,
                                "trigger_id": trigger_id, "sequence": sequence})


def _reply(rng, p, base=0.08, slope=0.38):
    return "reply" if rng.random() < base + slope * p else "none"


def presign_activities(w: World, a: Acct) -> None:
    rng = w.rng
    end = a.signed_at if a.signed else D.AS_OF
    start = a.created_at
    span = max((end - start).total_seconds(), 3600.0)
    q = float(_sigmoid(a.u_obs))  # observable-ish engagement quality

    def when():
        return _biz(rng, start + timedelta(seconds=float(rng.uniform(0, span))))

    rep = a.rep_id
    if not a.qualified:
        for _ in range(int(rng.poisson(2.0))):
            w.act(a, MARKETING_ID, when(), "email", _reply(rng, q, 0.02, 0.1), sequence="nurture")
        if rep is not None:
            for _ in range(int(rng.poisson(1.2))):
                w.act(a, rep, when(), "linkedin", _reply(rng, q, 0.03, 0.12))
        if rng.random() < 0.10 + 0.25 * q:
            w.act(a, MARKETING_ID, when(), "webinar")
        return
    for _ in range(int(rng.poisson(3 + 2 * q))):
        w.act(a, rep, when(), "email", _reply(rng, q))
    for _ in range(int(rng.poisson(2 + 1.5 * q))):
        r = rng.random()
        outcome = "meeting_booked" if r < 0.05 + 0.25 * q else ("reply" if r < 0.3 + 0.2 * q else "none")
        w.act(a, rep, when(), "call", outcome)
    for _ in range(int(rng.poisson(0.6 + 2.4 * q))):
        w.act(a, rep, when(), "meeting", "no_show" if rng.random() < 0.3 * (1 - q) else "none")
    if rng.random() < 0.25 + 0.55 * q:
        w.act(a, rep, when(), "demo")
    for _ in range(int(rng.poisson(1.2))):
        w.act(a, rep, when(), "linkedin", _reply(rng, q, 0.03, 0.15))
    if rng.random() < 0.15 + 0.35 * q:
        w.act(a, MARKETING_ID, when(), "webinar")


@dataclass
class Life:
    kyc_approved_at: datetime | None = None
    funded_at: datetime | None = None
    funded_amount: float | None = None
    first_trade_at: datetime | None = None
    first_qual_at: datetime | None = None
    trade_days: list | None = None  # sorted list of dates
    trade_iso_days: dict | None = None


def simulate_onboarding(w: World, a: Acct) -> Life:
    """contract_signed → funded (+ api key). Returns timestamps reached by AS_OF.

    A stall is not always final: with probability ``REVIVE_P`` a stalled
    account resumes after a long pause (new champion, budget cycle, ...).
    """
    rng = w.rng
    p, q = a.p, float(_sigmoid(a.u_obs))
    life = Life()
    t = a.signed_at
    stop = D.AS_OF

    def step(name, days, hours_lo=13, hours_hi=22):
        nonlocal t
        nt = _biz(rng, t + timedelta(days=float(days)), hours_lo, hours_hi)
        if nt <= t:
            nt = t + timedelta(minutes=int(rng.integers(5, 120)))
        if nt >= stop:
            return False
        t = nt
        w.ev(a, name, t)
        return True

    def stalls(prob: float) -> bool:
        """True if the account stops here for good; may instead pause and resume."""
        nonlocal t
        if rng.random() >= min(0.9, prob * STALL_MULT):
            return False
        if rng.random() < REVIVE_P:
            t = t + timedelta(days=float(rng.gamma(2.0, 22.0)))
            return t >= stop
        return True

    w.ev(a, "contract_signed", t)
    if a.is_lp:
        step("platform_account_created", 0.5)
        step("first_login", 1.0)
        step("kyc_submitted", 2.0)
        step("kyc_approved", 5.0)
        life.kyc_approved_at = t
        step("bank_linked", 2.0)
        step("funded", 2.0)
        life.funded_at = t
        life.funded_amount = round(float(rng.uniform(3e6, 12e6)), -3)
        step("api_key_created", 1.0)
        return life
    if not step("platform_account_created", rng.gamma(1.5, 0.6)):
        return life
    if stalls(0.10 * (1 - p) + 0.03):
        return life  # never logs in
    lag = rng.gamma(1.6, 3.0 * (1.7 - q) * (1.6 - p))
    if not step("first_login", lag):
        return life
    if stalls(0.05 + 0.14 * (1 - p)):
        return life  # never submits KYC
    slow = 1.4 if a.segment in ("UTILITY", "CI_LOAD") else 1.0
    if not step("kyc_submitted", rng.gamma(1.5, 2.6 * (1.5 - p) * slow) + 0.8 * a.kyc_redlines):
        return life
    loops = min(5, int(rng.poisson(KYC_LOOP_LAMBDA[a.segment] * (1.4 - p))))
    for _ in range(loops):
        if not step("kyc_info_requested", rng.gamma(2.0, 1.4)):
            return life
        rv = REVOPS_IDS[int(rng.integers(2))]
        w.act(a, rv, t + timedelta(hours=1), "email", _reply(rng, p, 0.3, 0.4), sequence="kyc_chase")
        w.act(a, rv, _biz(rng, t + timedelta(days=2)), "call", _reply(rng, p, 0.2, 0.4), sequence="kyc_chase")
        if stalls(KYC_LOOP_DROP.get(a.segment, 0.04) * (1.3 - p)):
            return life
        t = t + timedelta(days=float(rng.gamma(1.5, 3.5 * (1.5 - p))))
        if t >= stop:
            return life
    if not step("kyc_approved", rng.gamma(2.0, 1.2)):
        return life
    life.kyc_approved_at = t
    if stalls(0.05 + 0.12 * (1 - p)):
        return life
    if not step("bank_linked", rng.gamma(1.5, 2.2 * (1.5 - p))):
        return life
    if stalls(0.04 + 0.10 * (1 - p)):
        return life
    fund_scale = 8.5 if a.segment == "DATACENTER" else 1.3
    if not step("funded", rng.gamma(1.5, fund_scale * 1.3 * (1.4 - p))):
        return life
    life.funded_at = t
    base = 1.5e6 if a.side == "speculator" else 4e5
    life.funded_amount = round(float(base * math.sqrt(a.size_mw / SIZE_MEDIAN_MW[a.segment]) * np.exp(rng.normal(0, 0.5))), -3)
    api_p = (0.30 + 0.60 * q) if a.side == "speculator" else 0.04
    if rng.random() < api_p:
        tt = _biz(rng, t + timedelta(days=float(rng.gamma(2.0, 2.0 * (1.6 - q)))))
        if tt < stop:
            w.ev(a, "api_key_created", tt)
    return life


def _trigger_for(a: Acct, group: list[dict]) -> dict:
    for e in group:
        if e["hub"] == a.hub:
            return e
    return group[0]


def _coin(w: World, a: Acct, d: date) -> float:
    """Independent uniform per (account, event day): the AE's sequencing decision."""
    return float(np.random.default_rng([w.seed, 5, a.id, d.toordinal()]).random())


def volatility_sequence(w: World, a: Acct, e: dict) -> datetime:
    """Log a 5-touch triggered sequence; returns T0 time. Stops on reply."""
    rng = w.rng
    t0 = e["start_ts"] + timedelta(hours=float(rng.uniform(2, 20)))
    rep = a.rep_id or AE_BY_ISO[a.primary_iso]
    plan = [(0, "triggered_email"), (4 / 24, "linkedin"), (1, "call"), (2, "triggered_email"), (3, "call"),
            (5, "triggered_email")]
    for off, kind in plan:
        ts = t0 + timedelta(days=off)
        if ts.weekday() >= 5:
            ts = _biz(rng, ts)
        outcome = _reply(rng, a.p, 0.06, 0.30)
        w.act(a, rep, ts, kind, outcome, trigger_id=e["trigger_id"], sequence="volatility")
        if outcome == "reply":
            break
    return t0


def simulate_first_trade(w: World, a: Acct, life: Life, trig_cooldown: dict) -> None:
    """Funded → first order → first trade, with walkthroughs and triggered sequences."""
    rng = w.rng
    p = a.p
    funded = life.funded_at
    start_day = max(funded.date(), D.HISTORY_START.date())
    # pre-funding volatility sequences (no causal effect on trading)
    for (iso, d), group in w.trigger_groups:
        if iso not in a.exposure_isos or a.is_lp:
            continue
        e = _trigger_for(a, group)
        if not (a.signed_at < e["start_ts"] < funded):
            continue
        if e["start_ts"] >= DEMO_EVENT_START - timedelta(days=1):
            continue
        last = trig_cooldown.get(a.id)
        if last and (e["start_ts"] - last).days < D.TRIGGER_COOLDOWN_D:
            continue
        if _coin(w, a, d) < TRIGGER_PROB:
            trig_cooldown[a.id] = volatility_sequence(w, a, e)

    if a.is_lp:
        order_day = start_day + timedelta(days=int(rng.integers(0, 8)))
        while order_day.weekday() >= 5:
            order_day += timedelta(days=1)
        _place_first_order(w, a, life, order_day, rejected=False)
        return
    walk_p = (0.18 + 0.45 * _progress(funded)) if a.side == "hedger" else 0.05
    walk_at = None
    if rng.random() < walk_p:
        walk_at = _biz(rng, max(funded, D.HISTORY_START - timedelta(days=3)) + timedelta(days=float(rng.gamma(2.0, 2.5))))
    if a.side == "speculator":
        h0 = 0.023 * (p / 0.5) ** 1.0
    else:
        h0 = 0.0044 * (p / 0.5) ** 1.3
    h0 *= float(rng.lognormal(-0.12, 0.5))  # unobserved: internal approvals, risk limits, tech
    h_engaged = h0  # hazard once a blocker is addressed (used under a trigger)
    inert_p = 0.30 * (1 - p) ** 1.5
    if rng.random() < inert_p:
        h0 *= 0.12
    triggered_until: date | None = None
    trig_map = {d: g for (iso, d), g in w.trigger_groups if iso in a.exposure_isos}
    d = start_day
    end = D.AS_OF_DATE
    walked = False
    hz = np.random.default_rng([w.seed, 6, a.id])  # one uniform per weekday, always consumed
    while d < end:
        # volatility trigger on this day?
        if d in trig_map:
            e = _trigger_for(a, trig_map[d])
            if funded < e["start_ts"] and e["start_ts"] < DEMO_EVENT_START - timedelta(days=1):
                last = trig_cooldown.get(a.id)
                if not (last and (e["start_ts"] - last).days < D.TRIGGER_COOLDOWN_D) and _coin(w, a, d) < TRIGGER_PROB:
                    t0 = volatility_sequence(w, a, e)
                    trig_cooldown[a.id] = t0
                    triggered_until = t0.date() + timedelta(days=14)
        if walk_at is not None and not walked and walk_at.date() <= d:
            w.act(a, a.rep_id or AE_BY_ISO[a.primary_iso], walk_at, "walkthrough", sequence="activation")
            walked = True
        if d.weekday() < 5:
            u = float(hz.random())
            h = h0 * (0.5 + 0.8 * _progress(d))
            if walked and a.side == "hedger":
                h *= WALKTHROUGH_MULT
            if triggered_until is not None and d <= triggered_until:
                h = max(h, h_engaged * (0.5 + 0.8 * _progress(d))) * TRIGGER_HAZARD_MULT
            if d in w.event_days.get(a.primary_iso, ()):
                h *= NATURAL_EVENT_MULT
            if u < min(h, 0.95):
                _place_first_order(w, a, life, d, rejected=rng.random() < REJECT_PROB.get(a.segment, 0.08))
                return
        d += timedelta(days=1)
    # never ordered: some open a ticket anyway (intent without action)
    if rng.random() < 0.30:
        tt = _biz(rng, funded + timedelta(days=float(rng.gamma(2.0, 6.0))))
        if tt < D.AS_OF:
            w.ev(a, "order_ticket_opened", tt)


def _place_first_order(w: World, a: Acct, life: Life, d: date, rejected: bool) -> None:
    rng = w.rng
    order_ts = datetime(d.year, d.month, d.day, int(rng.integers(13, 21)), int(rng.integers(0, 60)))
    if order_ts <= life.funded_at:
        order_ts = life.funded_at + timedelta(hours=1)
    ticket_ts = order_ts - timedelta(hours=float(rng.gamma(1.5, 20.0)))
    ticket_ts = max(ticket_ts, life.funded_at + timedelta(minutes=10))
    w.ev(a, "order_ticket_opened", ticket_ts)
    w.ev(a, "first_order", order_ts)
    trade_ts = order_ts + timedelta(minutes=int(rng.integers(1, 30)))
    if rejected:
        w.ev(a, "order_rejected", order_ts + timedelta(minutes=2))
        td = _weekday_after(d + timedelta(days=int(rng.gamma(2.0, 1.6))))
        trade_ts = datetime(td.year, td.month, td.day, int(rng.integers(13, 21)), int(rng.integers(0, 60)))
    if trade_ts >= D.AS_OF:
        return
    life.first_trade_at = trade_ts


def simulate_trading(w: World, a: Acct, life: Life, lp_rank: int | None) -> None:
    """Trading-day process from first trade to AS_OF; emits trades."""
    rng = w.rng
    p = a.p
    first = life.first_trade_at
    side = a.side
    if a.is_lp:
        q = 0.97
        daily_scale = LP_DAILY[lp_rank] * SIZE_SCALE
        growth = 0.035
        churn_h = 0.0
        one_done = False
    else:
        if side == "speculator":
            q = float(np.clip(0.40 + 0.55 * p + rng.normal(0, 0.14), 0.06, 0.95))
        else:
            q = float(np.clip(0.07 + 0.40 * p + rng.normal(0, 0.12), 0.02, 0.75))
        daily_scale = DAILY_SIZE_MIN[a.segment] * (1 + float(np.clip(rng.pareto(1.6), 0, 25))) * SIZE_SCALE * 0.64
        daily_scale *= (a.size_mw / SIZE_MEDIAN_MW[a.segment]) ** 0.25
        growth = float(rng.uniform(0.06, 0.18)) if rng.random() < 0.4 else 0.0
        churn_h = 0.0038 * (1.3 - p)
        one_done = rng.random() < (0.22 if side == "hedger" else 0.10) * (1 - p)
    tenor_w = ({"HOURLY": 0.62, "DAILY_PEAK": 0.32, "WEEKLY_PEAK": 0.06} if side == "hedger"
               else {"HOURLY": 0.80, "DAILY_PEAK": 0.18, "WEEKLY_PEAK": 0.02})
    tenors = list(tenor_w)
    tw = np.array([tenor_w[k] for k in tenors])
    buy_p = 0.8 if a.segment in ("REP", "CI_LOAD", "DATACENTER", "UTILITY") else (0.2 if a.segment == "IPP" else 0.5)
    maker_p = 0.85 if a.is_lp else 0.15
    other_isos = [i for i in a.exposure_isos if i != a.primary_iso]
    # second-ISO expansion for some multi-ISO accounts after ~60 days
    expand_iso_day = None
    if other_isos and growth > 0 and rng.random() < 0.6:
        expand_iso_day = first.date() + timedelta(days=int(rng.integers(45, 120)))

    days: list[date] = []
    iso_days: dict[str, set] = defaultdict(set)

    def emit(ts: datetime, contracts_total: int, d: date, is_first: bool = False):
        n = 1 if is_first else (int(3 + rng.poisson(5)) if a.is_lp else int(1 + rng.poisson(min(5.0, contracts_total / 180.0))))
        n = max(1, min(n, contracts_total))
        parts = rng.multinomial(contracts_total - n, rng.dirichlet(np.ones(n))) + 1
        for k, c in enumerate(parts):
            if is_first:
                iso, hub = a.primary_iso, a.hub
            else:
                use_other = other_isos and (a.is_lp or (expand_iso_day and d >= expand_iso_day) or rng.random() < 0.12)
                iso = other_isos[int(rng.integers(len(other_isos)))] if use_other and rng.random() < 0.45 else a.primary_iso
                hub = a.hub if iso == a.primary_iso and rng.random() < 0.8 else D.ISOS[iso][int(rng.integers(len(D.ISOS[iso])))]
            tenor = tenors[int(rng.choice(len(tenors), p=tw))]
            if tenor != "HOURLY" and not is_first:
                c = max(1, int(round(c * TENOR_CONTRACT_SCALE[tenor])))
            room = max(2, (22 - ts.hour) * 60 - ts.minute)  # same trading day, before 22:00
            t_ts = ts if k == 0 else ts + timedelta(minutes=int(rng.integers(1, room)))
            if t_ts >= D.AS_OF:
                t_ts = ts
            if tenor == "HOURLY":
                price = w.lmp_at(hub, t_ts) * (1 + rng.normal(0, 0.03))
            else:
                price = w.peak_at(hub, t_ts.date()) * (1 + rng.normal(0, 0.05)) * (1.04 if tenor == "WEEKLY_PEAK" else 1.0)
            price = round(float(price), 2)
            maker = bool(rng.random() < maker_p)
            c = int(c)
            w.trades.append({
                "account_id": a.id, "ts": t_ts, "iso": iso, "hub": hub, "tenor": tenor,
                "side": "BUY" if rng.random() < buy_p else "SELL", "contracts": c, "price": price,
                "notional_usd": round(c * D.TENORS[tenor] * price, 2),
                "fee_usd": round(c * (D.FEE_MAKER_PER_CONTRACT if maker else D.FEE_TAKER_PER_CONTRACT), 2),
                "is_maker": maker,
            })
            iso_days[iso].add(t_ts.date())

    # first trade: hedgers often start with a 1–5 lot "test" fill (non-qualifying)
    if side == "hedger" and rng.random() < 0.30:
        first_c = int(rng.integers(1, 6))
    else:
        first_c = max(10, int(daily_scale * rng.lognormal(-0.7, 0.4)))
    emit(first, first_c, first.date(), is_first=True)
    days.append(first.date())

    churned = False
    d = first.date() + timedelta(days=1)
    while d < D.AS_OF_DATE:
        if d.weekday() < 5:
            tenure = (d - first.date()).days
            if not churned and not a.is_lp and rng.random() < churn_h:
                churned = True
                fade = 0.05 if rng.random() < 0.55 else 0.3
            q_eff = q * (0.55 + 0.45 * min(1.0, tenure / 30.0))
            if one_done:
                q_eff = 0.012
            if churned:
                q_eff *= fade
            ev_day = d in w.event_days.get(a.primary_iso, ())
            size_mult = 1.0
            if ev_day:
                q_eff = min(0.98, q_eff * (1.6 if side != "hedger" else 1.4))
                size_mult = 1.5 if side != "hedger" else 1.2
            if rng.random() < q_eff:
                contracts = int(max(1, round(daily_scale * rng.lognormal(-0.1, 0.45) * (1 + growth * tenure / 30.0) * size_mult)))
                ts = datetime(d.year, d.month, d.day, int(rng.integers(13, 21)), int(rng.integers(0, 60)))
                emit(ts, contracts, d)
                days.append(d)
        d += timedelta(days=1)
    life.trade_days = sorted(set(days))
    life.trade_iso_days = iso_days


def post_sign_touches(w: World, a: Acct, life: Life, active_dates: list[date]) -> None:
    """Standard activation sequence, AE check-ins while not yet active, QBR-ish check-ins."""
    rng = w.rng
    rep = a.rep_id or AE_BY_ISO[a.primary_iso]
    q = float(_sigmoid(a.u_obs))
    first_trade = life.first_trade_at
    for day, kind in ((0, "email"), (1, "call"), (3, "email"), (5, "call"), (7, "email"), (10, "email"),
                      (14, "call"), (21, "call")):
        ts = _biz(rng, a.signed_at + timedelta(days=day))
        if first_trade is not None and ts > first_trade:
            break
        w.act(a, rep, ts, kind, _reply(rng, q, 0.06, 0.35), sequence="activation")
    # periodic AE check-ins until active (or AS_OF)
    stop = datetime.combine(active_dates[0], datetime.min.time()) if active_dates else D.AS_OF
    t = a.signed_at + timedelta(days=25)
    while t < stop:
        t = t + timedelta(days=float(rng.gamma(2.0, 6.5)))
        if t >= stop or t >= D.AS_OF:
            break
        kind = "call" if rng.random() < 0.45 else ("email" if rng.random() < 0.8 else "meeting")
        outcome = _reply(rng, q, 0.05, 0.35) if kind != "meeting" else ("no_show" if rng.random() < 0.25 * (1 - q) else "none")
        w.act(a, rep, _biz(rng, t), kind, outcome)
    # light-touch account management once trading
    if first_trade is not None:
        t = first_trade + timedelta(days=float(rng.uniform(10, 40)))
        while t < D.AS_OF:
            w.act(a, rep, _biz(rng, t), "call" if rng.random() < 0.6 else "email", _reply(rng, q, 0.2, 0.4))
            t += timedelta(days=float(rng.gamma(3.0, 9.0)))


# ---------------------------------------------------------------------------
# Stage computation (from trades as of AS_OF)
# ---------------------------------------------------------------------------
def active_spells(trade_days: list[date], end: date) -> list[tuple[date, date | None]]:
    """[(start_day, end_day_or_None)] where Active holds at midnight evaluations.

    Active at midnight ``t`` ⇔ ≥4 distinct trading days in ``[t-30d, t)``.
    ``start_day`` is the day of the qualifying (4th) trading day.
    """
    if not trade_days:
        return []
    days = np.array([x.toordinal() for x in trade_days])
    t0 = trade_days[0].toordinal() + 1
    spells = []
    cur = None
    for t in range(t0, end.toordinal() + 1):
        cnt = int(((days >= t - D.ACTIVE_LOOKBACK_D) & (days < t)).sum())
        act = cnt >= D.ACTIVE_MIN_DAYS
        if act and cur is None:
            cur = date.fromordinal(t - 1)
        elif not act and cur is not None:
            spells.append((cur, date.fromordinal(t - 1)))
            cur = None
    if cur is not None:
        spells.append((cur, None))
    return spells


# ---------------------------------------------------------------------------
# Contacts, marketing, spreads
# ---------------------------------------------------------------------------
def gen_contacts(rng, accts: list[Acct]) -> list[dict]:
    rows = []
    for a in accts:
        q = float(_sigmoid(a.u_obs))
        n = 1 + int(rng.binomial(4, 0.12 + 0.45 * q))
        pw = PERSONA_W["speculator" if a.side != "hedger" else "hedger"]
        slug = "".join(ch for ch in a.name.lower() if ch.isalnum())[:24]
        champ_idx = int(rng.integers(n)) if rng.random() < 0.12 + 0.6 * q else -1
        used = set()
        for k in range(n):
            persona = _choice(rng, pw)
            for _ in range(20):
                fn = FIRST_NAMES[int(rng.integers(len(FIRST_NAMES)))]
                ln = LAST_NAMES[int(rng.integers(len(LAST_NAMES)))]
                if (fn, ln) not in used:
                    break
            used.add((fn, ln))
            rows.append({
                "account_id": a.id, "name": f"{fn} {ln}",
                "title": TITLES[persona][int(rng.integers(len(TITLES[persona])))], "persona": persona,
                "email": f"{fn[0].lower()}.{ln.lower()}@{slug}.example", "is_champion": k == champ_idx,
            })
    return rows


def gen_marketing(rng) -> list[dict]:
    base = {
        "Industry Conferences": 4000, "Webinars & Education": 9000, "Content & SEO": 12000, "LinkedIn Paid": 26000,
        "Partner Referrals": 5000, "Outbound Prospecting": 16000, "Liquidity Partner Intros": 3000,
    }
    leads_per_k = {
        "Industry Conferences": 0.45, "Webinars & Education": 2.6, "Content & SEO": 2.3, "LinkedIn Paid": 2.7,
        "Partner Referrals": 1.3, "Outbound Prospecting": 2.4, "Liquidity Partner Intros": 0.7,
    }
    conf_months = {date(2025, 10, 1): 60000, date(2026, 2, 1): 95000, date(2026, 4, 1): 70000,
                   date(2026, 6, 1): 85000, date(2026, 9, 1): 90000}
    rows = []
    for m in range(12):
        y, mo = 2025 + (9 + m) // 12, (9 + m) % 12 + 1
        month = date(y, mo, 1)
        for ch in D.CHANNELS:
            spend = base[ch] * (1 + 0.04 * m) * float(rng.uniform(0.85, 1.15))
            if ch == "Industry Conferences":
                spend += conf_months.get(month, 0)
            leads = int(rng.poisson(leads_per_k[ch] * spend / 1000.0))
            camp = CAMPAIGNS[ch][m % len(CAMPAIGNS[ch])]
            rows.append({"month": month, "channel": ch, "spend_usd": round(spend, 2), "leads": leads, "campaign": camp})
    return rows


SPREAD_AB = {
    "HB_NORTH": (0.50, 2.9, 55.0),
    "HB_HOUSTON": (0.65, 3.4, 60.0),
    "HB_WEST": (0.80, 3.6, 70.0),
    "PJM_WESTERN_HUB": (0.85, 4.2, 75.0),
    "SP15": (0.95, 4.2, 78.0),
    "NP15": (1.05, 4.4, 80.0),
    "MISO_INDIANA_HUB": (1.00, 4.4, 80.0),
}


def gen_spreads(rng, trades: pd.DataFrame, lp_ids: set[int], events: list[dict]) -> list[dict]:
    """Daily spread per hub × tenor from ISO-level active-account counts."""
    dates = pd.date_range(D.HISTORY_START.date(), D.AS_OF_DATE - timedelta(days=1), freq="D")
    nd = len(dates)
    d0 = D.HISTORY_START.date().toordinal()
    tr = trades.assign(day=trades["ts"].dt.normalize())
    tr["dix"] = (tr["day"] - pd.Timestamp(D.HISTORY_START)).dt.days
    acct_ids = sorted(tr["account_id"].unique())
    aix = {a: i for i, a in enumerate(acct_ids)}
    any_mat = np.zeros((len(acct_ids), nd), dtype=np.int32)
    g = tr.groupby(["account_id", "dix"]).size().reset_index()
    any_mat[g["account_id"].map(aix).to_numpy(), g["dix"].to_numpy()] = 1
    # trailing-30 (inclusive of day) distinct trading days
    cs = np.cumsum(any_mat, axis=1)
    cs_pad = np.concatenate([np.zeros((len(acct_ids), 30), dtype=np.int64), cs], axis=1)
    trail = cs_pad[:, 30:] - cs_pad[:, :-30]
    active = trail >= D.ACTIVE_MIN_DAYS
    is_lp = np.array([a in lp_ids for a in acct_ids])
    event_days = defaultdict(set)
    for e in events:
        for k in range(0, 2):
            event_days[e["hub"]].add((e["start_ts"].date() + timedelta(days=k)).toordinal() - d0)
    rows = []
    for iso, hubs in D.ISOS.items():
        iso_mat = np.zeros_like(any_mat)
        gi = tr[tr["iso"] == iso].groupby(["account_id", "dix"]).size().reset_index()
        iso_mat[gi["account_id"].map(aix).to_numpy(), gi["dix"].to_numpy()] = 1
        ics = np.cumsum(iso_mat, axis=1)
        ics_pad = np.concatenate([np.zeros((len(acct_ids), 30), dtype=np.int64), ics], axis=1)
        traded_iso = (ics_pad[:, 30:] - ics_pad[:, :-30]) > 0
        n_active = (active & traded_iso).sum(axis=0)
        n_org = (active & traded_iso & ~is_lp[:, None]).sum(axis=0)
        for hub in hubs:
            a_, b_, c_ = SPREAD_AB[hub]
            noise = _ar1(rng, nd, 0.6, 0.025)
            for tenor in D.SPREAD_TENORS:
                tm = 1.0 if tenor == "HOURLY" else 0.85
                for i in range(nd):
                    n_act = int(n_active[i])
                    eff = n_act + 3
                    spread = (a_ + b_ / math.sqrt(eff)) * tm + noise[i]
                    up = 100.0 - c_ / math.sqrt(eff) - (3.0 if tenor == "DAILY_PEAK" else 0.0) + rng.normal(0, 0.8)
                    if i in event_days[hub]:
                        spread *= 1.35
                        up -= 5.0
                    lp_share = float(np.clip(1.0 - 0.75 * (int(n_org[i]) / (eff + 6)), 0.35, 0.97))
                    rows.append({
                        "date": dates[i].date(), "iso": iso, "hub": hub, "tenor": tenor,
                        "spread_usd_mwh": round(max(0.3, spread), 3),
                        "two_sided_uptime_pct": round(float(np.clip(up, 40.0, 99.8)), 2),
                        "top_depth_contracts": int(max(5, 10 + 4 * n_act + rng.normal(0, 6))),
                        "active_accounts": n_act, "lp_quote_share": round(lp_share, 3),
                    })
    return rows


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def generate(seed: int = SEED) -> dict[str, pd.DataFrame]:
    """Generate every table as a DataFrame (no DB I/O)."""
    rng = np.random.default_rng(seed)
    reps = pd.DataFrame([{"id": r[0], "name": r[1], "role": r[2], "region": r[3], "quota_funded_annual": r[4],
                          "quota_adv": r[5], "start_date": r[6]} for r in REPS])
    prices = gen_prices(rng)
    forecasts = gen_forecasts(rng, prices)
    events = vol.detect_historical_events(prices)
    accts = gen_accounts(rng)
    assign_signing(rng, accts)
    w = World(rng, prices, events, seed)
    lives: dict[int, Life] = {}
    trig_cooldown: dict[int, datetime] = {}
    # Independent per-account streams: tuning one subsystem (e.g. trade sizes)
    # never reshuffles another (e.g. the funnel or the trigger experiment).
    def stream(kind: int, a: Acct) -> np.random.Generator:
        return np.random.default_rng([seed, kind, a.id])

    for a in accts:
        w.rng = stream(1, a)
        presign_activities(w, a)
    signed = sorted([a for a in accts if a.signed], key=lambda a: a.signed_at)
    lp_order = sorted([a for a in accts if a.is_lp], key=lambda a: a.id)
    lp_rank_of = {a.id: k for k, a in enumerate(lp_order)}
    for a in signed:
        w.rng = stream(2, a)
        life = simulate_onboarding(w, a)
        lives[a.id] = life
        if life.funded_at is not None:
            simulate_first_trade(w, a, life, trig_cooldown)
        if life.first_trade_at is not None:
            w.rng = stream(3, a)
            simulate_trading(w, a, life, lp_rank_of.get(a.id))
    trades_df = pd.DataFrame(w.trades).sort_values(["ts", "account_id"]).reset_index(drop=True)
    trades_df["ts"] = pd.to_datetime(trades_df["ts"])

    # ---- stage computation & activated events
    acc_rows = []
    adv_30_by_acct = trades_df[trades_df["ts"] >= pd.Timestamp(D.AS_OF - timedelta(days=30))].groupby("account_id")["contracts"].sum()
    for a in accts:
        life = lives.get(a.id, Life())
        tdays = life.trade_days or []
        spells = active_spells(tdays, D.AS_OF_DATE) if tdays else []
        lo = D.AS_OF_DATE - timedelta(days=D.ACTIVE_LOOKBACK_D)
        td30 = sum(1 for x in tdays if lo <= x < D.AS_OF_DATE)
        ever_active = bool(spells)
        active_dates = [s[0] for s in spells]
        if spells:
            first_act = spells[0][0]
            # "activated" ts: the 4th-day trade time (first trade of that day)
            day_trades = trades_df[(trades_df["account_id"] == a.id) & (trades_df["ts"].dt.date == first_act)]
            w.ev(a, "activated", day_trades["ts"].min().to_pydatetime() + timedelta(minutes=1))
        current_since = spells[-1][0] if spells and spells[-1][1] is None else None
        expanding = False
        if current_since is not None and (D.AS_OF_DATE - current_since).days >= D.EXPANDING_MIN_ACTIVE_D:
            ft = life.first_trade_at
            mine = trades_df[trades_df["account_id"] == a.id]
            base = mine[(mine["ts"] >= ft) & (mine["ts"] < ft + timedelta(days=60))]
            base_adv = base["contracts"].sum() / 60.0
            recent = mine[mine["ts"] >= pd.Timestamp(D.AS_OF - timedelta(days=30))]
            recent_adv = recent["contracts"].sum() / 30.0
            isos_base = set(base["iso"])
            isos_recent = set(recent["iso"])
            expanding = (base_adv > 0 and recent_adv >= D.EXPANDING_ADV_MULT * base_adv) or bool(isos_recent - isos_base)
        stage = D.classify_stage(
            signed=a.signed, qualified=a.qualified, kyc_approved=life.kyc_approved_at is not None,
            funded=life.funded_at is not None, has_traded=bool(tdays), trading_days_30=td30,
            ever_active=ever_active, expanding=expanding,
        )
        first_q = None
        if tdays:
            mine_q = trades_df[(trades_df["account_id"] == a.id) & (trades_df["contracts"] >= D.QUALIFYING_CONTRACTS)]
            if not mine_q.empty:
                first_q = mine_q["ts"].min().to_pydatetime()
        if a.signed:
            w.rng = stream(4, a)
            post_sign_touches(w, a, life, active_dates)
        acc_rows.append({
            "id": a.id, "name": a.name, "segment": a.segment, "primary_iso": a.primary_iso,
            "exposure_isos": ",".join(a.exposure_isos), "hub": a.hub, "hq_state": a.hq_state, "size_mw": a.size_mw,
            "est_annual_mwh": a.est_annual_mwh, "tam_tier": a.tam_tier, "lead_source": a.lead_source,
            "rep_id": a.rep_id, "stage": stage, "is_liquidity_partner": a.is_lp,
            "has_other_exchange_account": a.has_other_exchange, "kyc_redlines": a.kyc_redlines,
            "created_at": a.created_at, "signed_at": a.signed_at, "kyc_approved_at": life.kyc_approved_at,
            "funded_at": life.funded_at, "funded_amount_usd": life.funded_amount,
            "first_trade_at": life.first_trade_at, "first_qualifying_trade_at": first_q,
            "active_since": datetime.combine(current_since, datetime.min.time()) if current_since else None,
            "latent_propensity": round(a.p, 6),
        })
        if life.first_trade_at is not None:
            w.ev(a, "first_trade", life.first_trade_at)
    accounts = pd.DataFrame(acc_rows)

    # QBRs for top-20 accounts by trailing-30 volume
    top20 = adv_30_by_acct.sort_values(ascending=False).head(20).index
    by_id = {a.id: a for a in accts}
    w.rng = rng
    for aid in top20:
        a = by_id[int(aid)]
        ft = lives[a.id].first_trade_at
        t = ft + timedelta(days=60)
        while t < D.AS_OF:
            w.act(a, STRATEGIC_ID, _biz(rng, t), "qbr")
            t += timedelta(days=90)

    lp_ids = {a.id for a in accts if a.is_lp}
    spreads = gen_spreads(rng, trades_df, lp_ids, events)
    contacts = gen_contacts(rng, accts)
    marketing = gen_marketing(rng)

    onboarding = pd.DataFrame(w.onboarding).sort_values(["ts", "account_id"]).reset_index(drop=True)
    activities = pd.DataFrame(w.activities).sort_values(["ts", "account_id"]).reset_index(drop=True)
    vol_events = pd.DataFrame(events)
    out = {
        "reps": reps,
        "accounts": accounts,
        "contacts": pd.DataFrame(contacts),
        "activities": activities,
        "onboarding_events": onboarding,
        "trades": trades_df,
        "market_prices": prices,
        "price_forecasts": pd.DataFrame(forecasts),
        "spread_snapshots": pd.DataFrame(spreads),
        "marketing_spend": pd.DataFrame(marketing),
        "volatility_events": vol_events,
    }
    for name in ("contacts", "activities", "onboarding_events", "trades", "price_forecasts", "spread_snapshots",
                 "marketing_spend", "volatility_events"):
        df = out[name]
        df.insert(0, "id", np.arange(1, len(df) + 1))
    return out


def checksum(tables: dict[str, pd.DataFrame]) -> str:
    """Stable digest of row counts and key sums (determinism check)."""
    parts = [f"{name}:{len(tables[name])}" for name, _ in _TABLE_ORDER]
    t, a, p = tables["trades"], tables["accounts"], tables["market_prices"]
    parts.append(f"contracts:{int(t['contracts'].sum())}")
    parts.append(f"lmp:{round(float(p['lmp'].sum()), 2)}")
    parts.append("stages:" + ",".join(f"{k}={v}" for k, v in sorted(a["stage"].value_counts().items())))
    parts.append(f"acts:{len(tables['activities'])}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# DB I/O
# ---------------------------------------------------------------------------
_TABLE_ORDER = [
    ("reps", Rep), ("accounts", Account), ("contacts", Contact), ("activities", Activity),
    ("onboarding_events", OnboardingEvent), ("trades", Trade), ("market_prices", MarketPrice),
    ("price_forecasts", PriceForecast), ("spread_snapshots", SpreadSnapshot), ("marketing_spend", MarketingSpend),
    ("volatility_events", VolatilityEvent),
]


def _records(df: pd.DataFrame, model) -> list[dict]:
    cols = [c.name for c in model.__table__.columns]
    df = df[[c for c in cols if c in df.columns]]
    recs = []
    for row in df.itertuples(index=False, name=None):
        rec = {}
        for c, v in zip(df.columns, row):
            if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NaT:
                rec[c] = None
            elif isinstance(v, pd.Timestamp):
                rec[c] = v.to_pydatetime()
            elif isinstance(v, np.integer):
                rec[c] = int(v)
            elif isinstance(v, np.floating):
                rec[c] = float(v)
            elif isinstance(v, np.bool_):
                rec[c] = bool(v)
            else:
                rec[c] = v
        recs.append(rec)
    return recs


def write(engine: Engine, tables: dict[str, pd.DataFrame]) -> None:
    with engine.begin() as conn:
        for name, model in _TABLE_ORDER:
            recs = _records(tables[name], model)
            if recs:
                conn.execute(model.__table__.insert(), recs)


def reset(engine: Engine) -> None:
    from . import models  # noqa: F401

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def is_empty(engine: Engine) -> bool:
    create_all(engine)
    with engine.connect() as conn:
        return (conn.execute(select(func.count()).select_from(Account)).scalar() or 0) == 0


def seed(engine: Engine, seed_value: int = SEED) -> dict[str, pd.DataFrame]:
    tables = generate(seed_value)
    reset(engine)
    write(engine, tables)
    try:
        from . import repo

        repo.invalidate_cache()
    except Exception:  # pragma: no cover - repo optional during bootstrap
        pass
    return tables


def seed_if_empty(engine: Engine | None = None) -> bool:
    """Seed the DB when it has no accounts. Returns True if it seeded."""
    if engine is None:
        from .database import engine as default_engine

        engine = default_engine
    if not is_empty(engine):
        return False
    seed(engine)
    return True


# ---------------------------------------------------------------------------
# Calibration report
# ---------------------------------------------------------------------------
def calibration_report(t: dict[str, pd.DataFrame], as_of: datetime = D.AS_OF) -> dict:
    """Actual synthetic 'now' vs spec §C calibration targets."""
    acc = t["accounts"].copy()
    tr = t["trades"].copy()
    tr["ts"] = pd.to_datetime(tr["ts"])
    for c in ("signed_at", "funded_at", "first_trade_at", "first_qualifying_trade_at"):
        acc[c] = pd.to_datetime(acc[c])
    as_of_ts = pd.Timestamp(as_of)
    signed = int(acc["signed_at"].notna().sum())
    funded = int(acc["funded_at"].notna().sum())
    lo30 = as_of_ts - pd.Timedelta(days=30)
    td30 = tr[(tr["ts"] >= lo30) & (tr["ts"] < as_of_ts)].assign(d=lambda x: x["ts"].dt.date).groupby("account_id")["d"].nunique()
    acc["td30"] = acc["id"].map(td30).fillna(0).astype(int)
    acc["active"] = acc["td30"] >= D.ACTIVE_MIN_DAYS
    mature = acc["funded_at"].notna() & (acc["funded_at"] <= as_of_ts - pd.Timedelta(days=D.ACTIVE_RATE_MIN_AGE_D))
    active_rate = float(acc.loc[mature, "active"].mean())
    act = acc[acc["active"]]
    side = act.apply(lambda r: D.segment_side(r["segment"], bool(r["is_liquidity_partner"])), axis=1)
    hedger_share = float((side == "hedger").mean())
    hedger_share_ex_lp = float((side[side != "liquidity_partner"] == "hedger").mean())

    def adv(end: date, lp: bool | None = None):
        d0, d1 = D.adv_window(end)
        m = (tr["ts"].dt.date >= d0) & (tr["ts"].dt.date <= d1)
        x = tr[m]
        if lp is not None:
            lp_ids = set(acc.loc[acc["is_liquidity_partner"], "id"])
            x = x[x["account_id"].isin(lp_ids) == lp]
        return float(x["contracts"].sum()) / D.ADV_WINDOW_TD, x

    adv_now, win = adv(as_of.date())
    adv_prior, _ = adv(D.trading_days_back(as_of.date(), 20)[0])
    adv_lp, _ = adv(as_of.date(), lp=True)
    by_acct = win.groupby("account_id")["contracts"].sum().sort_values(ascending=False)
    top5 = float(by_acct.head(5).sum() / by_acct.sum())
    notional = float(win["notional_usd"].sum()) / D.ADV_WINDOW_TD
    # monthly ADV trend
    tr["month"] = tr["ts"].dt.to_period("M")
    wd = tr.groupby("month")["ts"].apply(lambda s: s.dt.date.nunique())
    monthly_adv = (tr.groupby("month")["contracts"].sum() / wd).round(0)
    # spreads
    sp = t["spread_snapshots"].copy()
    sp["date"] = pd.to_datetime(sp["date"])
    hn = sp[(sp["hub"] == "HB_NORTH") & (sp["tenor"] == "HOURLY")].sort_values("date")
    last5 = hn.tail(5)
    spread_now = float(last5["spread_usd_mwh"].mean())
    uptime_now = float(last5["two_sided_uptime_pct"].mean())
    spread_q1 = float(hn[hn["date"] < "2026-04-01"]["spread_usd_mwh"].mean())
    corr = float(np.corrcoef(hn["spread_usd_mwh"], hn["active_accounts"])[0, 1])
    # cohort activation (first qualifying trade within 30 d of funding), weekly cohorts
    f = acc[acc["funded_at"].notna() & ~acc["is_liquidity_partner"]].copy()
    f = f[f["funded_at"] <= as_of_ts - pd.Timedelta(days=D.COHORT_FIRST_TRADE_D)]
    f["ok"] = f["first_qualifying_trade_at"].notna() & (
        (f["first_qualifying_trade_at"] - f["funded_at"]) <= pd.Timedelta(days=D.COHORT_FIRST_TRADE_D))
    f["q"] = f["funded_at"].dt.to_period("Q")
    cohort_q = f.groupby("q")["ok"].agg(["mean", "size"]).round(3)
    last8w = f[f["funded_at"] > as_of_ts - pd.Timedelta(days=D.COHORT_FIRST_TRADE_D + 56)]
    ft = acc[acc["funded_at"].notna() & acc["first_trade_at"].notna() & ~acc["is_liquidity_partner"]]
    med_days = float(((ft["first_trade_at"] - ft["funded_at"]).dt.total_seconds() / 86400).median())
    # trigger lift
    ev = t["volatility_events"].copy()
    ev["start_ts"] = pd.to_datetime(ev["start_ts"])
    acts = t["activities"].copy()
    lift = vol.trigger_cohort_lift(acc, acts, tr, ev, as_of)
    # ERCOT-exposed pre-trade accounts
    pre = acc[(~acc["is_liquidity_partner"]) & acc["stage"].isin(["SIGNED", "KYC_APPROVED", "FUNDED"])
              & acc["exposure_isos"].str.contains("ERCOT")]
    return {
        "signed": signed,
        "funded": funded,
        "active_accounts": int(acc["active"].sum()),
        "active_rate": round(active_rate, 3),
        "adv_20td": round(adv_now, 0),
        "adv_prior_20td": round(adv_prior, 0),
        "adv_lp_20td": round(adv_lp, 0),
        "adv_notional_20td": round(notional, 0),
        "monthly_adv": {str(k): float(v) for k, v in monthly_adv.items()},
        "hedger_share_active": round(hedger_share, 3),
        "hedger_share_active_ex_lp": round(hedger_share_ex_lp, 3),
        "top5_adv_share": round(top5, 3),
        "ercot_north_spread_now": round(spread_now, 3),
        "ercot_north_spread_q1": round(spread_q1, 3),
        "ercot_north_uptime_now": round(uptime_now, 2),
        "corr_spread_active_hb_north": round(corr, 3),
        "cohort_activation_30d_last8w": round(float(last8w["ok"].mean()), 3) if len(last8w) else None,
        "cohort_activation_30d_last8w_n": int(len(last8w)),
        "cohort_activation_30d_by_quarter": {str(k): {"rate": float(r["mean"]), "n": int(r["size"])} for k, r in cohort_q.iterrows()},
        "median_days_funded_to_first_trade": round(med_days, 1),
        "trigger_lift": lift,
        "ercot_exposed_pre_trade": int(len(pre)),
        "ercot_exposed_pre_trade_segments": pre["segment"].value_counts().to_dict(),
        "stages": acc["stage"].value_counts().to_dict(),
        "volatility_events": int(len(ev)),
        "rows": {k: int(len(v)) for k, v in t.items()},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the Ignition database with synthetic data.")
    parser.add_argument("--reset", action="store_true", help="drop and re-create all tables, then seed")
    parser.add_argument("--report", action="store_true", help="print the calibration report (no DB writes)")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)
    from .database import engine

    t0 = time.perf_counter()
    if args.report and not args.reset:
        tables = generate(args.seed)
        print(json.dumps(calibration_report(tables), indent=2, default=str))
        print(f"checksum={checksum(tables)}  ({time.perf_counter() - t0:.1f}s)")
        return 0
    if args.reset:
        tables = seed(engine, args.seed)
    else:
        if not is_empty(engine):
            print("Database already seeded; use --reset to rebuild.")
            return 0
        tables = seed(engine, args.seed)
    print(f"Seeded {engine.url} in {time.perf_counter() - t0:.1f}s; checksum={checksum(tables)}")
    print("rows: " + ", ".join(f"{k}={len(v)}" for k, v in tables.items()))
    if args.report:
        print(json.dumps(calibration_report(tables), indent=2, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
