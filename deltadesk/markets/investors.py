"""Portfolios of well-known Indian investors: who they are, what they hold, valued with live quotes.

Source: data/investors.json (schema below). Holdings above 1 % are disclosed every quarter in the exchange
shareholding filings, which is where a fetcher should fill this file from. Until then a seed list ships with
the investors, their style and a few of their long-held, widely reported positions, flagged `seed: true`
with stakes marked approximate. Every page that shows them says so.

Schema:
  {"slug": "…", "name": "…", "known_for": "…", "style": ["…"], "vehicle": "RARE Enterprises",
   "since": "…", "asof": "YYYY-MM-DD", "holdings": [{"symbol": "TITAN", "stake_pct": 5.2, "approx": true}, …]}
Derived on load: for each holding the quote, day change, and value in ₹ crore when stake and market cap
are both known (stake_pct × market cap); per investor the number of holdings, sectors and the total value
of holdings we could value.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

PATH = Path("data") / "investors.json"

SEED = [
    {"slug": "rakesh-jhunjhunwala", "name": "Rakesh Jhunjhunwala (RARE Enterprises)", "known_for": "The Big Bull: concentrated, decade-long bets on Indian consumption and finance; the portfolio is now run by his family through RARE Enterprises.",  # noqa: E501
     "style": ["long term", "concentrated", "consumer", "financials"], "vehicle": "RARE Enterprises", "since": "1985", "asof": "2025-06-30",
     "holdings": [{"symbol": "TITAN", "stake_pct": 5.2, "approx": True}, {"symbol": "STARHEALTH", "stake_pct": 17.5, "approx": True},  # noqa: E501
                  {"symbol": "METROBRAND", "stake_pct": 14.4, "approx": True}, {"symbol": "CRISIL", "stake_pct": 5.5, "approx": True}, {"symbol": "FEDERALBNK", "stake_pct": 1.4, "approx": True},  # noqa: E501
                  {"symbol": "NAZARA", "stake_pct": 7.1, "approx": True}]},
    {"slug": "radhakishan-damani", "name": "Radhakishan Damani", "known_for": "Founder of DMart; buys quality businesses at fair prices and holds for decades with very few names.",  # noqa: E501
     "style": ["value", "very long term", "retail", "consumer"], "vehicle": "Bright Star Investments", "since": "1980s", "asof": "2025-06-30",  # noqa: E501
     "holdings": [{"symbol": "DMART", "stake_pct": 74.6, "approx": True}, {"symbol": "VSTIND", "stake_pct": 32.7, "approx": True},
                  {"symbol": "SUNDARMFIN", "stake_pct": 2.2, "approx": True}, {"symbol": "TRENT", "stake_pct": 1.4, "approx": True}, {"symbol": "BLUEDART", "stake_pct": 1.4, "approx": True}]},  # noqa: E501
    {"slug": "ashish-kacholia", "name": "Ashish Kacholia", "known_for": "Small and mid caps with rising earnings; dozens of positions, active churn, early into niche manufacturers.",  # noqa: E501
     "style": ["small cap", "growth", "diversified"], "vehicle": "Lucky Investment Managers", "since": "1990s", "asof": "2025-06-30",
     "holdings": [{"symbol": "SAFARI", "stake_pct": 2.3, "approx": True}, {"symbol": "GRAVITA", "stake_pct": 2.1, "approx": True}, {"symbol": "XPROINDIA", "stake_pct": 3.3, "approx": True},  # noqa: E501
                  {"symbol": "BEML", "stake_pct": 1.1, "approx": True}, {"symbol": "ADFFOODS", "stake_pct": 2.6, "approx": True}]},  # noqa: E501
    {"slug": "vijay-kedia", "name": "Vijay Kedia", "known_for": "SMILE investing: small in size, medium in experience, large in aspiration, extra-large in market potential.",  # noqa: E501
     "style": ["small cap", "long term", "management quality"], "vehicle": "Kedia Securities", "since": "1990s", "asof": "2025-06-30",
     "holdings": [{"symbol": "ATULAUTO", "stake_pct": 20.6, "approx": True}, {"symbol": "TEJASNET", "stake_pct": 1.8, "approx": True}, {"symbol": "ELECON", "stake_pct": 1.6, "approx": True},  # noqa: E501
                  {"symbol": "OMINFRAL", "stake_pct": 2.2, "approx": True}, {"symbol": "GLOBALVECT", "stake_pct": 4.5, "approx": True}, {"symbol": "REPRO", "stake_pct": 7.0, "approx": True}]},  # noqa: E501
    {"slug": "mukul-agrawal", "name": "Mukul Agrawal", "known_for": "One of the widest small-cap portfolios among individual investors, with a taste for turnarounds and special situations.",  # noqa: E501
     "style": ["small cap", "diversified", "special situations"], "vehicle": "Param Capital", "since": "2000s", "asof": "2025-06-30",
     "holdings": [{"symbol": "RADICO", "stake_pct": 2.1, "approx": True}, {"symbol": "NUVAMA", "stake_pct": 1.9, "approx": True}, {"symbol": "DELTACORP", "stake_pct": 2.0, "approx": True},  # noqa: E501
                  {"symbol": "BSE", "stake_pct": 1.4, "approx": True}, {"symbol": "PEARLPOLY", "stake_pct": 2.5, "approx": True}, {"symbol": "TARC", "stake_pct": 1.3, "approx": True}]},  # noqa: E501
    {"slug": "dolly-khanna", "name": "Dolly Khanna", "known_for": "Chennai-based investor known for early positions in unglamorous cyclicals: chemicals, textiles, sugar, small manufacturers.",  # noqa: E501
     "style": ["small cap", "cyclicals", "contrarian"], "vehicle": "", "since": "2010s", "asof": "2025-06-30",
     "holdings": [{"symbol": "CHENNPETRO", "stake_pct": 1.7, "approx": True}, {"symbol": "POLYPLEX", "stake_pct": 1.4, "approx": True}, {"symbol": "PRAKASH", "stake_pct": 1.6, "approx": True},  # noqa: E501
                  {"symbol": "NITINSPIN", "stake_pct": 1.4, "approx": True}]},
    {"slug": "sunil-singhania", "name": "Sunil Singhania (Abakkus)", "known_for": "Former Reliance MF CIO; Abakkus funds buy mid and small caps with a five-year lens and public disclosure above 1 %.",  # noqa: E501
     "style": ["mid cap", "growth at reasonable price", "institutional"], "vehicle": "Abakkus Asset Manager", "since": "2018", "asof": "2025-06-30",  # noqa: E501
     "holdings": [{"symbol": "IONEXCHANG", "stake_pct": 3.1, "approx": True}, {"symbol": "JTLIND", "stake_pct": 2.7, "approx": True}, {"symbol": "ROUTE", "stake_pct": 2.6, "approx": True},  # noqa: E501
                  {"symbol": "HILTON", "stake_pct": 4.9, "approx": True}, {"symbol": "SARDAEN", "stake_pct": 1.3, "approx": True}, {"symbol": "DYNAMATECH", "stake_pct": 2.1, "approx": True}]},  # noqa: E501
    {"slug": "porinju-veliyath", "name": "Porinju Veliyath (Equity Intelligence)", "known_for": "Deep-value and turnaround picks in micro and small caps, publicly argued, high conviction.",  # noqa: E501
     "style": ["micro cap", "deep value", "turnarounds"], "vehicle": "Equity Intelligence India", "since": "2002", "asof": "2025-06-30",
     "holdings": [{"symbol": "RAJSREESUG", "stake_pct": 2.4, "approx": True}, {"symbol": "SHALPAINTS", "stake_pct": 1.6, "approx": True},  # noqa: E501
                  {"symbol": "ANSALAPI", "stake_pct": 2.0, "approx": True}]},
]


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _read() -> tuple[list[dict], str]:
    if PATH.exists():
        try:
            return json.loads(PATH.read_text(encoding="utf-8")), str(PATH)
        except json.JSONDecodeError:
            return [], f"{PATH} (invalid JSON)"
    return [json.loads(json.dumps(e)) | {"seed": True} for e in SEED], "seed list (approximate stakes from public filings; wire the shareholding feed to refresh)"  # noqa: E501


def load(quotes: Callable[[list[str]], dict] | None = None, market_caps: Callable[[list[str]], dict] | None = None,
         names: Callable[[str], tuple[str, str, str]] | None = None) -> dict:
    investors, source = _read()
    for inv in investors:
        inv.setdefault("slug", slugify(inv["name"]))
        inv.setdefault("holdings", [])
    keys = sorted({h["symbol"] for inv in investors for h in inv["holdings"]})
    q = {}
    caps = {}
    if quotes:
        try:
            q = quotes(keys)
        except Exception:  # noqa: BLE001
            q = {}
    if market_caps:
        try:
            caps = market_caps(keys)
        except Exception:  # noqa: BLE001
            caps = {}
    for inv in investors:
        total, valued, sectors = 0.0, 0, set()
        for h in inv["holdings"]:
            k = h["symbol"]
            qq = q.get(k)
            nm, kind, sector = names(k) if names else (k, "stock", "")
            h["name"] = nm if kind != "unknown" else k
            h["sector"] = sector
            h["quote"] = qq.json() if qq is not None else None
            cap = caps.get(k)
            h["market_cap_cr"] = cap
            h["value_cr"] = round(cap * h["stake_pct"] / 100) if cap and h.get("stake_pct") else None
            if h["value_cr"]:
                total += h["value_cr"]
                valued += 1
            if sector:
                sectors.add(sector)
        inv["holdings"].sort(key=lambda x: -(x.get("value_cr") or 0))
        day = [h["quote"]["change_pct"] for h in inv["holdings"] if h.get("quote") and h["quote"].get("change_pct") is not None]
        inv["summary"] = {"count": len(inv["holdings"]), "valued": valued, "value_cr": round(total) if valued else None, "sectors": sorted(sectors),  # noqa: E501
                          "day_avg_pct": round(sum(day) / len(day), 2) if day else None, "quoted": len(day)}
    investors.sort(key=lambda i: -(i["summary"]["value_cr"] or 0))
    return {"source": source, "count": len(investors), "investors": investors,
            "note": "Stakes come from quarterly shareholding disclosures (holdings above 1 %). Values are stake × market cap when both are known. Seed stakes are approximate. Nothing here is investment advice."}  # noqa: E501


def one(slug: str, **kw) -> dict | None:
    d = load(**kw)
    return next((i for i in d["investors"] if i["slug"] == slug), None)
