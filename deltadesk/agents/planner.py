"""planner.agent: previous-session analysis into a DayPlan with armed-able opportunity zones."""
from __future__ import annotations

from datetime import date

from deltadesk.config import Settings
from deltadesk.schemas import Bar, DayPlan, Regime, Zone, ZoneKind


class PlannerAgent:
    name = "planner"
    version = "0.1"

    def __init__(self, settings: Settings) -> None:
        self.s = settings

    def step(self, day: date, prev_bars: list[Bar]) -> DayPlan:
        pdh = max(b.high for b in prev_bars)
        pdl = min(b.low for b in prev_bars)
        pdc = prev_bars[-1].close
        pivot = (pdh + pdl + pdc) / 3
        bc = (pdh + pdl) / 2
        tc = 2 * pivot - bc
        band = pdc * 0.0010                       # 0.10 % of price: how wide a "touch" is
        bias = "LONG" if pdc > pivot * 1.001 else "SHORT" if pdc < pivot * 0.999 else "NEUTRAL"
        zones = [
            Zone(id="PDH_FADE", kind=ZoneKind.FADE, lo=pdh - band, hi=pdh + band, source="PDH", direction="DOWN",
                 compatible=[Regime.RANGE_BOUND], structures=["short_call_spread", "short_strangle"]),
            Zone(id="PDL_FADE", kind=ZoneKind.FADE, lo=pdl - band, hi=pdl + band, source="PDL", direction="UP",
                 compatible=[Regime.RANGE_BOUND], structures=["short_put_spread", "short_strangle"]),
            Zone(id="PDH_BREAK", kind=ZoneKind.BREAK, lo=pdh + band, hi=pdh + 3 * band, source="PDH", direction="UP",
                 compatible=[Regime.TRENDING_UP], structures=["bull_call_spread"]),
            Zone(id="PDL_BREAK", kind=ZoneKind.BREAK, lo=pdl - 3 * band, hi=pdl - band, source="PDL", direction="DOWN",
                 compatible=[Regime.TRENDING_DOWN], structures=["bear_put_spread"]),
            Zone(id="INSIDE_PREMIUM", kind=ZoneKind.PREMIUM, lo=pdl + 2 * band, hi=pdh - 2 * band, source="exp_move",
                 direction="NONE", compatible=[Regime.RANGE_BOUND], structures=["short_strangle"]),
        ]
        notes = [
            f"PDH {pdh:.0f}, PDL {pdl:.0f}, PDC {pdc:.0f}; CPR {bc:.0f}-{tc:.0f} ({'narrow' if (tc - bc) / pdc < 0.002 else 'wide'}).",
            f"Bias {bias.lower()}: close {'above' if pdc > pivot else 'below'} pivot {pivot:.0f}.",
            "Fade zones need RANGE_BOUND; break zones need a trend call. Premium zone opens after 10:30.",
        ]
        return DayPlan(date=day, underlying=self.s.underlying, pdh=pdh, pdl=pdl, pdc=pdc, pivot=pivot,
                       bc=bc, tc=tc, bias=bias, zones=zones, notes=notes)
