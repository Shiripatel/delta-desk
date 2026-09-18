"""feed.agent: turns raw ticks into a typed Snapshot with local IV and Greeks."""
from __future__ import annotations

import asyncio
from datetime import datetime

from deltadesk.analytics.greeks import greeks, implied_vol
from deltadesk.config import Settings
from deltadesk.feeds.base import Feed, FeedEnded, expiry_ts
from deltadesk.schemas import Bar, ChainRow, Instrument, Kind, Snapshot, Tick


class FeedAgent:
    name = "feed"
    version = "0.1"

    def __init__(self, settings: Settings, feed: Feed, instruments: list[Instrument]) -> None:
        self.s = settings
        self.feed = feed
        self.instruments = {i.token: i for i in instruments}
        self.by_symbol = {i.symbol: i for i in instruments}
        self.idx = next(i for i in instruments if i.kind == Kind.IDX and i.underlying == settings.underlying)
        self.vix = next((i for i in instruments if i.kind == Kind.IDX and "VIX" in i.symbol.upper()), None)
        self.fut = next(i for i in instruments if i.kind == Kind.FUT)
        self.expiry = min(i.expiry for i in instruments if i.kind in (Kind.CE, Kind.PE) and i.expiry)
        self.latest: dict[str, Tick] = {}
        self.bars: list[Bar] = []
        self._cur: Bar | None = None
        self.last_ts: datetime | None = None
        self.latency_ms = 0.0
        self._it = None
        self.ended = False

    # ---- ingestion ------------------------------------------------------------------------
    def _ingest(self, t: Tick) -> None:
        self.latest[t.token] = t
        self.last_ts = t.ts
        if t.token == self.idx.token:
            slot = t.ts.replace(second=0, microsecond=0)
            if self._cur is None or self._cur.ts != slot:
                if self._cur is not None:
                    self.bars.append(self._cur)
                self._cur = Bar(ts=slot, open=t.ltp, high=t.ltp, low=t.ltp, close=t.ltp)
            else:
                c = self._cur
                self._cur = Bar(ts=slot, open=c.open, high=max(c.high, t.ltp), low=min(c.low, t.ltp), close=t.ltp)

    async def pump_until(self, target: datetime, timeout: float) -> None:
        """Consume ticks until one is stamped at or after `target`, or `timeout` real seconds pass."""
        if self._it is None:
            self._it = self.feed.ticks().__aiter__()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return
            try:
                t = await asyncio.wait_for(self._it.__anext__(), timeout=remaining)
            except TimeoutError:
                return
            except StopAsyncIteration:
                self.ended = True
                raise FeedEnded from None
            self._ingest(t)
            if t.ts >= target:
                return

    # ---- snapshot -------------------------------------------------------------------------
    def snapshot(self, prev_bars: list[Bar]) -> Snapshot | None:
        spot_t = self.latest.get(self.idx.token)
        fut_t = self.latest.get(self.fut.token)
        if spot_t is None or fut_t is None or self.last_ts is None:
            return None
        ts = self.last_ts
        T = max(1e-6, (expiry_ts(self.expiry) - ts).total_seconds() / (365 * 86400))
        F, r = fut_t.ltp, self.s.risk_free
        step = self.s.strike_step
        atm = round(spot_t.ltp / step) * step
        rows: dict[float, dict] = {}
        for tok, t in self.latest.items():
            inst = self.instruments.get(tok)
            if inst is None or inst.kind not in (Kind.CE, Kind.PE) or inst.expiry != self.expiry:
                continue
            rows.setdefault(inst.strike, {})[inst.kind] = t
        chain: list[ChainRow] = []
        for k in sorted(rows):
            ce, pe = rows[k].get(Kind.CE), rows[k].get(Kind.PE)
            if ce is None or pe is None:
                continue
            ce_iv = implied_vol(ce.ltp, F, k, T, r, True, hi=3.0)
            pe_iv = implied_vol(pe.ltp, F, k, T, r, False, hi=3.0)
            g_ce = greeks(F, k, T, r, ce_iv, True) if ce_iv else None
            g_pe = greeks(F, k, T, r, pe_iv, False) if pe_iv else None
            chain.append(ChainRow(strike=k, expiry=self.expiry, ce_ltp=ce.ltp, pe_ltp=pe.ltp,
                                  ce_oi=ce.oi, pe_oi=pe.oi, ce_iv=ce_iv, pe_iv=pe_iv,
                                  ce_delta=g_ce["delta"] if g_ce else None,
                                  pe_delta=g_pe["delta"] if g_pe else None,
                                  gamma=g_ce["gamma"] if g_ce else (g_pe["gamma"] if g_pe else None),
                                  vega=g_ce["vega"] if g_ce else (g_pe["vega"] if g_pe else None),
                                  theta=g_ce["theta"] if g_ce else (g_pe["theta"] if g_pe else None)))
        bars = list(self.bars) + ([self._cur] if self._cur else [])
        vix = self.latest[self.vix.token].ltp if self.vix and self.vix.token in self.latest else 0.0
        return Snapshot(ts=ts, underlying=self.s.underlying, spot=spot_t.ltp, fut=F, vix=vix,
                        expiry=self.expiry, t_years=T, atm=atm, chain=chain, bars_1m=bars,
                        prev_bars_1m=prev_bars, feed_latency_ms=self.latency_ms,
                        instruments=self.by_symbol)
