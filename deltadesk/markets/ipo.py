"""IPO calendar, detail, performance tracker and the IPO agent (rules v0).

Structure follows what retail investors expect from an IPO section: a list split by state (open, upcoming,
closed, listed), a detail page per issue (dates, price, subscription by category, company, financials,
strengths and risks, objectives, managers, documents) and a performance tracker (issue price vs listing
day close vs current price, per year and board).

Data source, in order of preference:
  1. data/ipo.json: a list of entries in the schema below. A fetcher job or a licensed vendor feed writes it.
     Primary sources for every field except the grey market: SEBI (DRHP / RHP), NSE and BSE offer documents
     and bid data, the registrar for allotment, the exchange for listing prices.
  2. Fictional example entries (flagged `example: true`) so the pages have shape before a feed is wired.

No broker API exposes IPOs, so bids stay in the user's broker app. Grey market premium is deliberately
not part of the model (no primary source).

Entry schema (all money in rupees, sizes in crore, dates ISO):
  name, symbol, slug, segment ("Mainboard" | "SME"), exchange ("NSE" | "BSE" | "NSE, BSE"), domain,
  price_lo, price_hi, lot, face_value, issue_size_cr, fresh_cr, ofs_cr,
  open, close, allotment, refund, credit, listing,
  subscription: {qib, nii, rii, employee, total}   (times subscribed)
  listing_open, listing_close                          (listing day prices, listed issues only)
  about, founded, md, sector,
  financials: [{fy, revenue, assets, pat, net_worth}]
  kpis: {roe, roce, pe, pb, eps, debt_equity}
  strengths: [..], risks: [..], objectives: [..], promoters: [..], lead_managers: [..], registrar,
  docs: {drhp, rhp}
Derived on load: status, min_investment, subscribed_x, listing_gain_pct, current_price, current_gain_pct.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

PATH = Path("data") / "ipo.json"

_EX = {
    "financials": [{"fy": "FY24", "revenue": 412.0, "assets": 388.0, "pat": 21.4, "net_worth": 142.0},
                   {"fy": "FY25", "revenue": 518.0, "assets": 455.0, "pat": 34.9, "net_worth": 181.0},
                   {"fy": "FY26", "revenue": 655.0, "assets": 540.0, "pat": 48.2, "net_worth": 236.0}],
    "kpis": {"roe": 20.4, "roce": 24.1, "pe": 28.5, "pb": 4.9, "eps": 3.5, "debt_equity": 0.4},
    "strengths": ["Three straight years of revenue and profit growth", "Long-standing customer relationships in the top accounts",
                  "Capacity expansion funded from this issue rather than debt"],
    "risks": ["Top five customers make up over half of revenue", "Raw material prices are volatile and not fully passed through",
              "Working-capital cycle is long for the industry"],
    "objectives": ["Capital expenditure for a new facility", "Repayment of borrowings", "General corporate purposes"],
    "promoters": ["Promoter family (example)"], "lead_managers": ["Example Capital Markets", "Sample Securities"],
    "registrar": "Example Registrars Pvt Ltd", "docs": {"drhp": "https://www.sebi.gov.in/", "rhp": "https://www.sebi.gov.in/"},
}


def _mk(name: str, symbol: str, segment: str, open_: str, close: str, listing: str, lo: float, hi: float, lot: int, size: float,
        sub: dict | None = None, lopen: float | None = None, lclose: float | None = None, sector: str = "Industrials",
        about: str = "", **extra: Any) -> dict:
    """Build one fictional example entry with the full schema (flagged example)."""
    c = date.fromisoformat(close)
    e = {"name": name, "symbol": symbol, "slug": symbol.lower(), "segment": segment, "exchange": "NSE, BSE" if segment == "Mainboard" else "NSE SME",  # noqa: E501
         "price_lo": lo, "price_hi": hi, "lot": lot, "face_value": 10, "issue_size_cr": size, "fresh_cr": round(size * 0.6, 1), "ofs_cr": round(size * 0.4, 1),  # noqa: E501
         "open": open_, "close": close, "allotment": _add(c, 1), "refund": _add(c, 2), "credit": _add(c, 2), "listing": listing,
         "subscription": sub or {}, "listing_open": lopen, "listing_close": lclose, "sector": sector, "founded": 2011, "md": "Example MD (fictional)",  # noqa: E501
         "about": about or f"{name} is a fictional company used to show the shape of the IPO section until a data feed is wired. "
                           "Every number on this page is illustrative.",
         "example": True}
    e.update(_EX)
    e.update(extra)
    return e


def _add(d: date, days: int) -> str:
    from datetime import timedelta
    return (d + timedelta(days=days)).isoformat()


EXAMPLES = [
    _mk("Meridian Foods Ltd", "MERIDIAN", "Mainboard", "2026-09-17", "2026-09-21", "2026-09-24", 94, 99, 150, 1416.0,
        {"qib": 1.85, "nii": 2.4, "rii": 3.1, "employee": 1.2, "total": 2.35}, sector="Consumer",
        about="Meridian Foods (fictional) processes and packs staples for modern retail and quick commerce across western India."),
    _mk("Kaveri Precision Tools", "KAVERI", "SME", "2026-09-18", "2026-09-22", "2026-09-25", 60, 64, 2000, 46.0,
        {"qib": 0.9, "nii": 4.2, "rii": 6.8, "total": 3.4}, sector="Industrials"),
    _mk("Northline Logistics Ltd", "NORTHLINE", "Mainboard", "2026-09-24", "2026-09-26", "2026-10-01", 310, 326, 46, 2250.0, sector="Industrials"),  # noqa: E501
    _mk("Arcadia Health Labs", "ARCADIA", "Mainboard", "2026-09-29", "2026-10-01", "2026-10-07", 480, 505, 29, 3100.0, sector="Healthcare"),
    _mk("Bluewave Renewables SME", "BLUEWAVE", "SME", "2026-09-30", "2026-10-03", "2026-10-08", 108, 114, 1200, 62.0, sector="Energy"),
    _mk("Trident Fintech Ltd", "TRIDENTF", "Mainboard", "2026-09-10", "2026-09-12", "2026-09-19", 250, 262, 57, 1800.0,
        {"qib": 12.4, "nii": 18.9, "rii": 4.6, "employee": 2.1, "total": 11.2}, sector="Financials"),
    _mk("Saffron Textiles Ltd", "SAFFRON", "Mainboard", "2026-08-25", "2026-08-27", "2026-09-01", 140, 148, 100, 980.0,
        {"qib": 22.0, "nii": 40.5, "rii": 9.8, "total": 21.6}, 196.0, 189.5, sector="Consumer"),
    _mk("Orbit Semicon Ltd", "ORBITSEMI", "Mainboard", "2026-07-14", "2026-07-16", "2026-07-21", 820, 860, 17, 4200.0,
        {"qib": 48.2, "nii": 61.0, "rii": 14.3, "total": 39.7}, 1180.0, 1210.0, sector="Technology"),
    _mk("Harbour Cement Ltd", "HARBOURC", "Mainboard", "2026-06-02", "2026-06-04", "2026-06-09", 400, 420, 35, 2600.0,
        {"qib": 2.1, "nii": 1.4, "rii": 1.9, "total": 1.9}, 398.0, 372.0, sector="Materials"),
    _mk("Vista Hospitality SME", "VISTAH", "SME", "2026-05-12", "2026-05-14", "2026-05-19", 72, 76, 1600, 38.0,
        {"qib": 3.2, "nii": 25.6, "rii": 41.0, "total": 24.8}, 121.0, 118.0, sector="Consumer"),
    _mk("Pinecrest Pharma Ltd", "PINECREST", "Mainboard", "2026-03-03", "2026-03-05", "2026-03-10", 560, 590, 25, 3300.0,
        {"qib": 6.4, "nii": 3.1, "rii": 2.2, "total": 4.6}, 612.0, 588.0, sector="Healthcare"),
    _mk("Ridgeway Motors Ltd", "RIDGEWAY", "Mainboard", "2026-01-20", "2026-01-22", "2026-01-27", 900, 945, 15, 5100.0,
        {"qib": 1.3, "nii": 0.8, "rii": 1.1, "total": 1.15}, 905.0, 842.0, sector="Auto"),
    _mk("Lumen Software Ltd", "LUMENSOFT", "Mainboard", "2025-11-18", "2025-11-20", "2025-11-25", 210, 220, 68, 1500.0,
        {"qib": 31.0, "nii": 22.4, "rii": 7.9, "total": 22.1}, 300.0, 318.0, sector="Technology"),
    _mk("Delta Agro SME", "DELTAAGRO", "SME", "2025-09-08", "2025-09-10", "2025-09-15", 44, 46, 3000, 22.0,
        {"qib": 1.1, "nii": 9.2, "rii": 15.8, "total": 10.4}, 60.0, 55.0, sector="Consumer"),
]

# fictional "current" prices for example listed issues so the tracker has a profit/loss column offline
EXAMPLE_PRICES = {"SAFFRON": 205.0, "ORBITSEMI": 1420.0, "HARBOURC": 351.0, "VISTAH": 96.0, "PINECREST": 640.0, "RIDGEWAY": 790.0,
                  "LUMENSOFT": 402.0, "DELTAAGRO": 48.5}


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _read() -> tuple[list[dict], str]:
    if PATH.exists():
        try:
            return json.loads(PATH.read_text(encoding="utf-8")), str(PATH)
        except json.JSONDecodeError:
            return [], f"{PATH} (invalid JSON)"
    return [json.loads(json.dumps(e)) for e in EXAMPLES], "examples (no data/ipo.json yet)"


def _derive(e: dict, today: date) -> dict:
    e.setdefault("slug", slugify(e.get("symbol") or e["name"]))
    e.setdefault("segment", "Mainboard")
    e.setdefault("subscription", {})
    try:
        o, c = date.fromisoformat(e["open"]), date.fromisoformat(e["close"])
        li = date.fromisoformat(e["listing"]) if e.get("listing") else None
        has_px = (e.get("listing_close") if e.get("listing_close") is not None else e.get("listing_price")) is not None
        listed = bool(li) and (today > li or (today == li and has_px))
        e["status"] = "listed" if listed else "closed" if today > c else "open" if today >= o else "upcoming"
    except (KeyError, ValueError):
        e.setdefault("status", "upcoming")
    hi = e.get("price_hi") or 0
    e["min_investment"] = round((e.get("lot") or 0) * hi)
    sub = e["subscription"]
    e["subscribed_x"] = sub.get("total") if sub.get("total") is not None else e.get("subscribed_x")
    lc = e.get("listing_close") if e.get("listing_close") is not None else e.get("listing_price")
    e["listing_price"] = lc
    e["listing_gain_pct"] = round((lc / hi - 1) * 100, 2) if lc and hi else None
    e["days_to_open"] = (date.fromisoformat(e["open"]) - today).days if e.get("open") else None
    return e


def _with_prices(entries: list[dict], quotes: Callable[[list[str]], dict] | None) -> None:
    listed = [e for e in entries if e["status"] == "listed" and e.get("symbol")]
    live: dict = {}
    if quotes and any(not e.get("example") for e in listed):
        try:
            live = quotes([e["symbol"] for e in listed if not e.get("example")])
        except Exception:  # noqa: BLE001 - quotes are best effort here
            live = {}
    for e in listed:
        px = None
        if e.get("example"):
            px = EXAMPLE_PRICES.get(e["symbol"])
        else:
            q = live.get(e["symbol"])
            px = getattr(q, "ltp", None) if q is not None else None
        e["current_price"] = px
        hi = e.get("price_hi") or 0
        e["current_gain_pct"] = round((px / hi - 1) * 100, 2) if px and hi else None


def load(today: date | None = None, quotes: Callable[[list[str]], dict] | None = None) -> dict:
    today = today or date.today()
    entries, source = _read()
    entries = [_derive(e, today) for e in entries]
    _with_prices(entries, quotes)
    def part(status: str, key: str, newest_first: bool) -> list[dict]:
        return sorted([e for e in entries if e["status"] == status], key=lambda e: e.get(key) or "", reverse=newest_first)

    entries = part("open", "close", False) + part("upcoming", "open", False) + part("closed", "close", True) + part("listed", "listing", True)  # noqa: E501
    listed = [e for e in entries if e["status"] == "listed" and e.get("listing_gain_pct") is not None]
    stats = {"open": sum(e["status"] == "open" for e in entries), "upcoming": sum(e["status"] == "upcoming" for e in entries),
             "closed": sum(e["status"] == "closed" for e in entries), "listed": sum(e["status"] == "listed" for e in entries),
             "listed_gain": sum(e["listing_gain_pct"] > 0 for e in listed), "listed_loss": sum(e["listing_gain_pct"] <= 0 for e in listed)}
    return {"source": source, "asof": today.isoformat(), "stats": stats, "entries": entries}


def detail(slug: str, today: date | None = None, quotes: Callable[[list[str]], dict] | None = None,
           headlines: list[dict] | None = None) -> dict | None:
    data = load(today, quotes)
    e = next((x for x in data["entries"] if x.get("slug") == slug or (x.get("symbol") or "").lower() == slug.lower()), None)
    if e is None:
        return None
    e = dict(e)
    e["timeline"] = timeline(e, today or date.today())
    e["agent"] = agent(e, headlines or [])
    e["source"] = data["source"]
    return e


def timeline(e: dict, today: date) -> list[dict]:
    steps = [("open", "Bidding opens"), ("close", "Bidding closes"), ("allotment", "Allotment finalised"),
             ("refund", "Refunds initiated"), ("credit", "Shares credited to demat"), ("listing", "Listing on the exchange")]
    out = []
    for key, label in steps:
        d = e.get(key)
        try:
            dd = date.fromisoformat(d) if d else None
        except ValueError:
            dd = None
        state = "tbd" if dd is None else "done" if dd < today else "today" if dd == today else "upcoming"
        out.append({"key": key, "label": label, "date": d, "state": state})
    return out


# ---- IPO agent, rules v0 ---------------------------------------------------------------------------
def _cagr(a: float | None, b: float | None, years: int) -> float | None:
    if not a or not b or a <= 0 or b <= 0 or years <= 0:
        return None
    return round(((b / a) ** (1 / years) - 1) * 100, 1)


def agent(e: dict, headlines: list[dict]) -> dict:
    """Five transparent checks, each a vote in [-1, 1] with a confidence and a reading. Not advice."""
    checks: list[dict] = []
    sub = e.get("subscription") or {}
    total, qib = sub.get("total"), sub.get("qib")
    if total is None:
        checks.append({"name": "demand", "signal": 0.0, "confidence": 0.0, "reading": "no subscription data yet (bidding not open or feed missing)"})  # noqa: E501
    else:
        s = max(-1.0, min(1.0, (total - 1.0) / 10.0)) if total >= 1 else -0.8
        q = f" · QIB {qib:.1f}x" if qib is not None else ""
        checks.append({"name": "demand", "signal": round(s, 2), "confidence": 0.9 if e["status"] != "open" else 0.6,
                       "reading": f"{total:.1f}x overall{q}" + (" · institutions lead" if qib and qib >= (sub.get('rii') or 0) else " · retail-led")})  # noqa: E501
    fin = e.get("financials") or []
    if len(fin) >= 2:
        rev = _cagr(fin[0].get("revenue"), fin[-1].get("revenue"), len(fin) - 1)
        pat = _cagr(fin[0].get("pat"), fin[-1].get("pat"), len(fin) - 1)
        g = ((rev or 0) + (pat or 0)) / 2
        checks.append({"name": "growth", "signal": round(max(-1.0, min(1.0, (g - 10) / 30)), 2), "confidence": 0.8,
                       "reading": f"revenue CAGR {rev if rev is not None else '—'} % · PAT CAGR {pat if pat is not None else '—'} % over {len(fin) - 1} years"})  # noqa: E501
    else:
        checks.append({"name": "growth", "signal": 0.0, "confidence": 0.0, "reading": "financials not loaded"})
    k = e.get("kpis") or {}
    pe = k.get("pe")
    if pe:
        checks.append({"name": "valuation", "signal": round(max(-1.0, min(1.0, (30 - pe) / 30)), 2), "confidence": 0.5,
                       "reading": f"P/E {pe} at the top of the band · P/B {k.get('pb', '—')} · ROE {k.get('roe', '—')} %"})
    else:
        checks.append({"name": "valuation", "signal": 0.0, "confidence": 0.0, "reading": "no valuation metrics"})
    size = e.get("issue_size_cr") or 0
    ofs = e.get("ofs_cr") or 0
    share = ofs / size if size else 0
    checks.append({"name": "issue structure", "signal": round(0.6 - share, 2), "confidence": 0.6,
                   "reading": f"{share * 100:.0f} % of the issue is offer for sale" + (" · mostly promoters cashing out" if share > 0.6 else " · fresh money goes into the business")})  # noqa: E501
    words = [w for w in re.findall(r"[A-Za-z]{4,}", e.get("name", "")) if w.lower() not in {"limited", "india", "ltd"}][:2]
    hits = [h for h in headlines if words and all(w.lower() in (h.get("title", "") + " " + h.get("description", "")).lower() for w in words)]  # noqa: E501
    good = sum(1 for h in hits if h.get("impact") == "good")
    bad = sum(1 for h in hits if h.get("impact") == "bad")
    if hits:
        checks.append({"name": "news", "signal": round(max(-1.0, min(1.0, (good - bad) / max(1, len(hits)))), 2), "confidence": min(0.7, 0.2 + 0.1 * len(hits)),  # noqa: E501
                       "reading": f"{len(hits)} headlines mention the company · {good} good · {bad} bad"})
    else:
        checks.append({"name": "news", "signal": 0.0, "confidence": 0.0, "reading": "no headlines on the wire mention the company"})
    wsum = sum(c["confidence"] for c in checks) or 1.0
    score = round(sum(c["signal"] * c["confidence"] for c in checks) / wsum, 2)
    coverage = round(sum(1 for c in checks if c["confidence"] > 0) / len(checks), 2)
    stance = "positive" if score > 0.25 else "cautious" if score < -0.2 else "neutral"
    horizon = "listing day" if e["status"] in ("open", "upcoming", "closed") else "post-listing"
    return {"model": "rules v0", "score": score, "stance": stance, "coverage": coverage, "horizon": horizon, "checks": checks,
            "note": "Five checks on demand, growth, valuation, issue structure and news, weighted by how much data each had. "
                    "A stance is a summary of those checks, not a recommendation to apply. Read the RHP."}


# ---- performance tracker ---------------------------------------------------------------------------
def performance(year: int | None = None, segment: str | None = None, today: date | None = None,
                quotes: Callable[[list[str]], dict] | None = None) -> dict:
    data = load(today, quotes)
    rows = [e for e in data["entries"] if e["status"] == "listed" and e.get("listing")]
    years = sorted({int(e["listing"][:4]) for e in rows}, reverse=True)
    if year:
        rows = [e for e in rows if e["listing"].startswith(str(year))]
    if segment:
        rows = [e for e in rows if e.get("segment") == segment]
    out = [{"name": e["name"], "symbol": e.get("symbol"), "slug": e["slug"], "segment": e["segment"], "domain": e.get("domain"), "example": e.get("example", False),  # noqa: E501
            "listing": e["listing"], "issue_price": e.get("price_hi"), "listing_open": e.get("listing_open"), "listing_close": e.get("listing_close"),  # noqa: E501
            "listing_gain_pct": e.get("listing_gain_pct"), "current_price": e.get("current_price"), "current_gain_pct": e.get("current_gain_pct"),  # noqa: E501
            "subscribed_x": e.get("subscribed_x")} for e in rows]
    out.sort(key=lambda r: r["listing"], reverse=True)
    lg = [r["listing_gain_pct"] for r in out if r["listing_gain_pct"] is not None]
    cg = [r["current_gain_pct"] for r in out if r["current_gain_pct"] is not None]
    best = max(out, key=lambda r: r["listing_gain_pct"] or -1e9) if lg else None
    worst = min(out, key=lambda r: r["listing_gain_pct"] if r["listing_gain_pct"] is not None else 1e9) if lg else None
    summary = {"count": len(out), "avg_listing_gain": round(sum(lg) / len(lg), 2) if lg else None, "avg_current_gain": round(sum(cg) / len(cg), 2) if cg else None,  # noqa: E501
               "in_gain": sum(1 for g in lg if g > 0), "in_loss": sum(1 for g in lg if g <= 0),
               "best": {"name": best["name"], "slug": best["slug"], "gain": best["listing_gain_pct"]} if best else None,
               "worst": {"name": worst["name"], "slug": worst["slug"], "gain": worst["listing_gain_pct"]} if worst else None}
    return {"source": data["source"], "year": year, "segment": segment, "years": years, "summary": summary, "rows": out,
            "note": "Issue price is the top of the band. Listing gain compares the listing day close with the issue price; "
                    "profit / loss compares the current price with the issue price. Splits, bonuses and dividends are not adjusted."}
