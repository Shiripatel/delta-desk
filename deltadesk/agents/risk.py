"""risk.agent: margin, max loss, Greek limits, drawdown. It can veto and says why.

Margin here is an approximation for paper mode. Live mode must call the broker's margin API
(Kite `order_margins`, Upstox `/charges/margin`, Dhan `/margincalculator`) before routing.
"""
from __future__ import annotations

from datetime import time

from deltadesk.config import Settings
from deltadesk.schemas import CandidateTrade, Kind, OrderState, RiskVerdict, Side, Snapshot

NAKED_MARGIN_PCT = 0.12          # index short option, SPAN + exposure, rough


class RiskAgent:
    name = "risk"
    version = "0.1"

    def __init__(self, settings: Settings) -> None:
        self.s = settings

    def step(self, trade: CandidateTrade, snap: Snapshot, book: OrderState, day_pnl: float,
             margin_used: float = 0.0, open_structures: int = 0) -> RiskVerdict:
        L = self.s.limits
        units = trade.lot_size
        reasons: list[str] = []
        shorts = [l for l in trade.legs if l.side == Side.SELL]
        longs = [l for l in trade.legs if l.side == Side.BUY]
        net_premium = sum((l.limit if l.side == Side.SELL else -l.limit) * l.lots * units for l in trade.legs)

        # margin and max loss ----------------------------------------------------------------
        if shorts and longs and len(shorts) == len(longs):
            width = sum(abs(s.strike - b.strike) for s, b in zip(shorts, longs, strict=False)) / len(shorts)
            if net_premium >= 0:                                   # credit spread: width minus credit
                max_loss = max(0.0, width * shorts[0].lots * units - net_premium)
            else:                                                  # debit spread: the debit paid
                max_loss = -net_premium
            margin = max_loss * 1.05
        elif shorts and not longs:
            margin = sum(NAKED_MARGIN_PCT * snap.spot * l.lots * units for l in shorts) * (0.7 if len(shorts) > 1 else 1.0)
            max_loss = (trade.stop - sum(l.limit for l in shorts)) * shorts[0].lots * units if trade.stop else margin
        else:
            margin = max(0.0, -net_premium)
            max_loss = max(0.0, -net_premium)
        margin_after = margin_used + margin

        # greeks ----------------------------------------------------------------------------
        net_delta = sum(p.delta * p.qty for p in book.positions) / units
        net_vega = sum(p.vega * p.qty for p in book.positions)
        for l in trade.legs:
            row = next((r for r in snap.chain if r.strike == l.strike), None)
            if row is None:
                continue
            d = (row.ce_delta if l.kind == Kind.CE else row.pe_delta) or 0.0
            sign = 1 if l.side == Side.BUY else -1
            net_delta += sign * d * l.lots
            net_vega += sign * (row.vega or 0.0) * l.lots * units

        # checks ----------------------------------------------------------------------------
        if margin_after > L.margin_cap:
            reasons.append(f"margin after {margin_after:,.0f} exceeds cap {L.margin_cap:,.0f}")
        if max_loss > L.max_loss_per_trade:
            reasons.append(f"max loss {max_loss:,.0f} exceeds {L.max_loss_per_trade:,.0f}")
        if any(l.lots > L.max_lots for l in trade.legs):
            reasons.append(f"lots exceed {L.max_lots}")
        if not (L.net_vega_min <= net_vega <= L.net_vega_max):
            reasons.append(f"net vega {net_vega:,.0f} outside [{L.net_vega_min:,.0f}, {L.net_vega_max:,.0f}]")
        if abs(net_delta) > L.net_delta_abs_max * (open_structures + 1):
            reasons.append(f"net delta {net_delta:.2f} lots beyond limit")
        if open_structures >= L.max_open_structures:
            reasons.append(f"already {open_structures} open structures (limit {L.max_open_structures})")
        if day_pnl < -L.daily_drawdown:
            reasons.append(f"daily drawdown {day_pnl:,.0f} breached {L.daily_drawdown:,.0f}")
        a, b = L.trading_window
        t = snap.ts.timetz().replace(tzinfo=None)
        if not (time.fromisoformat(a) <= t <= time.fromisoformat(b)):
            reasons.append(f"outside trading window {a}-{b}")
        return RiskVerdict(risk_ok=not reasons, reasons=reasons, margin=round(margin, 2), margin_after=round(margin_after, 2),
                           max_loss=round(max_loss, 2), net_delta=round(net_delta, 3), net_vega=round(net_vega, 1))
