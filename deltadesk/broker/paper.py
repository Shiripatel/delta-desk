"""Paper broker: fills at the limit when the market is at or through it, else at the touch price."""
from __future__ import annotations

from deltadesk.schemas import CandidateTrade, Fill, Kind, OrderState, Position, Side, Snapshot


class PaperBroker:
    def __init__(self) -> None:
        self.positions: dict[str, Position] = {}
        self.fills: list[Fill] = []
        self.realised = 0.0
        self.log: list[str] = []

    # ---- helpers --------------------------------------------------------------------------
    @staticmethod
    def _ltp(snap: Snapshot, kind: Kind, strike: float) -> float | None:
        row = next((r for r in snap.chain if r.strike == strike), None)
        if row is None:
            return None
        return row.ce_ltp if kind == Kind.CE else row.pe_ltp

    def _fill(self, snap: Snapshot, symbol: str, kind: Kind, strike: float, side: Side, qty: int, limit: float | None) -> Fill | None:
        ltp = self._ltp(snap, kind, strike)
        if ltp is None:
            return None
        if limit is None:
            px = ltp
        elif side == Side.BUY:
            px = min(limit, ltp) if ltp <= limit * 1.01 else ltp
        else:
            px = max(limit, ltp) if ltp >= limit * 0.99 else ltp
        signed = qty if side == Side.BUY else -qty
        pos = self.positions.get(symbol)
        if pos is None or pos.qty == 0:
            self.positions[symbol] = Position(symbol=symbol, kind=kind, strike=strike, qty=signed, avg=px, ltp=px)
        elif (pos.qty > 0) == (signed > 0):
            tot = pos.qty + signed
            pos.avg = (pos.avg * pos.qty + px * signed) / tot
            pos.qty = tot
        else:
            closing = min(abs(pos.qty), abs(signed))
            self.realised += (px - pos.avg) * closing * (1 if pos.qty > 0 else -1)
            pos.qty += signed
            if pos.qty == 0:
                del self.positions[symbol]
            elif (pos.qty > 0) != (pos.qty - signed > 0):
                pos.avg = px
        f = Fill(ts=snap.ts, symbol=symbol, side=side, qty=qty, price=px)
        self.fills.append(f)
        self.log.append(f"{snap.ts:%H:%M:%S} {side.value} {qty} {symbol} @ {px:.2f}")
        return f

    # ---- Broker protocol -------------------------------------------------------------------
    def place(self, trade: CandidateTrade, snap: Snapshot) -> list[Fill]:
        out = []
        for l in trade.legs:
            f = self._fill(snap, l.symbol, l.kind, l.strike, l.side, l.lots * trade.lot_size, l.limit)
            if f:
                out.append(f)
        return out

    def mark(self, snap: Snapshot) -> None:
        for p in self.positions.values():
            row = next((r for r in snap.chain if r.strike == p.strike), None)
            if row is None:
                continue
            p.ltp = row.ce_ltp if p.kind == Kind.CE else row.pe_ltp
            p.delta = (row.ce_delta if p.kind == Kind.CE else row.pe_delta) or 0.0
            p.vega = row.vega or 0.0
            p.theta_day = (row.theta or 0.0) * (1 if p.kind == Kind.CE else 1)

    def structure_premium(self, trade: CandidateTrade, snap: Snapshot) -> float | None:
        """Net premium of the structure at current prices, per unit, from the seller's view for shorts."""
        total = 0.0
        for l in trade.legs:
            ltp = self._ltp(snap, l.kind, l.strike)
            if ltp is None:
                return None
            total += ltp if l.side == Side.SELL else -ltp
        return abs(total) if trade.structure.startswith("short") else -total

    def close_structure(self, trade: CandidateTrade, snap: Snapshot, reason: str) -> list[Fill]:
        out = []
        for l in trade.legs:
            side = Side.BUY if l.side == Side.SELL else Side.SELL
            f = self._fill(snap, l.symbol, l.kind, l.strike, side, l.lots * trade.lot_size, None)
            if f:
                out.append(f)
        self.log.append(f"{snap.ts:%H:%M:%S} closed {trade.id} ({reason})")
        return out

    def flatten(self, snap: Snapshot) -> list[Fill]:
        out = []
        for p in list(self.positions.values()):
            side = Side.SELL if p.qty > 0 else Side.BUY
            f = self._fill(snap, p.symbol, p.kind, p.strike, side, abs(p.qty), None)
            if f:
                out.append(f)
        self.log.append(f"{snap.ts:%H:%M:%S} KILL SWITCH: flattened")
        return out

    def state(self, snap: Snapshot, mode: str) -> OrderState:
        unreal = sum(p.pnl for p in self.positions.values())
        return OrderState(ts=snap.ts, mode=mode, open_orders=0, positions=list(self.positions.values()),
                          realised=round(self.realised, 2), unrealised=round(unreal, 2),
                          fills_today=list(self.fills[-50:]))
