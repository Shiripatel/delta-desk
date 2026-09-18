"""Calendars: F&O expiries (computed), financial events, earnings, and FII/DII institutional flows.

Computed rows are derived from exchange rules and are marked `computed`. User-maintained rows live in
JSON files under data/ and are the only source for dated events that cannot be derived:

  data/calendar.json  [{"date": "YYYY-MM-DD", "title": "...", "kind": "holiday|rbi|budget|macro|exchange", "note": "..."}]
  data/earnings.json  [{"symbol": "...", "company": "...", "date": "YYYY-MM-DD", "quarter": "Q2 FY27", "time": "post-market"}]
  data/flows.json     [{"date": "YYYY-MM-DD", "fii_net_cr": -1234.5, "dii_net_cr": 2345.6}]

Sources to fill them: NSE holiday circular and F&O expiry circulars; NSE corporate announcements and
board-meeting pages for results dates; NSE "FII/DII trading activity" daily report (also on SEBI and
via most broker apps). None has an official free API; a small daily job that scrapes or copies the
official pages is the usual answer. Until the files exist, example rows are shown and flagged.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from deltadesk.markets.universe import last_weekday_of_month

DATA = Path("data")


def _load(name: str, examples: list[dict]) -> tuple[list[dict], str]:
    f = DATA / name
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8")), str(f)
        except json.JSONDecodeError:
            return [], f"{f} (invalid JSON)"
    return [dict(e, example=True) for e in examples], f"examples (no {f} yet)"


def _holidays(cal_rows: list[dict]) -> set[date]:
    out = set()
    for r in cal_rows:
        if r.get("kind") == "holiday":
            try:
                out.add(date.fromisoformat(r["date"]))
            except (KeyError, ValueError):
                pass
    return out


def _prev_trading_day(d: date, holidays: set[date]) -> date:
    while d.weekday() > 4 or d in holidays:
        d -= timedelta(days=1)
    return d


def expiries(today: date, holidays: set[date] | None = None, weeks: int = 8) -> list[dict]:
    """NIFTY weekly on Tuesday, SENSEX weekly on Thursday, NSE index monthlies on the last Tuesday.
    A holiday moves the expiry to the previous trading day. Verify against the current exchange circular."""
    holidays = holidays or set()
    rows = []
    d = today
    for _ in range(weeks):
        tue = d + timedelta(days=(1 - d.weekday()) % 7)
        thu = d + timedelta(days=(3 - d.weekday()) % 7)
        rows.append({"date": _prev_trading_day(tue, holidays).isoformat(), "title": "NIFTY weekly expiry",
                     "kind": "expiry", "computed": True})
        rows.append({"date": _prev_trading_day(thu, holidays).isoformat(), "title": "SENSEX weekly expiry (BSE)",
                     "kind": "expiry", "computed": True})
        d = tue + timedelta(days=1)
    y, m = today.year, today.month
    for _ in range(3):
        e = _prev_trading_day(last_weekday_of_month(y, m, 1), holidays)
        if e >= today:
            rows.append({"date": e.isoformat(), "title": "Monthly expiry: NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY futures and options",
                         "kind": "expiry", "computed": True})
        m += 1
        if m == 13:
            y, m = y + 1, 1
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: (r["date"], r["title"])):
        k = (r["date"], r["title"])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


CAL_EXAMPLES = [
    {"date": "2026-10-02", "title": "Gandhi Jayanti · market holiday (sample entry)", "kind": "holiday"},
    {"date": "2026-10-07", "title": "RBI monetary policy decision (sample entry, verify date)", "kind": "rbi"},
]
EARN_EXAMPLES = [
    {"symbol": "TCS", "company": "Tata Consultancy Services (sample entry)", "date": "2026-10-09", "quarter": "Q2 FY27",
     "time": "post-market"},
    {"symbol": "HDFCBANK", "company": "HDFC Bank (sample entry)", "date": "2026-10-18", "quarter": "Q2 FY27", "time": "mid-day"},
    {"symbol": "RELIANCE", "company": "Reliance Industries (sample entry)", "date": "2026-10-17", "quarter": "Q2 FY27",
     "time": "post-market"},
]
FLOW_EXAMPLES = [
    {"date": "2026-09-11", "fii_net_cr": -1850.4, "dii_net_cr": 2410.7},
    {"date": "2026-09-14", "fii_net_cr": -920.1, "dii_net_cr": 1305.2},
    {"date": "2026-09-15", "fii_net_cr": 640.8, "dii_net_cr": 890.5},
    {"date": "2026-09-16", "fii_net_cr": -2210.0, "dii_net_cr": 2985.3},
    {"date": "2026-09-17", "fii_net_cr": 310.2, "dii_net_cr": 1120.9},
]


def financial_calendar(today: date | None = None) -> dict:
    today = today or date.today()
    rows, source = _load("calendar.json", CAL_EXAMPLES)
    hol = _holidays(rows)
    allrows = [r for r in rows if r.get("date", "") >= today.isoformat()] + expiries(today, hol)
    allrows.sort(key=lambda r: (r.get("date", ""), r.get("kind", "")))
    return {"source": source + " + computed expiries", "today": today.isoformat(), "entries": allrows}


def earnings(today: date | None = None) -> dict:
    today = today or date.today()
    rows, source = _load("earnings.json", EARN_EXAMPLES)
    rows = [r for r in rows if r.get("date", "") >= (today - timedelta(days=7)).isoformat()]
    rows.sort(key=lambda r: r.get("date", ""))
    return {"source": source, "entries": rows}


def flows() -> dict:
    rows, source = _load("flows.json", FLOW_EXAMPLES)
    rows.sort(key=lambda r: r.get("date", ""))
    for r in rows:
        r["net_cr"] = round(float(r.get("fii_net_cr", 0)) + float(r.get("dii_net_cr", 0)), 1)
    tot_f = round(sum(float(r.get("fii_net_cr", 0)) for r in rows), 1)
    tot_d = round(sum(float(r.get("dii_net_cr", 0)) for r in rows), 1)
    return {"source": source, "entries": rows[-30:], "totals": {"fii_net_cr": tot_f, "dii_net_cr": tot_d, "days": len(rows)}}
