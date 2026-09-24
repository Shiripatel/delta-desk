"""Keep the read model warm so the first click after a wake-up or deploy does not pay for every fetch.

On start it fills, in priority order: index quotes, the NIFTY 50 ranking, the all-universe ranking (the AI
score column on the watchlist and the analysis head), the news wire, the global map and the default
watchlist's week / month stats. Then it loops: quotes-driven caches every few minutes, rankings on their own
TTL, and the slow, rarely changing things (investors' valuations, fundamentals for the default watchlist) once
after start. Every step is best effort: a failing fetch is logged and skipped, never raised.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

FAST_EVERY = 150        # seconds: quotes, indices, news (inside the 180 s quote cache)
RANK_EVERY = 600        # seconds: rankings (cache TTL is 900)


class Warmer:
    def __init__(self, markets, log: Callable[[str], None] = print) -> None:
        self.m = markets
        self.log = log
        self.runs = 0
        self.last: dict[str, float] = {}

    def _step(self, name: str, fn: Callable[[], object]) -> None:
        t0 = time.time()
        try:
            fn()
            self.last[name] = time.time()
            self.log(f"warm: {name} in {time.time() - t0:.1f}s")
        except Exception as exc:  # noqa: BLE001 - warming must never crash the server
            self.log(f"warm: {name} failed: {exc}")

    def fast(self) -> None:
        m = self.m
        self._step("indices", m.indices)
        self._step("news", lambda: m.news.refresh())
        self._step("global", m.global_market)
        try:
            keys = sorted({k for v in m.watchlist.lists.values() for k in v})
            self._step("watchlist quotes", lambda: m.quotes.quotes(keys))
        except Exception:  # noqa: BLE001
            pass

    def rankings(self) -> None:
        m = self.m
        self._step("ranking NIFTY50", lambda: m.ai_rank("NIFTY50", 50, "short"))
        self._step("ranking all", lambda: m.ai_rank(None, 500, "short"))
        self._step("radar NIFTY50", lambda: m.ai_radar("NIFTY50", 5, "short"))
        for code in ("BANKNIFTY", "SENSEX"):
            self._step(f"ranking {code}", lambda c=code: m.ai_rank(c, 50, "short"))

    def slow(self) -> None:
        m = self.m
        try:
            keys = sorted({k for v in m.watchlist.lists.values() for k in v})
            self._step("watchlist stats", lambda: m.wl_stats(keys))
        except Exception:  # noqa: BLE001
            pass
        self._step("investors", m.investors)
        if getattr(m, "funda", None) is not None:
            try:
                keys = [k for v in m.watchlist.lists.values() for k in v if m._name(k)[1] == "stock"][:8]
                for k in keys:
                    self._step(f"fundamentals {k}", lambda s=k: m.fundamentals(s))
            except Exception:  # noqa: BLE001
                pass

    async def run(self) -> None:
        """Start immediately, then keep the fast caches fresh; rankings on their own cadence."""
        await asyncio.to_thread(self.fast)
        await asyncio.to_thread(self.rankings)
        await asyncio.to_thread(self.slow)
        self.runs += 1
        last_rank = time.time()
        while True:
            await asyncio.sleep(FAST_EVERY)
            await asyncio.to_thread(self.fast)
            if time.time() - last_rank >= RANK_EVERY:
                await asyncio.to_thread(self.rankings)
                last_rank = time.time()
            self.runs += 1
