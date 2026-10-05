"""Monitor agents and the confluence gate.

Each monitor watches one thing on the live tape and votes +1 (long), 0 (neutral) or -1 (short) with the reading
that produced the vote. The confluence agent is the AND gate over the monitors the user has dragged onto the
desk: when every active monitor agrees (or `required` of them, with no dissent) it writes one Trigger with the
entry, stop and target in underlying points. Strategy, risk and exec then treat it like any other trigger.

Transparent rules, v0. Thresholds are deliberately plain so the page can state them in one sentence each.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from deltadesk.analytics.indicators import atr, ema, resample, rsi, vwap
from deltadesk.config import Settings
from deltadesk.schemas import (
    ChainStats,
    Confluence,
    DayPlan,
    Regime,
    RegimeCall,
    Signal,
    Snapshot,
    Trigger,
    Zone,
    ZoneKind,
)

TF_MIN = 3          # the monitors read 3-minute bars


def bars_tf(snap: Snapshot, minutes: int = TF_MIN, keep: int = 160) -> list:
    """Yesterday plus today resampled, most recent `keep` bars."""
    return resample(snap.prev_bars_1m + snap.bars_1m, minutes)[-keep:]


class _Monitor:
    name = ""
    label = ""
    desc = ""
    icon = ""
    version = "0.1"

    def step(self, snap: Snapshot, regime: RegimeCall, stats: ChainStats, plan: DayPlan | None) -> Signal:
        raise NotImplementedError

    def _sig(self, vote: int, reading: str, why: str, value: float | None = None) -> Signal:
        return Signal(name=self.name, label=self.label, vote=vote, reading=reading, why=why, value=value)


class VolumeMonitor(_Monitor):
    name, label, icon = "volume", "Volume", "bars"
    desc = "Relative volume: the last three completed 3-min bars against the twenty before them; 1.2x or more votes with the move."

    def step(self, snap, regime, stats, plan):
        bars = bars_tf(snap)
        done = bars[:-1]                                             # the forming bar is partial
        if len(done) < 10 or all(b.volume == 0 for b in done):
            return self._sig(0, "no volume", "This feed carries no volume yet, so the volume agent stays neutral.")
        recent, base = done[-3:], done[-23:-3]
        rv = sum(b.volume for b in recent) / len(recent)
        bv = sum(b.volume for b in base) / len(base) if base else 0.0
        rvol = rv / bv if bv else 0.0
        move = recent[-1].close - recent[0].open
        vote = (1 if move > 0 else -1) if rvol >= 1.2 and move != 0 else 0
        why = (f"Relative volume {rvol:.2f}x over the last three 3-min bars while price moved {move:+,.0f}"
               + (": participation confirms the move." if vote else "; below 1.2x nothing is confirmed."))
        return self._sig(vote, f"RVOL {rvol:.2f}x", why, round(rvol, 2))


class MaVwapMonitor(_Monitor):
    name, label, icon = "ma_vwap", "MA / VWAP", "cross"
    desc = "EMA 9 against EMA 21 on 3-min closes, and spot against the session VWAP; both must agree."

    def step(self, snap, regime, stats, plan):
        bars = bars_tf(snap)
        closes = [b.close for b in bars]
        if len(closes) < 22:
            return self._sig(0, "warming up", "Fewer than 22 three-minute bars so far; the averages are not stable yet.")
        e9, e21 = ema(closes[-60:], 9), ema(closes[-90:], 21)
        vw = vwap(snap.bars_1m) if snap.bars_1m else snap.spot
        above_ma, above_vw = e9 > e21, snap.spot > vw
        vote = 1 if above_ma and above_vw else -1 if (not above_ma and not above_vw) else 0
        reading = f"EMA9 {'>' if above_ma else '<'} EMA21 · {'above' if above_vw else 'below'} VWAP"
        why = (f"EMA9 {e9:,.0f} is {'above' if above_ma else 'below'} EMA21 {e21:,.0f} and spot {snap.spot:,.0f} is "
               f"{'above' if above_vw else 'below'} VWAP {vw:,.0f}" + ("; both agree." if vote else "; they disagree, so neutral."))
        return self._sig(vote, reading, why, round(snap.spot - vw, 1))


class RsiMonitor(_Monitor):
    name, label, icon = "rsi", "RSI", "wave"
    desc = "RSI(14) on 3-min closes: 55-70 votes long, 30-45 votes short; the middle and the extremes are neutral."

    def step(self, snap, regime, stats, plan):
        closes = [b.close for b in bars_tf(snap)]
        r = rsi(closes[-120:], 14)
        vote = 1 if 55 <= r <= 70 else -1 if 30 <= r <= 45 else 0
        zone = ("bullish momentum, not yet overbought" if vote == 1 else "bearish momentum, not yet oversold" if vote == -1
                else "overbought" if r > 70 else "oversold" if r < 30 else "no momentum either way")
        return self._sig(vote, f"RSI {r:.0f}", f"RSI(14) on 3-min closes is {r:.0f}: {zone}.", round(r, 1))


class TrendMonitor(_Monitor):
    name, label, icon = "trend", "Trend", "trend"
    desc = "The regime agent's call: trending up votes long, trending down votes short, range or event is neutral."

    def step(self, snap, regime, stats, plan):
        vote = 1 if regime.regime == Regime.TRENDING_UP else -1 if regime.regime == Regime.TRENDING_DOWN else 0
        label = regime.regime.value.replace("_", " ").lower()
        return self._sig(vote, f"{label} · ADX {regime.adx:.0f}",
                         f"Regime {label} with confidence {regime.p:.2f} and ADX {regime.adx:.0f}"
                         + ("." if vote else ": no directional edge."), round(regime.adx, 1))


class OptionsMonitor(_Monitor):
    name, label, icon = "options", "Options", "options"
    desc = "Put-call ratio on open interest: 1.05 or more votes long (put writers confident), 0.85 or less votes short."

    def step(self, snap, regime, stats, plan):
        pcr = stats.pcr_oi
        vote = 1 if pcr >= 1.05 else -1 if pcr <= 0.85 else 0
        return self._sig(vote, f"PCR {pcr:.2f} · max pain {stats.max_pain:,.0f}",
                         f"PCR {pcr:.2f} on OI" + (" shows put writers confident: long." if vote == 1 else
                                                   " shows call writers confident: short." if vote == -1 else " is balanced."),
                         round(pcr, 2))


class LevelsMonitor(_Monitor):
    name, label, icon = "levels", "Levels", "levels"
    desc = "Spot against yesterday's high and low: above PDH votes long, below PDL votes short, inside is neutral."

    def step(self, snap, regime, stats, plan):
        if plan is None:
            return self._sig(0, "no plan", "No day plan yet.")
        vote = 1 if snap.spot > plan.pdh else -1 if snap.spot < plan.pdl else 0
        where = "above PDH" if vote == 1 else "below PDL" if vote == -1 else "inside yesterday's range"
        return self._sig(vote, where, f"Spot {snap.spot:,.0f} is {where} ({plan.pdl:,.0f} - {plan.pdh:,.0f}).",
                         round(snap.spot - plan.pdc, 1))


MONITORS: list[type[_Monitor]] = [VolumeMonitor, MaVwapMonitor, RsiMonitor, TrendMonitor, OptionsMonitor, LevelsMonitor]


class ConfluenceAgent:
    """AND gate over the active monitors; writes the trigger with entry, stop and target on the underlying."""
    name = "confluence"
    version = "0.1"

    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.monitors: dict[str, _Monitor] = {cls.name: cls() for cls in MONITORS}
        self.active: list[str] = []
        self.required: int | None = None
        self.configure(settings.sniper_monitors, settings.sniper_required)
        self.cooldown = timedelta(minutes=settings.sniper_cooldown_min)
        self.last_fire: datetime | None = None
        self.last: Confluence | None = None

    def catalogue(self) -> list[dict]:
        return [{"name": m.name, "label": m.label, "desc": m.desc, "icon": m.icon} for m in self.monitors.values()]

    def configure(self, active: list[str], required: int | None) -> None:
        names = [n for n in dict.fromkeys(active)]
        unknown = [n for n in names if n not in self.monitors]
        if unknown:
            raise ValueError(f"unknown monitor: {', '.join(unknown)}")
        if not names:
            raise ValueError("at least one monitor must be active")
        if required is not None and not (1 <= required <= len(names)):
            raise ValueError(f"required must be between 1 and {len(names)}")
        self.active, self.required = names, required

    def step(self, snap: Snapshot, regime: RegimeCall, stats: ChainStats, signals: list[Signal],
             in_window: bool, open_dirs: set[str], blocked_by_desk: bool) -> Confluence:
        for s in signals:
            s.active = s.name in self.active
        act = [s for s in signals if s.active]
        req = min(self.required or len(act), len(act)) if act else 0
        longs = sum(1 for s in act if s.vote > 0)
        shorts = sum(1 for s in act if s.vote < 0)
        if act and longs >= req and shorts == 0:
            direction, agree = "LONG", longs
        elif act and shorts >= req and longs == 0:
            direction, agree = "SHORT", shorts
        else:
            direction, agree = "NONE", max(longs, shorts)
        ready = direction != "NONE"
        a = atr(bars_tf(snap)[-40:], 14) or snap.spot * 0.001
        risk = max(1.5 * a, snap.spot * 0.001)     # stop 1.5 ATR away (at least 0.1 %), target twice that
        entry = round(snap.spot, 2)
        stop = target = None
        if ready:
            sign = 1 if direction == "LONG" else -1
            stop, target = round(entry - sign * risk, 2), round(entry + sign * 2 * risk, 2)
        if not act:
            why = "No monitor on the desk."
        elif ready:
            agreeing = [s for s in act if s.vote and (s.vote > 0) == (direction == "LONG")]
            why = f"{agree} of {len(act)} agree {direction}: " + "; ".join(f"{s.label} {s.reading}" for s in agreeing)
        elif longs and shorts:
            why = f"Votes split {longs} long / {shorts} short: " + "; ".join(f"{s.label} {s.reading}" for s in act if s.vote)
        else:
            side = "long" if longs else "short"
            why = (f"{agree} of {len(act)} lean {side}, needs {req}: " if agree else f"All {len(act)} neutral: ") + \
                  "; ".join(f"{s.label} {s.reading}" for s in act)
        blocked = None
        if ready:
            if blocked_by_desk:
                blocked = "desk is killed or at capacity"
            elif not in_window:
                blocked = "outside the trading window"
            elif direction in open_dirs:
                blocked = f"already in a {direction.lower()} trade"
            elif self.last_fire is not None and snap.ts - self.last_fire < self.cooldown:
                left = int((self.cooldown - (snap.ts - self.last_fire)).total_seconds() // 60) + 1
                blocked = f"cooldown, {left} min left"
        self.last = Confluence(ts=snap.ts, signals=signals, active=list(self.active), required=req, agree=agree,
                               direction=direction, ready=ready, why=why, entry=entry, stop=stop, target=target,
                               atr=round(a, 2), blocked=blocked)
        return self.last

    def trigger(self, conf: Confluence, snap: Snapshot) -> Trigger:
        up = conf.direction == "LONG"
        zone = Zone(id=f"CONFLUENCE_{conf.direction}", kind=ZoneKind.BREAK, lo=round(snap.spot - (conf.atr or 0), 2),
                    hi=round(snap.spot + (conf.atr or 0), 2), source="confluence", direction="UP" if up else "DOWN",
                    compatible=list(Regime), structures=["bull_call_spread" if up else "bear_put_spread"], armed=True,
                    fired_at=snap.ts)
        self.last_fire = snap.ts
        return Trigger(ts=snap.ts, zone=zone, spot=snap.spot, quality=round(conf.agree / max(1, len(conf.active)), 2), why=conf.why)
