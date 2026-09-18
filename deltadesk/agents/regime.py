"""regime.agent: trend / range / event classification with a probability.

Features: ADX(14) on 5-minute bars (warmed up on the previous session), EMA slope, realised vol,
VIX jump since the open, the last 1-minute return, and where today's range sits against yesterday's.
Rules today; the phase-3 calibration pass replaces the p() mapping with one fitted on the journal.
"""
from __future__ import annotations

from deltadesk.analytics.indicators import adx, ema, realised_vol, resample
from deltadesk.schemas import DayPlan, Regime, RegimeCall, Snapshot


class RegimeAgent:
    name = "regime"
    version = "0.2"

    def __init__(self) -> None:
        self._vix_open: float | None = None

    def step(self, snap: Snapshot, plan: DayPlan | None = None) -> RegimeCall:
        if self._vix_open is None and snap.vix:
            self._vix_open = snap.vix
        bars_1m = snap.prev_bars_1m + snap.bars_1m
        bars_5m = resample(bars_1m, 5)
        a = adx(bars_5m[-60:], 14)
        closes = [b.close for b in bars_5m[-40:]]
        slope = (ema(closes, 8) - ema(closes[:-3], 8)) / snap.spot if len(closes) > 10 else 0.0
        rv = realised_vol(snap.bars_1m, window=30) if len(snap.bars_1m) > 5 else realised_vol(bars_1m, window=30)
        vix_jump = (snap.vix / self._vix_open - 1) if self._vix_open else 0.0
        last_ret = abs(snap.bars_1m[-1].close / snap.bars_1m[-1].open - 1) if snap.bars_1m else 0.0
        today_hi = max((b.high for b in snap.bars_1m), default=snap.spot)
        today_lo = min((b.low for b in snap.bars_1m), default=snap.spot)
        band = snap.spot * 0.001
        inside = plan is not None and today_hi <= plan.pdh + band and today_lo >= plan.pdl - band
        above = plan is not None and snap.spot > plan.pdh + band
        below = plan is not None and snap.spot < plan.pdl - band
        feats = {"adx": a, "ema_slope": slope, "vix_jump": vix_jump, "last_1m_ret": last_ret,
                 "inside_prev_range": float(inside), "realised_vol": rv}

        def call(regime: Regime, p: float) -> RegimeCall:
            return RegimeCall(regime=regime, p=round(min(0.92, max(0.5, p)), 2), adx=a, realised_vol=rv, features=feats)

        if vix_jump > 0.08 or last_ret > 0.004:
            return call(Regime.EVENT, 0.8)
        if above and slope > 0 and a >= 20:
            return call(Regime.TRENDING_UP, 0.6 + (a - 20) / 50)
        if below and slope < 0 and a >= 20:
            return call(Regime.TRENDING_DOWN, 0.6 + (a - 20) / 50)
        if inside and a < 35:
            return call(Regime.RANGE_BOUND, 0.6 + 0.3 * (1 - a / 35))
        if a >= 25 and slope > 0:
            return call(Regime.TRENDING_UP, 0.55 + (a - 25) / 60)
        if a >= 25 and slope < 0:
            return call(Regime.TRENDING_DOWN, 0.55 + (a - 25) / 60)
        return call(Regime.RANGE_BOUND, 0.55 + (25 - a) / 60)
