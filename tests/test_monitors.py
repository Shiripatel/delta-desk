"""Monitor agents vote on plain rules; the confluence gate fires only when the active set agrees."""
from datetime import UTC, date, datetime, timedelta

import pytest

from deltadesk.agents.monitors import ConfluenceAgent, MaVwapMonitor, RsiMonitor, VolumeMonitor
from deltadesk.analytics.indicators import atr, rsi, vwap
from deltadesk.config import Settings
from deltadesk.feeds.synthetic import SyntheticFeed
from deltadesk.pipeline import Pipeline
from deltadesk.schemas import Bar, ChainStats, Regime, RegimeCall, Signal, Snapshot

T0 = datetime(2026, 9, 18, 9, 15, tzinfo=UTC)


def _bars(closes, volume=60_000, start=T0):
    out, prev = [], closes[0]
    for i, c in enumerate(closes):
        v = volume[i] if isinstance(volume, list) else volume
        out.append(Bar(ts=start + timedelta(minutes=i), open=prev, high=max(prev, c) + 1, low=min(prev, c) - 1, close=c, volume=v))
        prev = c
    return out


def _snap(bars, prev=None, spot=None):
    return Snapshot(ts=bars[-1].ts + timedelta(minutes=1), underlying="NIFTY", spot=spot or bars[-1].close, fut=bars[-1].close + 20,
                    vix=12.0, expiry=date(2026, 9, 22), t_years=0.01, atm=25000, chain=[], bars_1m=bars, prev_bars_1m=prev or [])


def _stats(pcr=1.0):
    return ChainStats(atm_iv=0.12, iv_rank=None, pcr_oi=pcr, max_pain=25000, call_wall=25200, put_wall=24800,
                      expected_move_pts=150, expected_move_pct=0.006, skew=1.0, iv_minus_rv=1.0)


def _settings(**kw):
    return Settings(feed="synthetic", auto_approve=True, cycle_seconds=30, _env_file=None, **kw)


def test_indicators_basics():
    assert rsi([1.0] * 5, 14) == 50.0                       # not enough values
    up = [100 + i for i in range(40)]
    assert rsi(up, 14) == 100.0
    assert 0 < rsi([100 - i * 0.5 + (i % 3) for i in range(60)], 14) < 50
    bars = _bars([100, 101, 102], volume=[1, 1, 2])
    assert abs(vwap(bars) - (sum((b.high + b.low + b.close) / 3 * b.volume for b in bars) / 4)) < 1e-9
    assert vwap(_bars([100, 101], volume=0)) > 0        # falls back to the plain mean without volume
    assert atr(bars, 14) > 0 and atr(bars[:1], 14) == 0


def test_volume_monitor_votes_with_the_surge_direction():
    closes = [25000 + i for i in range(120)]            # slow grind up
    vols = [60_000] * 120
    vols[-12:-3] = [120_000] * 9                         # the last three completed 3-min bars run at 2x
    s = VolumeMonitor().step(_snap(_bars(closes, vols)), None, None, None)
    assert s.vote == 1 and s.name == "volume" and s.reading.startswith("RVOL") and s.value is not None and s.value > 1.5
    quiet = VolumeMonitor().step(_snap(_bars(closes, 60_000)), None, None, None)
    assert quiet.vote == 0
    none = VolumeMonitor().step(_snap(_bars(closes, 0)), None, None, None)
    assert none.vote == 0 and none.reading == "no volume"


def test_ma_vwap_and_rsi_monitors():
    up = _bars([25000 + i * 2 for i in range(150)])
    assert MaVwapMonitor().step(_snap(up), None, None, None).vote == 1
    down = _bars([25300 - i * 2 for i in range(150)])
    assert MaVwapMonitor().step(_snap(down), None, None, None).vote == -1
    assert MaVwapMonitor().step(_snap(up[:30]), None, None, None).vote == 0   # warming up
    r = RsiMonitor().step(_snap(up), None, None, None)
    assert r.vote == 0 and r.value is not None and r.value > 70          # straight line is overbought, not a long vote


def test_confluence_gate_fires_only_on_agreement_and_respects_blocks():
    s = _settings(sniper_monitors=["volume", "ma_vwap", "rsi", "trend"])
    c = ConfluenceAgent(s)
    bars = _bars([25000 + i for i in range(60)])
    snap = _snap(bars)
    regime = RegimeCall(regime=Regime.TRENDING_UP, p=0.7, adx=25.0, realised_vol=0.1)

    def sig(name, vote):
        return Signal(name=name, label=name, vote=vote, reading="r", why="w")
    all_long = [sig("volume", 1), sig("ma_vwap", 1), sig("rsi", 1), sig("trend", 1), sig("options", 0), sig("levels", -1)]
    conf = c.step(snap, regime, _stats(), all_long, True, set(), False)
    assert conf.ready and conf.direction == "LONG" and conf.agree == 4 and conf.required == 4 and conf.blocked is None
    assert conf.stop < conf.entry < conf.target and abs((conf.target - conf.entry) - 2 * (conf.entry - conf.stop)) < 0.05
    assert [x.name for x in conf.signals if x.active] == ["volume", "ma_vwap", "rsi", "trend"]   # inactive monitors still reported
    trig = c.trigger(conf, snap)
    assert trig.zone.source == "confluence" and trig.zone.structures == ["bull_call_spread"] and trig.quality == 1.0
    # one dissenter blocks the gate
    split = [sig("volume", 1), sig("ma_vwap", 1), sig("rsi", -1), sig("trend", 1)]
    assert not c.step(snap, regime, _stats(), split, True, set(), False).ready
    # three of four with a lower bar
    c.configure(["volume", "ma_vwap", "rsi", "trend"], 3)
    three = [sig("volume", 0), sig("ma_vwap", -1), sig("rsi", -1), sig("trend", -1)]
    conf = c.step(snap, regime, _stats(), three, True, set(), False)
    assert conf.ready and conf.direction == "SHORT" and conf.stop > conf.entry > conf.target
    # blocks: window, open trade in that direction, cooldown
    assert c.step(snap, regime, _stats(), three, False, set(), False).blocked == "outside the trading window"
    assert "short" in c.step(snap, regime, _stats(), three, True, {"SHORT"}, False).blocked
    assert c.step(snap, regime, _stats(), three, True, set(), False).blocked.startswith("cooldown")   # trigger() above set last_fire
    with pytest.raises(ValueError):
        c.configure(["volume", "bogus"], None)
    with pytest.raises(ValueError):
        c.configure([], None)
    with pytest.raises(ValueError):
        c.configure(["rsi"], 2)


@pytest.mark.asyncio
async def test_pipeline_emits_signals_every_cycle_and_fires_on_a_trend_day():
    s = _settings()
    pipe = Pipeline(s, SyntheticFeed(s, scenario="trend_up", seed=7, speed=0.0, day=date(2026, 9, 18)))
    await pipe.run(300)
    sig = pipe.bus.history["signals"]
    assert len(sig) == len(pipe.bus.history["snapshot"])
    assert all(a.ok for r in pipe.bus.history["cycle"] for a in r.agents), [a.error for r in pipe.bus.history["cycle"] for a in r.agents if not a.ok]  # noqa: E501
    names = {x.name for x in sig[-1].signals}
    assert names == {"volume", "ma_vwap", "rsi", "trend", "options", "levels"} and sig[-1].active == ["volume", "ma_vwap", "rsi", "trend"]
    fired = [d for d in pipe.decisions.values() if d.trade.source == "confluence"]
    assert fired, "the confluence gate never fired on the trend day"
    d = fired[0]
    assert d.trade.spot_dir == "LONG" and d.trade.spot_stop < d.trade.spot_entry < d.trade.spot_target
    assert d.trade.structure == "bull_call_spread"
