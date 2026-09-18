"""exec.agent: routes approved decisions to the broker, manages exits, reports the book."""
from __future__ import annotations

from datetime import datetime

from deltadesk.broker.base import Broker
from deltadesk.config import Settings
from deltadesk.schemas import Decision, OrderState, Snapshot


class ExecAgent:
    name = "exec"
    version = "0.1"

    def __init__(self, settings: Settings, broker: Broker) -> None:
        self.s = settings
        self.broker = broker
        self.open: dict[str, Decision] = {}        # decision id -> decision with live legs

    def execute(self, d: Decision, snap: Snapshot) -> Decision:
        fills = self.broker.place(d.trade, snap)
        if fills:
            d = d.model_copy(update={"state": "executed"})
            self.open[d.id] = d
        return d

    def step(self, snap: Snapshot) -> OrderState:
        """Mark the book, apply stop / target / expiry exits, return the order state."""
        self.broker.mark(snap)
        for did, d in list(self.open.items()):
            net = self.broker.structure_premium(d.trade, snap)   # current cost to close, per unit
            if net is None:
                continue
            short = d.trade.structure.startswith("short")
            hit_stop = d.trade.stop is not None and ((net >= d.trade.stop) if short else (net <= d.trade.stop))
            hit_target = d.trade.target is not None and ((net <= d.trade.target) if short else (net >= d.trade.target))
            expiring = snap.ts >= datetime.combine(snap.expiry, datetime.min.time(), snap.ts.tzinfo).replace(hour=15, minute=20)
            if hit_stop or hit_target or expiring:
                self.broker.close_structure(d.trade, snap, reason="stop" if hit_stop else "target" if hit_target else "expiry")
                self.open.pop(did, None)
        return self.broker.state(snap, mode=self.s.mode)

    def kill(self, snap: Snapshot) -> OrderState:
        self.broker.flatten(snap)
        self.open.clear()
        return self.broker.state(snap, mode=self.s.mode)
