"""Synthetic NSE-like market for development and tests. No credentials, deterministic by seed.

Scenarios shape the spot path so the sniper has something to hunt:
  range      oscillates inside yesterday's range and pokes the previous-day high, then rejects
  trend_up   grinds up about 1 % by early afternoon, breaking the previous-day high
  trend_down mirror of trend_up
"""
from __future__ import annotations

import asyncio
import math
import random
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta

from deltadesk.analytics.greeks import price
from deltadesk.config import Settings
from deltadesk.feeds.base import IST, expiry_ts, next_weekly_expiry, option_symbol
from deltadesk.schemas import Bar, Instrument, Kind, Tick


def _round_tick(x: float) -> float:
    return max(0.05, round(x / 0.05) * 0.05)


class SyntheticFeed:
    name = "synthetic"

    def __init__(self, settings: Settings, scenario: str = "range", seed: int = 7, speed: float = 0.0,
                 day: date | None = None, base_spot: float = 25_300.0, base_iv: float = 0.13,
                 option_tick_every: int = 5) -> None:
        self.s = settings
        self.scenario = scenario
        self.rng = random.Random(seed)
        self.speed = speed                  # sim seconds per real second; 0 = as fast as possible
        self.day = day or datetime.now(IST).date()
        self.base_spot = base_spot
        self.base_iv = base_iv
        self.option_tick_every = option_tick_every
        self.expiry = next_weekly_expiry(self.day)
        self.und = settings.underlying
        self._subscribed: set[str] = set()
        self._prev_bars = self._make_prev_session()
        self.pdh = max(b.high for b in self._prev_bars)
        self.pdl = min(b.low for b in self._prev_bars)
        self.pdc = self._prev_bars[-1].close
        self.atm0 = round(self.pdc / settings.strike_step) * settings.strike_step
        self._instruments = self._make_instruments()
        self._oi: dict[str, int] = {}
        self._iv_noise = 0.0
        self._vix_noise = 0.0
        self._ou = 0.0
        self.t = datetime(self.day.year, self.day.month, self.day.day, 9, 15, tzinfo=IST)
        self.end = datetime(self.day.year, self.day.month, self.day.day, 15, 30, tzinfo=IST)

    # ---- universe -------------------------------------------------------------------------
    def _make_instruments(self) -> list[Instrument]:
        out = [
            Instrument(token=f"IDX:{self.und}", symbol=self.und, underlying=self.und, kind=Kind.IDX),
            Instrument(token="IDX:INDIAVIX", symbol="INDIA VIX", underlying="INDIA VIX", kind=Kind.IDX),
            Instrument(token=f"FUT:{self.und}:{self.expiry}", symbol=f"{self.und} {self.expiry:%d%b%y} FUT".upper(),
                       underlying=self.und, kind=Kind.FUT, expiry=self.expiry, lot_size=self.s.lot_size),
        ]
        step, n = self.s.strike_step, self.s.strikes_each_side
        for i in range(-n, n + 1):
            k = self.atm0 + i * step
            for kind in (Kind.CE, Kind.PE):
                out.append(Instrument(token=f"OPT:{self.und}:{self.expiry}:{k:.0f}:{kind.value}",
                                      symbol=option_symbol(self.und, self.expiry, k, kind), underlying=self.und,
                                      kind=kind, strike=k, expiry=self.expiry, lot_size=self.s.lot_size))
        return out

    def _make_prev_session(self) -> list[Bar]:
        bars: list[Bar] = []
        prev_day = self.day - timedelta(days=1)
        while prev_day.weekday() > 4:
            prev_day -= timedelta(days=1)
        t0 = datetime(prev_day.year, prev_day.month, prev_day.day, 9, 15, tzinfo=IST)
        px = self.base_spot
        rng = random.Random(self.rng.random())
        for m in range(375):
            det = self.base_spot * (1 + 0.004 * math.sin(2 * math.pi * m / 250))
            px = 0.9 * px + 0.1 * det + rng.gauss(0, 2.5)
            o = px + rng.gauss(0, 1.5)
            c = px + rng.gauss(0, 1.5)
            h = max(o, c) + abs(rng.gauss(0, 3))
            l = min(o, c) - abs(rng.gauss(0, 3))
            bars.append(Bar(ts=t0 + timedelta(minutes=m), open=o, high=h, low=l, close=c,
                            volume=int(abs(rng.gauss(60_000, 15_000)))))
        return bars

    # ---- paths ----------------------------------------------------------------------------
    def _spot(self, minutes: float) -> float:
        rng = self.rng
        self._ou = 0.98 * self._ou + rng.gauss(0, 0.6)
        if self.scenario == "range":
            centre = self.pdc
            amp = (self.pdh - self.pdl) / 2 * 1.03
            det = centre + amp * math.sin(2 * math.pi * (minutes - 22.5) / 90)
        elif self.scenario == "trend_up":
            det = self.pdc * (1 + 0.010 * min(1.0, minutes / 225) + 0.0006 * math.sin(2 * math.pi * minutes / 30))
        elif self.scenario == "trend_down":
            det = self.pdc * (1 - 0.010 * min(1.0, minutes / 225) + 0.0006 * math.sin(2 * math.pi * minutes / 30))
        else:
            raise ValueError(self.scenario)
        return det + self._ou

    def _iv(self, F: float, K: float, minutes: float) -> float:
        m = (F - K) / F
        smile = self.base_iv * (1 + 1.2 * m + 6.0 * m * m)
        decay = -0.004 * (minutes / 375) if self.scenario == "range" else 0.0
        return max(0.05, smile + self._iv_noise + decay)

    def _oi_for(self, inst: Instrument) -> int:
        if inst.token not in self._oi:
            k = inst.strike or 0.0
            dist = (k - self.atm0) / 400.0
            base = 40_000 * math.exp(-dist * dist)
            if k % 500 == 0:
                base *= 2.6
            if inst.kind == Kind.CE and k > self.atm0:
                base *= 1.6
            if inst.kind == Kind.PE and k < self.atm0:
                base *= 1.6
            self._oi[inst.token] = int(base * self.rng.uniform(0.8, 1.2))
        self._oi[inst.token] = max(0, self._oi[inst.token] + int(self.rng.gauss(0, 80)))
        return self._oi[inst.token]

    # ---- Feed protocol --------------------------------------------------------------------
    async def connect(self) -> None:
        return None

    async def instruments(self, underlying: str) -> list[Instrument]:
        return list(self._instruments)

    async def subscribe(self, tokens: list[str], mode: str = "full") -> None:
        self._subscribed.update(tokens)

    async def history(self, underlying: str) -> list[Bar]:
        return list(self._prev_bars)

    async def close(self) -> None:
        return None

    async def ticks(self) -> AsyncIterator[Tick]:
        r = self.s.risk_free
        sec = 0
        while self.t < self.end:
            minutes = (self.t.hour * 60 + self.t.minute + self.t.second / 60) - 555
            spot = self._spot(minutes)
            T = max(1e-6, (expiry_ts(self.expiry) - self.t).total_seconds() / (365 * 86400))
            F = spot * math.exp(r * T)
            self._iv_noise = 0.995 * self._iv_noise + self.rng.gauss(0, 0.0004)
            self._vix_noise = 0.99 * self._vix_noise + self.rng.gauss(0, 0.03)
            yield Tick(ts=self.t, token=f"IDX:{self.und}", ltp=round(spot, 2))
            yield Tick(ts=self.t, token="IDX:INDIAVIX", ltp=round(self.base_iv * 100 + self._vix_noise, 2))
            yield Tick(ts=self.t, token=f"FUT:{self.und}:{self.expiry}", ltp=_round_tick(F),
                       bid=_round_tick(F - 0.5), ask=_round_tick(F + 0.5),
                       volume=1000 * sec, oi=12_000_000)
            if sec % self.option_tick_every == 0:
                for inst in self._instruments:
                    if inst.kind not in (Kind.CE, Kind.PE):
                        continue
                    K = inst.strike or 0.0
                    px = price(F, K, T, r, self._iv(F, K, minutes), inst.kind == Kind.CE)
                    px = _round_tick(px)
                    spread = max(0.05, round(px * 0.01 / 0.05) * 0.05)
                    yield Tick(ts=self.t, token=inst.token, ltp=px, bid=_round_tick(px - spread / 2),
                               ask=_round_tick(px + spread / 2), volume=int(50 * sec * self.rng.random()),
                               oi=self._oi_for(inst))
            self.t += timedelta(seconds=1)
            sec += 1
            if self.speed > 0:
                await asyncio.sleep(1.0 / self.speed)
            elif sec % 200 == 0:
                await asyncio.sleep(0)       # let other tasks run
