"""Upstox instrument master: the daily list of every tradable instrument with its feed key.

Downloaded from https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz (and BSE) and
cached under data/upstox_<EXCH>.json.gz for the day. Keys look like "NSE_EQ|INE040A01034",
"NSE_INDEX|Nifty 50", "NSE_FO|49480". No credentials are needed to download the master.
"""
from __future__ import annotations

import gzip
import json
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
URL = "https://assets.upstox.com/market-quote/instruments/exchange/{exch}.json.gz"
CACHE = Path("data")
INDEX_NAMES = {"NIFTY50": "Nifty 50", "BANKNIFTY": "Nifty Bank", "FINNIFTY": "Nifty Fin Service",
               "MIDCPNIFTY": "NIFTY MID SELECT", "NIFTYNEXT50": "Nifty Next 50", "INDIAVIX": "India VIX",
               "SENSEX": "SENSEX"}
FO_UNDERLYING = {"NIFTY50": "NIFTY", "BANKNIFTY": "BANKNIFTY", "FINNIFTY": "FINNIFTY", "MIDCPNIFTY": "MIDCPNIFTY"}


def _expiry_date(v) -> date | None:
    if v in (None, "", 0):
        return None
    try:
        if isinstance(v, (int, float)) or str(v).isdigit():
            return datetime.fromtimestamp(int(v) / 1000, IST).date()
        return date.fromisoformat(str(v)[:10])
    except (ValueError, OSError):
        return None


class InstrumentMaster:
    def __init__(self, exchanges: tuple[str, ...] = ("NSE",), max_age_hours: float = 20.0) -> None:
        self.exchanges = exchanges
        self.max_age = max_age_hours * 3600
        self.rows: list[dict] = []
        self.by_key: dict[str, dict] = {}
        self._eq: dict[str, dict] = {}       # trading symbol -> row (NSE_EQ)
        self._idx: dict[str, dict] = {}      # lower-case index name -> row
        self._fo: dict[str, list[dict]] = {}  # underlying symbol -> rows

    # ---- loading --------------------------------------------------------------------------
    def load(self, download: bool = True) -> int:
        rows: list[dict] = []
        for exch in self.exchanges:
            p = CACHE / f"upstox_{exch}.json.gz"
            fresh = p.exists() and time.time() - p.stat().st_mtime < self.max_age
            if not fresh and download:
                try:
                    req = urllib.request.Request(URL.format(exch=exch), headers={"User-Agent": "Mozilla/5.0 (DeltaDesk)"})
                    with urllib.request.urlopen(req, timeout=60) as r:
                        CACHE.mkdir(parents=True, exist_ok=True)
                        p.write_bytes(r.read())
                except Exception:
                    if not p.exists():
                        continue
            if p.exists():
                with gzip.open(p, "rt", encoding="utf-8") as f:
                    rows.extend(json.load(f))
        self.index(rows)
        return len(rows)

    def index(self, rows: list[dict]) -> None:
        self.rows = rows
        self.by_key = {r["instrument_key"]: r for r in rows if "instrument_key" in r}
        self._eq, self._idx, self._fo = {}, {}, {}
        for r in rows:
            seg = r.get("segment", "")
            if seg == "NSE_EQ" or seg == "BSE_EQ":
                self._eq.setdefault(r.get("trading_symbol", ""), r)
            elif seg.endswith("_INDEX"):
                self._idx[str(r.get("name", "")).lower()] = r
            elif seg.endswith("_FO"):
                self._fo.setdefault(str(r.get("underlying_symbol") or r.get("name", "")), []).append(r)

    # ---- lookups --------------------------------------------------------------------------
    def equity_key(self, symbol: str) -> str | None:
        r = self._eq.get(symbol)
        return r["instrument_key"] if r else None

    def index_key(self, code_or_name: str) -> str | None:
        name = INDEX_NAMES.get(code_or_name, code_or_name)
        r = self._idx.get(name.lower())
        return r["instrument_key"] if r else None

    def fo(self, underlying: str, kind: str | None = None, expiry: date | None = None) -> list[dict]:
        out = []
        for r in self._fo.get(FO_UNDERLYING.get(underlying, underlying), []):
            if kind and r.get("instrument_type") != kind:
                continue
            if expiry and _expiry_date(r.get("expiry")) != expiry:
                continue
            out.append(r)
        return out

    def expiries(self, underlying: str, kind: str = "CE") -> list[date]:
        return sorted({e for e in (_expiry_date(r.get("expiry")) for r in self.fo(underlying, kind)) if e})

    def nearest_expiry(self, underlying: str, today: date | None = None, kind: str = "CE") -> date | None:
        today = today or datetime.now(IST).date()
        return next((e for e in self.expiries(underlying, kind) if e >= today), None)

    def futures_key(self, underlying: str, expiry: date) -> str | None:
        rows = self.fo(underlying, "FUT", expiry)
        return rows[0]["instrument_key"] if rows else None

    def chain(self, underlying: str, expiry: date, centre: float, step: float, each_side: int) -> list[dict]:
        lo, hi = centre - each_side * step, centre + each_side * step
        out = []
        for r in self.fo(underlying, None, expiry):
            if r.get("instrument_type") not in ("CE", "PE"):
                continue
            k = float(r.get("strike_price") or 0)
            if lo <= k <= hi:
                out.append(r)
        return sorted(out, key=lambda r: (float(r.get("strike_price") or 0), r.get("instrument_type", "")))
