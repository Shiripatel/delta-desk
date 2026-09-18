"""Yahoo Finance quote provider: real NSE prices, about 15 minutes delayed, no account or key.

Uses the public chart endpoint (https://query1.finance.yahoo.com/v8/finance/chart/<symbol>) and reads the
`meta` block: regularMarketPrice, chartPreviousClose, day high/low, volume, time. One request per symbol,
fetched in a small thread pool and cached for `ttl` seconds, so a page polling every 3 s costs nothing
between refreshes. Unofficial endpoint: fine for personal use, not for redistribution, and it can change.

Coverage: NSE stocks and ETFs (`<SYMBOL>.NS`), the main indices, currency pairs (`USDINR=X`).
Not available: NIFTY Midcap Select, index futures, option chains. Those keys return no quote.
"""
from __future__ import annotations

import concurrent.futures
import json
import threading
import time
import urllib.parse
import urllib.request

from deltadesk.markets.quotes import Quote
from deltadesk.markets.universe import FX, INDICES

INDEX_SYMBOLS = {"NIFTY50": "^NSEI", "BANKNIFTY": "^NSEBANK", "SENSEX": "^BSESN", "INDIAVIX": "^INDIAVIX",
                 "FINNIFTY": "NIFTY_FIN_SERVICE.NS", "NIFTYNEXT50": "^NSMIDCP"}   # ^NSMIDCP is Yahoo's NIFTY NEXT 50
FX_KEYS = {f[0] for f in FX}
CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=5m"


class YahooQuotes:
    name = "yahoo"
    delay_min = 15
    note = "Yahoo Finance · about 15 min delayed · no account"

    def __init__(self, ttl: float = 60.0, workers: int = 8, timeout: float = 10.0) -> None:
        self.ttl = ttl
        self.workers = workers
        self.timeout = timeout
        self._cache: dict[str, tuple[float, Quote]] = {}
        self._lock = threading.Lock()
        self.errors: dict[str, str] = {}
        self.fetches = 0

    # ---- mapping ----------------------------------------------------------------------------
    @staticmethod
    def map_symbol(k: str) -> str | None:
        if k in INDICES:
            return INDEX_SYMBOLS.get(k)
        if k in FX_KEYS:
            return f"{k}=X"
        if k.startswith("FUT:"):
            return None
        return f"{k}.NS"

    # ---- fetching ---------------------------------------------------------------------------
    def _fetch_chart(self, sym: str) -> dict:
        url = CHART.format(sym=urllib.parse.quote(sym, safe="^="))
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (DeltaDesk)"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.load(r)
        result = (data.get("chart") or {}).get("result") or []
        if not result:
            raise ValueError("empty chart result")
        return result[0].get("meta") or {}

    def _quote_from_meta(self, key: str, meta: dict) -> Quote | None:
        ltp = meta.get("regularMarketPrice")
        if ltp is None:
            return None
        prev = meta.get("chartPreviousClose") or meta.get("previousClose") or ltp
        chg = float(ltp) - float(prev)
        d = 4 if key in FX_KEYS else 2
        return Quote(key=key, ltp=round(float(ltp), d), prev_close=round(float(prev), d), open=round(float(prev), d),
                     high=round(float(meta.get("regularMarketDayHigh") or ltp), d),
                     low=round(float(meta.get("regularMarketDayLow") or ltp), d),
                     volume=int(meta.get("regularMarketVolume") or 0), change=round(chg, d),
                     change_pct=round(chg / float(prev) * 100, 2) if prev else 0.0,
                     ts=float(meta.get("regularMarketTime") or time.time()))

    def _refresh(self, key: str) -> None:
        sym = self.map_symbol(key)
        if sym is None:
            return
        try:
            q = self._quote_from_meta(key, self._fetch_chart(sym))
            self.fetches += 1
        except Exception as e:  # noqa: BLE001 - keep the last good quote, remember the error
            with self._lock:
                self.errors[key] = f"{type(e).__name__}: {str(e)[:80]}"
            return
        if q is not None:
            with self._lock:
                self._cache[key] = (time.time(), q)
                self.errors.pop(key, None)

    def quotes(self, keys: list[str]) -> dict[str, Quote]:
        now = time.time()
        with self._lock:
            stale = [k for k in keys if k not in self._cache or now - self._cache[k][0] > self.ttl]
        if stale:
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as ex:
                list(ex.map(self._refresh, stale))
        with self._lock:
            return {k: self._cache[k][1] for k in keys if k in self._cache}
