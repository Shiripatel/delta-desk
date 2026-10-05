"""Small, dependency-free indicators on Bar lists."""
from __future__ import annotations

import math

from deltadesk.schemas import Bar


def realised_vol(bars: list[Bar], window: int = 20, bars_per_year: float = 252 * 375) -> float:
    closes = [b.close for b in bars[-(window + 1):]]
    if len(closes) < 3:
        return 0.0
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    mean = sum(rets) / len(rets)
    var = sum((x - mean) ** 2 for x in rets) / max(1, len(rets) - 1)
    return math.sqrt(var * bars_per_year)


def adx(bars: list[Bar], period: int = 14) -> float:
    """Wilder's ADX. Returns 0 until enough bars exist."""
    if len(bars) < 2 * period + 1:
        return 0.0
    trs, pdms, ndms = [], [], []
    for i in range(1, len(bars)):
        h, l, pc = bars[i].high, bars[i].low, bars[i - 1].close
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        up, dn = h - bars[i - 1].high, bars[i - 1].low - l
        pdms.append(up if up > dn and up > 0 else 0.0)
        ndms.append(dn if dn > up and dn > 0 else 0.0)

    def wilder(xs: list[float]) -> list[float]:
        s = sum(xs[:period])
        out = [s]
        for x in xs[period:]:
            s = s - s / period + x
            out.append(s)
        return out

    tr_s, pdm_s, ndm_s = wilder(trs), wilder(pdms), wilder(ndms)
    dxs = []
    for t, p, n in zip(tr_s, pdm_s, ndm_s, strict=False):
        if t == 0:
            dxs.append(0.0)
            continue
        pdi, ndi = 100 * p / t, 100 * n / t
        dxs.append(100 * abs(pdi - ndi) / (pdi + ndi) if pdi + ndi else 0.0)
    if len(dxs) < period:
        return 0.0
    a = sum(dxs[:period]) / period
    for d in dxs[period:]:
        a = (a * (period - 1) + d) / period
    return a


def ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    k = 2 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def resample(bars: list[Bar], minutes: int) -> list[Bar]:
    out: list[Bar] = []
    for b in bars:
        slot = b.ts.replace(minute=(b.ts.minute // minutes) * minutes, second=0, microsecond=0)
        if out and out[-1].ts == slot:
            last = out[-1]
            out[-1] = Bar(ts=slot, open=last.open, high=max(last.high, b.high),
                          low=min(last.low, b.low), close=b.close, volume=last.volume + b.volume)
        else:
            out.append(Bar(ts=slot, open=b.open, high=b.high, low=b.low, close=b.close, volume=b.volume))
    return out


def rsi(values: list[float], period: int = 14) -> float:
    """Wilder RSI on closes; 50 until there are enough values."""
    if len(values) < period + 1:
        return 50.0
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = values[i] - values[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    ag, al = gains / period, losses / period
    for i in range(period + 1, len(values)):
        d = values[i] - values[i - 1]
        ag = (ag * (period - 1) + max(d, 0.0)) / period
        al = (al * (period - 1) + max(-d, 0.0)) / period
    if al == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + ag / al)


def vwap(bars: list[Bar]) -> float:
    """Volume-weighted average of the typical price; falls back to the plain mean when the feed has no volume."""
    if not bars:
        return 0.0
    num = den = 0.0
    for b in bars:
        tp = (b.high + b.low + b.close) / 3
        num += tp * b.volume
        den += b.volume
    if den <= 0:
        return sum((b.high + b.low + b.close) / 3 for b in bars) / len(bars)
    return num / den


def atr(bars: list[Bar], period: int = 14) -> float:
    """Average true range over the last `period` bars (simple mean); 0 with fewer than two bars."""
    if len(bars) < 2:
        return 0.0
    trs = []
    for i in range(1, len(bars)):
        h, lo, pc = bars[i].high, bars[i].low, bars[i - 1].close
        trs.append(max(h - lo, abs(h - pc), abs(lo - pc)))
    trs = trs[-period:]
    return sum(trs) / len(trs)
