"""IPO calendar.

There is no official free IPO API. Sources, in order of preference:
  1. A JSON file you maintain or a job fills: data/ipo.json  (schema below). This is what ships.
  2. NSE public endpoints behind nseindia.com (e.g. /api/ipo-current-issue, /api/all-upcoming-issues?category=ipo).
     They need browser-like headers and cookies, change without notice, and the site's terms restrict
     automated use, so treat any fetcher as best-effort and never as the only source.
  3. BSE's IPO pages, SEBI's DRHP filings, and paid vendors (TrueData, Trendlyne, Tickertape APIs).
  4. Broker apps show IPOs and accept UPI bids, but none of the retail broker APIs (Kite, Upstox, Dhan,
     Angel) expose an IPO endpoint at the time of writing. Bidding stays in the broker app.

Schema of one entry:
  {"name": "...", "symbol": "...", "segment": "Mainboard|SME", "open": "YYYY-MM-DD", "close": "YYYY-MM-DD",
   "listing": "YYYY-MM-DD", "price_lo": 0, "price_hi": 0, "lot": 0, "issue_size_cr": 0, "status": "upcoming|open|closed|listed"}
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

PATH = Path("data") / "ipo.json"

EXAMPLES = [
    {"name": "Example Retail Ltd (sample entry)", "symbol": "EXAMPLE1", "segment": "Mainboard", "open": "2026-09-22",
     "close": "2026-09-24", "listing": "2026-09-29", "price_lo": 95, "price_hi": 100, "lot": 150,
     "issue_size_cr": 1200, "status": "upcoming", "example": True},
    {"name": "Sample Components SME (sample entry)", "symbol": "SAMPLE2", "segment": "SME", "open": "2026-09-16",
     "close": "2026-09-18", "listing": "2026-09-23", "price_lo": 60, "price_hi": 64, "lot": 2000,
     "issue_size_cr": 45, "status": "open", "example": True},
]


def load(today: date | None = None) -> dict:
    today = today or date.today()
    if PATH.exists():
        try:
            entries = json.loads(PATH.read_text(encoding="utf-8"))
            source = str(PATH)
        except json.JSONDecodeError:
            entries, source = [], f"{PATH} (invalid JSON)"
    else:
        entries, source = [dict(e) for e in EXAMPLES], "examples (no data/ipo.json yet)"
    for e in entries:
        try:
            o, c = date.fromisoformat(e["open"]), date.fromisoformat(e["close"])
            l = date.fromisoformat(e["listing"]) if e.get("listing") else None
            e["status"] = "listed" if l and today >= l else "closed" if today > c else "open" if today >= o else "upcoming"
        except (KeyError, ValueError):
            e.setdefault("status", "upcoming")
    order = {"open": 0, "upcoming": 1, "closed": 2, "listed": 3}
    entries.sort(key=lambda e: (order.get(e["status"], 9), e.get("open", "")))
    return {"source": source, "entries": entries}
