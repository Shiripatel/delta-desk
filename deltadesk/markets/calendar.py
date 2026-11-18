"""Calendars: F&O expiries (computed), financial events, earnings, and FII/DII institutional flows.

Computed rows are derived from exchange rules and are marked `computed`. User-maintained rows live in
JSON files under data/ and are the only source for dated events that cannot be derived:

  data/calendar.json  [{"date": "YYYY-MM-DD", "title": "...", "kind": "holiday|rbi|budget|macro|exchange", "note": "..."}]
  data/earnings.json  [{"symbol": "...", "company": "...", "date": "YYYY-MM-DD", "quarter": "Q2 FY27", "time": "post-market"}]
  data/flows.json     [{"date": "YYYY-MM-DD", "fii_net_cr": -1234.5, "dii_net_cr": 2345.6}]

Sources to fill them: NSE holiday circular and F&O expiry circulars; NSE corporate announcements and
board-meeting pages for results dates; NSE "FII/DII trading activity" daily report (also on SEBI and
via most broker apps). None has an official free API; a small daily job that scrapes or copies the
official pages is the usual answer. Until the files exist, sample rows dated relative to today are shown and flagged.
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


def _weekday_on_or_after(d: date) -> date:
    while d.weekday() > 4:
        d += timedelta(days=1)
    return d


def _trading_days_back(today: date, n: int) -> list[date]:
    out, d = [], today - timedelta(days=1)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def quarter_label(today: date) -> str:
    """The quarter whose results are being reported around `today` (Indian fiscal year, April to March):
    quarters end in March, June, September and December; results follow in the next one to two months."""
    m = today.month
    ended = ((m - 1) // 3) * 3          # month the last quarter ended: 0 (Dec), 3 (Mar), 6 (Jun), 9 (Sep)
    q = {0: 3, 3: 4, 6: 1, 9: 2}[ended]
    fy_end_year = today.year + (1 if ended in (6, 9) else 0)   # June and September quarters belong to the FY ending next March
    return f"Q{q} FY{fy_end_year % 100:02d}"


def sample_calendar(today: date) -> list[dict]:
    """Illustrative rows, dated relative to today so they never go stale. No sample holiday: a holiday moves
    computed expiries, and an invented one would show wrong expiry dates."""
    return [{"date": _weekday_on_or_after(today + timedelta(days=9)).isoformat(),
             "title": "RBI monetary policy decision (sample entry, verify date)", "kind": "rbi"},
            {"date": _weekday_on_or_after(today + timedelta(days=16)).isoformat(),
             "title": "CPI inflation print (sample entry, verify date)", "kind": "macro"}]


def sample_earnings(today: date) -> list[dict]:
    q = quarter_label(today)
    return [{"symbol": "TCS", "company": "Tata Consultancy Services (sample entry)",
             "date": _weekday_on_or_after(today + timedelta(days=3)).isoformat(), "quarter": q, "time": "post-market"},
            {"symbol": "RELIANCE", "company": "Reliance Industries (sample entry)",
             "date": _weekday_on_or_after(today + timedelta(days=10)).isoformat(), "quarter": q, "time": "post-market"},
            {"symbol": "HDFCBANK", "company": "HDFC Bank (sample entry)",
             "date": _weekday_on_or_after(today + timedelta(days=11)).isoformat(), "quarter": q, "time": "mid-day"}]


def sample_flows(today: date) -> list[dict]:
    vals = [(-1850.4, 2410.7), (-920.1, 1305.2), (640.8, 890.5), (-2210.0, 2985.3), (310.2, 1120.9)]
    return [{"date": d.isoformat(), "fii_net_cr": f, "dii_net_cr": i} for d, (f, i) in zip(_trading_days_back(today, 5), vals, strict=True)]


def financial_calendar(today: date | None = None) -> dict:
    today = today or date.today()
    rows, source = _load("calendar.json", sample_calendar(today))
    hol = _holidays(rows)
    allrows = [r for r in rows if r.get("date", "") >= today.isoformat()] + expiries(today, hol)
    allrows.sort(key=lambda r: (r.get("date", ""), r.get("kind", "")))
    return {"source": source + " + computed expiries", "today": today.isoformat(), "entries": allrows}


def earnings(today: date | None = None) -> dict:
    today = today or date.today()
    rows, source = _load("earnings.json", sample_earnings(today))
    rows = [r for r in rows if r.get("date", "") >= (today - timedelta(days=7)).isoformat()]
    rows.sort(key=lambda r: r.get("date", ""))
    return {"source": source, "entries": rows}


def flows(today: date | None = None) -> dict:
    today = today or date.today()
    rows, source = _load("flows.json", sample_flows(today))
    rows.sort(key=lambda r: r.get("date", ""))
    for r in rows:
        r["net_cr"] = round(float(r.get("fii_net_cr", 0)) + float(r.get("dii_net_cr", 0)), 1)
    tot_f = round(sum(float(r.get("fii_net_cr", 0)) for r in rows), 1)
    tot_d = round(sum(float(r.get("dii_net_cr", 0)) for r in rows), 1)
    return {"source": source, "entries": rows[-30:], "totals": {"fii_net_cr": tot_f, "dii_net_cr": tot_d, "days": len(rows)}}
