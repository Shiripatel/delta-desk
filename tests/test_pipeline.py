"""End-to-end paper run on the synthetic market: the sniper must fire, strategy must build a typed trade,
risk must rule on it, and the paper broker must hold a book."""
from datetime import date

import pytest

from deltadesk.config import Settings
from deltadesk.feeds.synthetic import SyntheticFeed
from deltadesk.pipeline import Pipeline
from deltadesk.schemas import Decision, Regime, RegimeCall, Trigger

DAY = date(2026, 9, 18)


def _settings(**kw) -> Settings:
    return Settings(feed="synthetic", auto_approve=True, cycle_seconds=30, _env_file=None, **kw)


async def _run(scenario: str, cycles: int) -> Pipeline:
    s = _settings()
    feed = SyntheticFeed(s, scenario=scenario, seed=7, speed=0.0, day=DAY)
    pipe = Pipeline(s, feed)
    await pipe.run(cycles)
    return pipe


@pytest.mark.asyncio
async def test_range_day_produces_a_typed_decision():
    pipe = await _run("range", cycles=420)          # 3.5 market hours at 30 s per cycle
    assert pipe.snapshot is not None and len(pipe.snapshot.chain) >= 30
    reports = pipe.bus.history["cycle"]
    assert all(a.ok for r in reports for a in r.agents), [a.error for r in reports for a in r.agents if not a.ok]
    assert pipe.decisions, "sniper never fired on a range day"
    d = next(iter(pipe.decisions.values()))
    assert isinstance(d, Decision)
    Decision.model_validate_json(d.model_dump_json())   # schema round-trip
    assert 0 <= d.trade.confidence <= 1 and d.trade.legs
    assert any(x.state in ("executed", "held", "vetoed") for x in pipe.decisions.values())


@pytest.mark.asyncio
async def test_kill_switch_flattens():
    pipe = await _run("range", cycles=420)
    executed = [d for d in pipe.decisions.values() if d.state == "executed"]
    if not executed:
        pytest.skip("no fill in this seed")
    assert pipe.orders and pipe.orders.positions
    out = pipe.kill()
    assert out is not None and not out.positions and pipe.killed


@pytest.mark.asyncio
async def test_strategy_and_risk_on_fixed_trigger():
    s = _settings()
    feed = SyntheticFeed(s, scenario="range", seed=3, speed=0.0, day=DAY)
    pipe = Pipeline(s, feed)
    await pipe.start()
    await pipe.cycle()
    await pipe.cycle()
    snap, plan = pipe.snapshot, pipe.plan
    assert snap is not None and plan is not None
    regime = RegimeCall(regime=Regime.RANGE_BOUND, p=0.8, adx=14.0, realised_vol=0.10)
    stats = pipe.chain.step(snap, 0.10)
    zone = next(z for z in plan.zones if z.id == "PDH_FADE")
    trig = Trigger(ts=snap.ts, zone=zone, spot=snap.spot, quality=0.8, why="test")
    trade = pipe.strategy.step(trig, snap, regime, stats, plan)
    assert trade is not None and trade.structure == "short_call_spread" and len(trade.legs) == 2
    assert trade.legs[0].strike < trade.legs[1].strike
    book = pipe.broker.state(snap, mode="paper")
    verdict = pipe.risk.step(trade, snap, book, 0.0)
    assert verdict.max_loss > 0
    # outside the trading window the risk agent must veto
    late = snap.model_copy(update={"ts": snap.ts.replace(hour=15, minute=10)})
    assert not pipe.risk.step(trade, late, book, 0.0).risk_ok
    await feed.close()
