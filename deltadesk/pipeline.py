"""The desk: one cycle every `cycle_seconds` of market time, agents in a fixed order, typed outputs on the bus.

Topics: plan, snapshot, regime, chain, trigger, decision, orders, cycle, log
"""
from __future__ import annotations

import time as _time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from deltadesk.agents.chain_agent import ChainAgent
from deltadesk.agents.exec_agent import ExecAgent
from deltadesk.agents.feed_agent import FeedAgent
from deltadesk.agents.planner import PlannerAgent
from deltadesk.agents.regime import RegimeAgent
from deltadesk.agents.risk import RiskAgent
from deltadesk.agents.sniper import SniperAgent
from deltadesk.agents.strategy import StrategyAgent
from deltadesk.broker.base import Broker
from deltadesk.broker.paper import PaperBroker
from deltadesk.bus import Bus
from deltadesk.config import Settings
from deltadesk.feeds.base import Feed, FeedEnded
from deltadesk.schemas import AgentStatus, Bar, CycleReport, DayPlan, Decision, OrderState, Snapshot


class Pipeline:
    def __init__(self, settings: Settings, feed: Feed, broker: Broker | None = None, bus: Bus | None = None,
                 on_event: Callable[[str, object], None] | None = None) -> None:
        self.s = settings
        self.feed = feed
        self.bus = bus or Bus()
        self.broker = broker or PaperBroker()
        self.on_event = on_event
        self.planner = PlannerAgent(settings)
        self.regime = RegimeAgent()
        self.chain = ChainAgent()
        self.sniper = SniperAgent(settings)
        self.strategy = StrategyAgent(settings)
        self.risk = RiskAgent(settings)
        self.exec = ExecAgent(settings, self.broker)
        self.feed_agent: FeedAgent | None = None
        self.plan: DayPlan | None = None
        self.prev_bars: list[Bar] = []
        self.decisions: dict[str, Decision] = {}
        self.snapshot: Snapshot | None = None
        self.orders: OrderState | None = None
        self.seq = 0
        self.killed = False
        self.started = False

    # ---- lifecycle ------------------------------------------------------------------------
    def _emit(self, topic: str, msg) -> None:
        self.bus.publish(topic, msg)
        if self.on_event:
            self.on_event(topic, msg)

    async def start(self) -> None:
        await self.feed.connect()
        instruments = await self.feed.instruments(self.s.underlying)
        await self.feed.subscribe([i.token for i in instruments])
        self.feed_agent = FeedAgent(self.s, self.feed, instruments)
        lots = [i.lot_size for i in instruments if i.kind.value in ("CE", "PE") and i.lot_size > 1]
        if lots and lots[0] != self.s.lot_size:
            self._emit("log", f"feed: lot size {lots[0]} from instrument master (config said {self.s.lot_size})")
            self.s.lot_size = lots[0]
        self.prev_bars = await self.feed.history(self.s.underlying)
        day = datetime.now(UTC).date()
        self.plan = self.planner.step(day, self.prev_bars)
        self._emit("plan", self.plan)
        self._emit("log", f"planner: {' '.join(self.plan.notes)}")
        self.started = True

    async def run(self, cycles: int | None = None) -> None:
        if not self.started:
            await self.start()
        n = 0
        try:
            while cycles is None or n < cycles:
                await self.cycle()
                n += 1
        except FeedEnded:
            self._emit("log", "feed ended")
        finally:
            await self.feed.close()

    # ---- one cycle ------------------------------------------------------------------------
    async def cycle(self) -> CycleReport:
        assert self.feed_agent is not None and self.plan is not None
        fa = self.feed_agent
        t0 = _time.perf_counter()
        statuses: list[AgentStatus] = []
        if fa.last_ts is None:
            await fa.pump_until(datetime.min.replace(tzinfo=UTC), timeout=30)
        target = (fa.last_ts or datetime.now(UTC)) + timedelta(seconds=self.s.cycle_seconds)
        await fa.pump_until(target, timeout=max(5.0, self.s.cycle_seconds * 2))
        self.seq += 1

        snap = self._timed(statuses, fa, lambda: fa.snapshot(self.prev_bars))
        if snap is None or len(snap.chain) < 5:
            rep = CycleReport(ts=fa.last_ts or datetime.now(UTC), seq=self.seq,
                              ms=(_time.perf_counter() - t0) * 1000, agents=statuses)
            self._emit("cycle", rep)
            return rep
        self.snapshot = snap
        self._emit("snapshot", snap)

        regime = self._timed(statuses, self.regime, lambda: self.regime.step(snap, self.plan))
        stats = self._timed(statuses, self.chain, lambda: self.chain.step(snap, regime.realised_vol))
        self._emit("regime", regime)
        self._emit("chain", stats)

        book = self.orders or self.broker.state(snap, mode=self.s.mode)
        day_pnl = book.realised + book.unrealised
        open_ids = {d.trade.zone_id for d in self.exec.open.values()}
        margin_used = sum(d.risk.margin for d in self.exec.open.values())
        at_capacity = len(self.exec.open) >= self.s.limits.max_open_structures
        trigger = None if (self.killed or at_capacity) else self._timed(
            statuses, self.sniper, lambda: self.sniper.step(snap, self.plan, regime, stats, open_ids))
        if trigger is not None:
            self._emit("trigger", trigger)
            self._emit("log", f"sniper: {trigger.zone.id} fired q={trigger.quality:.2f}")
            trade = self._timed(statuses, self.strategy,
                                lambda: self.strategy.step(trigger, snap, regime, stats, self.plan))
            if trade is not None:
                verdict = self._timed(statuses, self.risk, lambda: self.risk.step(
                    trade, snap, book, day_pnl, margin_used, len(self.exec.open)))
                if not verdict.risk_ok:
                    state = "vetoed"
                elif trade.confidence < self.s.confidence_threshold:
                    state = "held"
                elif self.s.auto_approve and self.s.mode == "paper":
                    state = "approved"
                else:
                    state = "awaiting_approval"
                d = Decision(id=trade.id, ts=snap.ts, trade=trade, risk=verdict,
                             threshold=self.s.confidence_threshold, state=state)
                if state == "approved":
                    d = self.exec.execute(d, snap)
                self.decisions[d.id] = d
                self._emit("decision", d)
                self._emit("log", f"{d.id} {trade.structure} conf={trade.confidence:.2f} -> {d.state}"
                                  + (f" ({'; '.join(verdict.reasons)})" if verdict.reasons else ""))

        for d in list(self.decisions.values()):
            if d.state == "awaiting_approval" and snap.ts > d.trade.valid_until:
                self.decisions[d.id] = d.model_copy(update={"state": "expired"})
                self._emit("decision", self.decisions[d.id])

        self.orders = self._timed(statuses, self.exec, lambda: self.exec.step(snap))
        self._emit("orders", self.orders)
        rep = CycleReport(ts=snap.ts, seq=self.seq, ms=(_time.perf_counter() - t0) * 1000, agents=statuses)
        self._emit("cycle", rep)
        return rep

    @staticmethod
    def _timed(statuses: list[AgentStatus], agent, fn):
        t0 = _time.perf_counter()
        try:
            out = fn()
            statuses.append(AgentStatus(name=agent.name, version=agent.version, ok=True,
                                        ms=(_time.perf_counter() - t0) * 1000, summary=_summary(out)))
            return out
        except Exception as e:  # noqa: BLE001 - one agent failing must not kill the cycle
            statuses.append(AgentStatus(name=agent.name, version=agent.version, ok=False,
                                        ms=(_time.perf_counter() - t0) * 1000, error=repr(e)))
            return None

    # ---- human controls -------------------------------------------------------------------
    def approve(self, decision_id: str) -> Decision:
        d = self.decisions[decision_id]
        if d.state != "awaiting_approval" or self.snapshot is None:
            return d
        d = self.exec.execute(d.model_copy(update={"state": "approved"}), self.snapshot)
        self.decisions[d.id] = d
        self._emit("decision", d)
        self._emit("log", f"{d.id} approved by human -> {d.state}")
        return d

    def reject(self, decision_id: str) -> Decision:
        d = self.decisions[decision_id]
        if d.state == "awaiting_approval":
            d = d.model_copy(update={"state": "rejected"})
            self.decisions[d.id] = d
            self._emit("decision", d)
        return d

    def kill(self) -> OrderState | None:
        self.killed = True
        if self.snapshot is None:
            return None
        self.orders = self.exec.kill(self.snapshot)
        for z in (self.plan.zones if self.plan else []):
            z.armed = False
        self._emit("orders", self.orders)
        self._emit("log", "KILL SWITCH: flattened, zones disarmed")
        return self.orders


def _summary(out) -> str:
    if out is None:
        return "idle"
    n = type(out).__name__
    if n == "Snapshot":
        return f"spot {out.spot:,.2f} · {len(out.chain)} strikes"
    if n == "RegimeCall":
        return f"{out.regime.value} · {out.p:.2f}"
    if n == "ChainStats":
        return f"IV {out.atm_iv*100:.1f}% · PCR {out.pcr_oi:.2f} · ±{out.expected_move_pts:.0f}"
    if n == "Trigger":
        return f"{out.zone.id} q={out.quality:.2f}"
    if n == "CandidateTrade":
        return f"{out.structure} conf={out.confidence:.2f}"
    if n == "RiskVerdict":
        return "APPROVED" if out.risk_ok else "VETO"
    if n == "OrderState":
        return f"{len(out.positions)} pos · P&L {out.realised + out.unrealised:+,.0f}"
    return n
