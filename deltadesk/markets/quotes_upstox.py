"""Upstox quote provider for the markets page and watchlists (REST full quotes, free plan).

Keys used by the page (stock symbol, index code, ETF symbol, FUT:code:expiry) are mapped to Upstox
instrument keys through the instrument master. Up to 500 keys per request; results are cached for two
seconds so several page widgets polling at once share one call. Currency pairs need NCD_FO futures keys
and are left for a later day (they return no quote for now).
"""
from __future__ import annotations

import time
from datetime import date

from deltadesk.auth import load_token
from deltadesk.markets.quotes import Quote
from deltadesk.markets.universe import INDICES
from deltadesk.markets.upstox_master import FO_UNDERLYING, InstrumentMaster


class UpstoxQuotes:
    name = "upstox"

    def __init__(self, master: InstrumentMaster | None = None, ttl: float = 2.0) -> None:
        import upstox_client  # lazy

        token = load_token("upstox")
        if not token:
            raise RuntimeError("No Upstox token. Run: uv run deltadesk login upstox")
        cfg = upstox_client.Configuration()
        cfg.access_token = token
        self.api = upstox_client.MarketQuoteApi(upstox_client.ApiClient(cfg))
        self.master = master or InstrumentMaster()
        if not self.master.rows:
            self.master.load()
        self.ttl = ttl
        self._cache: dict[str, tuple[float, Quote]] = {}

    def map_key(self, k: str) -> str | None:
        if k in INDICES:
            return self.master.index_key(k)
        if k.startswith("FUT:"):
            _, code, exp = k.split(":", 2)
            return self.master.futures_key(FO_UNDERLYING.get(code, code), date.fromisoformat(exp))
        return self.master.equity_key(k)

    def quotes(self, keys: list[str]) -> dict[str, Quote]:
        now = time.time()
        out: dict[str, Quote] = {}
        need: dict[str, str] = {}
        for k in keys:
            c = self._cache.get(k)
            if c and now - c[0] < self.ttl:
                out[k] = c[1]
                continue
            ik = self.map_key(k)
            if ik:
                need[ik] = k
        for i in range(0, len(need), 500):
            batch = list(need)[i:i + 500]
            try:
                resp = self.api.get_full_market_quote(symbol=",".join(batch), api_version="2.0")
            except Exception:  # noqa: BLE001 - one failed batch must not break the page
                continue
            for v in (resp.data or {}).values():
                ik = getattr(v, "instrument_token", None)
                k = need.get(ik or "")
                if not k:
                    continue
                ohlc = getattr(v, "ohlc", None)
                ltp = float(v.last_price or 0)
                chg = float(getattr(v, "net_change", 0) or 0)
                prev = ltp - chg if ltp else 0.0
                q = Quote(key=k, ltp=round(ltp, 2), prev_close=round(prev, 2), open=float(getattr(ohlc, "open", 0) or 0),
                          high=float(getattr(ohlc, "high", 0) or 0), low=float(getattr(ohlc, "low", 0) or 0),
                          volume=int(getattr(v, "volume", 0) or 0), change=round(chg, 2),
                          change_pct=round(chg / prev * 100, 2) if prev else 0.0, ts=now, oi=int(getattr(v, "oi", 0) or 0))
                self._cache[k] = (now, q)
                out[k] = q
        return out
