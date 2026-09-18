"""Quote providers for equities, indices, ETFs, currency pairs and index futures.

`QuoteProvider.quotes(keys)` returns {key: Quote}. Keys are plain NSE symbols ("HDFCBANK", "NIFTYBEES",
"USDINR"), index codes ("NIFTY50") or futures keys ("FUT:NIFTY50:2026-09-29"). The synthetic provider is
deterministic per seed and moves with wall-clock time so the page looks alive without credentials.
Real providers map keys to broker instrument keys:

  Upstox  GET https://api.upstox.com/v2/market-quote/quotes?instrument_key=NSE_EQ|<ISIN>,NSE_INDEX|Nifty 50,NSE_FO|<token>
          (free; up to 500 keys per call; WebSocket V3 for streaming; ISIN and tokens from the instrument master;
          currency futures are NCD_FO|<token>)
  Kite    kite.quote(["NSE:HDFCBANK", "NSE:NIFTY 50", "NFO:NIFTY25SEPFUT", "CDS:USDINR25SEPFUT"])  (paid; 500 per call)
  Dhan    POST /v2/marketfeed/quote {"NSE_EQ": [security_id, ...], "NSE_FNO": [...]}  (Data API plan; 1,000 per call)
  Angel   POST /rest/secure/angelbroking/market/v1/quote/ {"mode":"FULL","exchangeTokens":{"NSE":[...],"NFO":[...]}}
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Protocol

from deltadesk.markets.universe import ETFS, FX, FX_WORLD, GLOBAL, INDICES, SEED_LEVELS, all_symbols, futures_contracts


@dataclass
class Quote:
    key: str
    ltp: float
    prev_close: float
    open: float
    high: float
    low: float
    volume: int
    change: float
    change_pct: float
    ts: float
    oi: int = 0

    def json(self) -> dict:
        return asdict(self)


class QuoteProvider(Protocol):
    name: str

    def quotes(self, keys: list[str]) -> dict[str, Quote]: ...


class SyntheticQuotes:
    """Index-correlated random walks. State advances with real time so repeated polls show motion."""
    name = "synthetic"

    def __init__(self, seed: int = 11, vol_daily: float = 0.011, today: date | None = None) -> None:
        self.seed = seed
        self.vol = vol_daily
        self.today = today or date.today()
        self.t0 = time.time()
        rng = random.Random(seed)
        syms = all_symbols()
        self._beta = {s: rng.uniform(0.6, 1.4) for s in syms}
        self._idio = {s: rng.uniform(0.6, 1.6) for s in syms}
        self._px0 = {s: rng.uniform(150, 4_000) for s in syms}
        self._sector_drift: dict[str, float] = {}
        for c in syms.values():
            self._sector_drift.setdefault(c.sector, rng.gauss(0, 0.004))
        self._etf = {e[0]: e for e in ETFS}
        self._fx = {f[0]: f for f in FX}
        self._fx_walk = {f[0]: 0.0 for f in FX}
        self._glob = {g[0]: g for g in GLOBAL}
        for g in GLOBAL:
            self._fx_walk[g[0]] = 0.0
        self._fxw = {f[0]: f for f in FX_WORLD}
        for f in FX_WORLD:
            self._fx_walk[f[0]] = 0.0
        self._futs = {f["key"]: f for f in futures_contracts(self.today)}
        self._state: dict[str, tuple[float, float, float, float]] = {}   # key -> (ltp, high, low, last_t)
        self._last = self.t0
        self._market = 0.0
        self._rvol = 0.0
        # warm up so the first paint already shows dispersion
        for i in range(40):
            self._advance(60.0, random.Random(f"{seed}:warm:{i}"), self.t0)

    # ---- dynamics -------------------------------------------------------------------------
    def _advance(self, dt: float, rng: random.Random, now: float) -> None:
        per_sec = self.vol / math.sqrt(6.25 * 3600)
        self._market += rng.gauss(0, per_sec * math.sqrt(dt))
        self._market *= 0.9995 ** dt
        syms = all_symbols()
        for s, c in syms.items():
            move = self._beta[s] * self._market + self._sector_drift[c.sector]
            ltp0, hi, lo, _ = self._state.get(s, (self._px0[s], self._px0[s], self._px0[s], now))
            idio = rng.gauss(0, per_sec * self._idio[s] * math.sqrt(dt))
            r_prev = math.log(ltp0 / self._px0[s])
            r_new = move + (r_prev - move) * (0.999 ** dt) + idio
            ltp = self._px0[s] * math.exp(r_new)
            self._state[s] = (ltp, max(hi, ltp), min(lo, ltp), now)
        idx_ret: dict[str, float] = {}
        for code, ix in INDICES.items():
            base = SEED_LEVELS[code]
            if code == "INDIAVIX":
                ret = -4 * self._market + rng.gauss(0, 0.002)
            else:
                w = sum(c.weight for c in ix.constituents) or 1.0
                ret = sum(c.weight * math.log(self._state[c.symbol][0] / self._px0[c.symbol]) for c in ix.constituents) / w
            idx_ret[code] = ret
            self._put(code, base * math.exp(ret), now)
        for sym, (_, _, tracks, seed_px) in self._etf.items():
            if tracks in idx_ret:
                ret = idx_ret[tracks] + rng.gauss(0, 0.0003)
            else:
                walk = self._fx_walk.setdefault(sym, 0.0)
                self._fx_walk[sym] = walk * (0.9995 ** dt) + rng.gauss(0, per_sec * 0.7 * math.sqrt(dt))
                ret = self._fx_walk[sym]
            self._put(sym, seed_px * math.exp(ret), now)
        for sym, (_, _, _, seed_px) in self._fx.items():
            self._fx_walk[sym] = self._fx_walk[sym] * (0.9995 ** dt) + rng.gauss(0, per_sec * 0.3 * math.sqrt(dt))
            self._put(sym, seed_px * math.exp(self._fx_walk[sym]), now)
        for key, f in self._fxw.items():
            self._fx_walk[key] = self._fx_walk[key] * (0.9995 ** dt) + rng.gauss(0, per_sec * 0.3 * math.sqrt(dt))
            self._put(key, f[6] * math.exp(self._fx_walk[key]), now)
        for key, g in self._glob.items():
            v = 3.0 if g[5] == "crypto" else 0.6 if g[5] == "commodity" else 0.3
            self._fx_walk[key] = self._fx_walk[key] * (0.9995 ** dt) + rng.gauss(0, per_sec * v * math.sqrt(dt))
            self._put(key, g[6] * math.exp(self._fx_walk[key]), now)
        for key, f in self._futs.items():
            spot = self._state[f["underlying"]][0]
            T = max(0.0, (datetime.fromisoformat(f["expiry"]).timestamp() + 15.5 * 3600 - now) / (365 * 86400))
            self._put(key, spot * math.exp(0.065 * T) + rng.gauss(0, spot * 0.0001), now)

    def _put(self, key: str, ltp: float, now: float) -> None:
        _, hi, lo, _ = self._state.get(key, (ltp, ltp, ltp, now))
        self._state[key] = (ltp, max(hi, ltp), min(lo, ltp), now)

    def _step(self) -> None:
        now = time.time()
        dt = now - self._last
        if dt < 0.5:
            return
        self._advance(dt, random.Random(f"{self.seed}:{int(now)}"), now)
        self._last = now

    def _prev(self, k: str) -> float:
        if k in SEED_LEVELS:
            return SEED_LEVELS[k]
        if k in self._px0:
            return self._px0[k]
        if k in self._etf:
            return self._etf[k][3]
        if k in self._fx:
            return self._fx[k][3]
        if k in self._glob:
            return self._glob[k][6]
        if k in self._fxw:
            return self._fxw[k][6]
        if k in self._futs:
            f = self._futs[k]
            T = max(0.0, (datetime.fromisoformat(f["expiry"]).timestamp() + 15.5 * 3600 - self.t0) / (365 * 86400))
            return SEED_LEVELS[f["underlying"]] * math.exp(0.065 * T)
        return self._state[k][0]

    def quotes(self, keys: list[str]) -> dict[str, Quote]:
        self._step()
        out: dict[str, Quote] = {}
        for k in keys:
            st = self._state.get(k)
            if st is None:
                continue
            ltp, hi, lo, ts = st
            prev = self._prev(k)
            chg = ltp - prev
            h = abs(hash((self.seed, k)))
            vol = 0 if k in INDICES else int(h % 4_000_000 + 200_000)
            oi = int(h % 9_000_000 + 3_000_000) if k in self._futs else 0
            d = 4 if k in self._fx else self._glob[k][3] if k in self._glob else self._fxw[k][3] if k in self._fxw else 2
            out[k] = Quote(key=k, ltp=round(ltp, d), prev_close=round(prev, d), open=round(prev, d),
                           high=round(hi, d), low=round(lo, d), volume=vol, change=round(chg, d),
                           change_pct=round(chg / prev * 100, 2), ts=ts, oi=oi)
        return out


def make_quotes(feed: str) -> QuoteProvider:
    """Quote provider matching DD_FEED. Falls back to synthetic with a warning when a broker is not ready."""
    if feed == "yahoo":
        from deltadesk.markets.quotes_yahoo import YahooQuotes
        return YahooQuotes()
    if feed == "upstox":
        try:
            from deltadesk.markets.quotes_upstox import UpstoxQuotes
            return UpstoxQuotes()
        except Exception as e:  # noqa: BLE001 - missing token or SDK: keep the page alive
            print(f"warning: Upstox quotes unavailable ({e}); using synthetic quotes")
    elif feed != "synthetic":
        print(f"warning: no quote provider for feed {feed!r}; using synthetic quotes")
    return SyntheticQuotes()
