"""strategy.agent: turns a Trigger into one CandidateTrade with strikes, size, stop, target, confidence."""
from __future__ import annotations

import math
from datetime import timedelta

from deltadesk.config import Settings
from deltadesk.schemas import (
    CandidateTrade,
    ChainRow,
    ChainStats,
    DayPlan,
    Kind,
    Leg,
    RegimeCall,
    Side,
    Snapshot,
    Trigger,
)


class StrategyAgent:
    name = "strategy"
    version = "0.1"

    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self._seq = 416

    # ---- helpers --------------------------------------------------------------------------
    def _row(self, snap: Snapshot, strike: float) -> ChainRow | None:
        return next((r for r in snap.chain if r.strike == strike), None)

    def _up(self, x: float) -> float:
        return math.ceil(x / self.s.strike_step) * self.s.strike_step

    def _down(self, x: float) -> float:
        return math.floor(x / self.s.strike_step) * self.s.strike_step

    def _leg(self, snap: Snapshot, side: Side, kind: Kind, strike: float, lots: int) -> Leg | None:
        row = self._row(snap, strike)
        if row is None:
            return None
        ltp = row.ce_ltp if kind == Kind.CE else row.pe_ltp
        sym = next((s for s, i in snap.instruments.items() if i.kind == kind and i.strike == strike), None)
        if sym is None:
            return None
        return Leg(side=side, symbol=sym, kind=kind, strike=strike, lots=lots, limit=round(ltp, 2))

    def _confidence(self, trig: Trigger, regime: RegimeCall, stats: ChainStats, short_premium: bool) -> float:
        c = 0.30 + 0.30 * regime.p + 0.25 * trig.quality
        if stats.iv_rank is not None:
            edge = stats.iv_rank / 100 if short_premium else 1 - stats.iv_rank / 100
            c += 0.10 * edge
        else:
            c += 0.08 if (stats.iv_minus_rv > 0) == short_premium else -0.05
        return round(max(0.05, min(0.95, c)), 2)

    # ---- main -----------------------------------------------------------------------------
    def step(self, trig: Trigger, snap: Snapshot, regime: RegimeCall, stats: ChainStats, plan: DayPlan) -> CandidateTrade | None:
        lots = max(1, min(2, self.s.limits.max_lots))
        if "strangle" in (trig.zone.structures[0] if trig.zone.structures else ""):
            lots = 1
        em = stats.expected_move_pts
        step = self.s.strike_step
        structure = next((x for x in trig.zone.structures if x in BUILDERS), None)
        if structure is None:
            return None
        legs, stop, target, why = BUILDERS[structure](self, snap, trig, stats, plan, lots, em, step)
        if not legs:
            return None
        short_premium = structure.startswith("short")
        self._seq += 1
        conf = self._confidence(trig, regime, stats, short_premium)
        return CandidateTrade(id=f"S-{self._seq:04d}", ts=snap.ts, structure=structure, zone_id=trig.zone.id, legs=legs,
                              lot_size=self.s.lot_size, stop=stop, target=target, confidence=conf,
                              regime=regime.regime, why=f"{trig.why} {why}",
                              valid_until=snap.ts + timedelta(minutes=15))


def _short_strangle(a: StrategyAgent, snap, trig, stats, plan, lots, em, step):
    ce_k = max(a._up(snap.spot + em), stats.call_wall if stats.call_wall > snap.spot + 0.5 * em else 0)
    pe_k = min(a._down(snap.spot - em), stats.put_wall if stats.put_wall < snap.spot - 0.5 * em else 1e12)
    legs = [a._leg(snap, Side.SELL, Kind.CE, ce_k, lots), a._leg(snap, Side.SELL, Kind.PE, pe_k, lots)]
    if None in legs:
        return [], None, None, ""
    credit = sum(l.limit for l in legs)
    why = (f"Short strangle {pe_k:.0f} PE / {ce_k:.0f} CE outside the ±{em:.0f} pt expected move, "
           f"credit {credit:.2f}. Walls at {stats.put_wall:.0f} / {stats.call_wall:.0f}, max pain {stats.max_pain:.0f}.")
    return legs, round(credit * 1.6, 2), round(credit * 0.5, 2), why


def _short_call_spread(a: StrategyAgent, snap, trig, stats, plan, lots, em, step):
    sell_k = a._up(trig.zone.hi + 0.25 * em)
    buy_k = sell_k + 4 * step
    legs = [a._leg(snap, Side.SELL, Kind.CE, sell_k, lots), a._leg(snap, Side.BUY, Kind.CE, buy_k, lots)]
    if None in legs:
        return [], None, None, ""
    credit = legs[0].limit - legs[1].limit
    why = f"Short call spread {sell_k:.0f}/{buy_k:.0f} above the rejected level, credit {credit:.2f}."
    return legs, round(credit * 2.0, 2), round(credit * 0.4, 2), why


def _short_put_spread(a: StrategyAgent, snap, trig, stats, plan, lots, em, step):
    sell_k = a._down(trig.zone.lo - 0.25 * em)
    buy_k = sell_k - 4 * step
    legs = [a._leg(snap, Side.SELL, Kind.PE, sell_k, lots), a._leg(snap, Side.BUY, Kind.PE, buy_k, lots)]
    if None in legs:
        return [], None, None, ""
    credit = legs[0].limit - legs[1].limit
    why = f"Short put spread {sell_k:.0f}/{buy_k:.0f} below the rejected level, credit {credit:.2f}."
    return legs, round(credit * 2.0, 2), round(credit * 0.4, 2), why


def _bull_call_spread(a: StrategyAgent, snap, trig, stats, plan, lots, em, step):
    buy_k = a._down(snap.spot)
    sell_k = a._up(snap.spot + em)
    legs = [a._leg(snap, Side.BUY, Kind.CE, buy_k, lots), a._leg(snap, Side.SELL, Kind.CE, sell_k, lots)]
    if None in legs:
        return [], None, None, ""
    debit = legs[0].limit - legs[1].limit
    why = f"Bull call spread {buy_k:.0f}/{sell_k:.0f} on the break, debit {debit:.2f}."
    return legs, round(debit * 0.5, 2), round(debit * 1.8, 2), why


def _bear_put_spread(a: StrategyAgent, snap, trig, stats, plan, lots, em, step):
    buy_k = a._up(snap.spot)
    sell_k = a._down(snap.spot - em)
    legs = [a._leg(snap, Side.BUY, Kind.PE, buy_k, lots), a._leg(snap, Side.SELL, Kind.PE, sell_k, lots)]
    if None in legs:
        return [], None, None, ""
    debit = legs[0].limit - legs[1].limit
    why = f"Bear put spread {buy_k:.0f}/{sell_k:.0f} on the break, debit {debit:.2f}."
    return legs, round(debit * 0.5, 2), round(debit * 1.8, 2), why


BUILDERS = {
    "short_strangle": _short_strangle,
    "short_call_spread": _short_call_spread,
    "short_put_spread": _short_put_spread,
    "bull_call_spread": _bull_call_spread,
    "bear_put_spread": _bear_put_spread,
}
