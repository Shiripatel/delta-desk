"""sniper.agent: holds the DayPlan's zones, arms them as price approaches, fires on confirmation.

It never picks a trade. It only says: this zone, now, with this quality.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from deltadesk.config import Settings
from deltadesk.schemas import ChainStats, DayPlan, RegimeCall, Snapshot, Trigger, Zone, ZoneKind


class SniperAgent:
    name = "sniper"
    version = "0.1"

    def __init__(self, settings: Settings, cooldown_min: int = 60) -> None:
        self.s = settings
        self.cooldown = timedelta(minutes=cooldown_min)
        self._touched: dict[str, datetime] = {}
        self._extreme: dict[str, float] = {}

    def _in_window(self, ts: datetime) -> bool:
        a, b = self.s.limits.trading_window
        return time.fromisoformat(a) <= ts.timetz().replace(tzinfo=None) <= time.fromisoformat(b)

    def step(self, snap: Snapshot, plan: DayPlan, regime: RegimeCall, stats: ChainStats,
             open_zone_ids: set[str] | None = None) -> Trigger | None:
        open_zone_ids = open_zone_ids or set()
        spot, ts = snap.spot, snap.ts
        reach = max(stats.expected_move_pts * 0.35, plan.pdc * 0.002)
        fired: Trigger | None = None
        for z in plan.zones:
            mid = (z.lo + z.hi) / 2
            z.armed = abs(spot - mid) <= reach and (z.fired_at is None or ts - z.fired_at > self.cooldown)
            if not z.armed or not self._in_window(ts) or fired is not None:
                continue
            if regime.regime not in z.compatible or z.id in open_zone_ids:
                continue
            t = self._check(z, snap, regime, stats, plan)
            if t is not None:
                z.fired_at = ts
                fired = t
        return fired

    def _check(self, z: Zone, snap: Snapshot, regime: RegimeCall, stats: ChainStats, plan: DayPlan) -> Trigger | None:
        spot, ts, band = snap.spot, snap.ts, (z.hi - z.lo)
        bars = snap.bars_1m
        if z.kind == ZoneKind.FADE:
            if z.lo <= spot <= z.hi:
                self._touched[z.id] = ts
                ext = self._extreme.get(z.id, spot)
                self._extreme[z.id] = max(ext, spot) if z.direction == "DOWN" else min(ext, spot)
                return None
            touched = self._touched.get(z.id)
            if touched is None or ts - touched > timedelta(minutes=20):
                return None
            rejected = (spot < z.lo - band * 0.5) if z.direction == "DOWN" else (spot > z.hi + band * 0.5)
            if not rejected or len(bars) < 2:
                return None
            last = bars[-1]
            candle_ok = last.close < last.open if z.direction == "DOWN" else last.close > last.open
            q = min(1.0, 0.45 + 0.35 * regime.p + (0.15 if candle_ok else 0.0) + (0.05 if stats.iv_minus_rv > 0 else 0))
            self._touched.pop(z.id, None)
            return Trigger(ts=ts, zone=z, spot=spot, quality=q,
                           why=f"{z.source} {mid_str(z)} touched at {touched:%H:%M} and rejected; "
                               f"regime {regime.regime.value} p={regime.p:.2f}, ADX {regime.adx:.0f}.")
        if z.kind == ZoneKind.BREAK:
            if len(bars) < 3:
                return None
            c1, c2 = bars[-2].close, bars[-1].close
            beyond = (c1 > z.lo and c2 > z.lo) if z.direction == "UP" else (c1 < z.hi and c2 < z.hi)
            if not beyond:
                return None
            q = min(1.0, 0.4 + 0.45 * regime.p + (0.1 if regime.adx > 30 else 0.0))
            return Trigger(ts=ts, zone=z, spot=spot, quality=q,
                           why=f"Two 1-min closes beyond {z.source} {mid_str(z)}; regime {regime.regime.value} "
                               f"p={regime.p:.2f}, ADX {regime.adx:.0f}.")
        if z.kind == ZoneKind.PREMIUM:
            if ts.timetz().replace(tzinfo=None) < time(10, 30):
                return None
            if not (z.lo <= spot <= z.hi) or regime.p < 0.7 or stats.iv_minus_rv < 2.0:
                return None
            q = min(1.0, 0.4 + 0.4 * regime.p + min(0.2, stats.iv_minus_rv / 20))
            return Trigger(ts=ts, zone=z, spot=spot, quality=q,
                           why=f"Inside yesterday's range, regime RANGE_BOUND p={regime.p:.2f}, "
                               f"IV {stats.atm_iv*100:.1f} % vs realised {(stats.atm_iv*100 - stats.iv_minus_rv):.1f} %.")
        return None


def mid_str(z: Zone) -> str:
    return f"{(z.lo + z.hi) / 2:,.0f}"
