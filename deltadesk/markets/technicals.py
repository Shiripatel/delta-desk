"""Technical analysis read model: indicators, moving averages, pivot points and a summary per timeframe.

Computed from the same bars the chart uses. The layout mirrors what retail traders expect from a technicals
page: a summary strip (per timeframe, from the balance of buy and sell readings), an indicators table with a
value and an action for each, a moving-averages table (simple and exponential) and pivot-point tables
(classic, Fibonacci, Camarilla, Woodie, DeMark). Rules only; not advice.
"""
from __future__ import annotations

from math import isfinite

TIMEFRAMES: dict[str, tuple[str, str]] = {"15m": ("5d", "15 minutes"), "1h": ("1m", "1 hour"), "daily": ("1y", "Daily"),
                                         "weekly": ("5y", "Weekly"), "monthly": ("all", "Monthly")}
MA_PERIODS = [5, 10, 20, 50, 100, 200]


def _sma(v: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(v)
    s = 0.0
    for i, x in enumerate(v):
        s += x
        if i >= n:
            s -= v[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def _ema(v: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(v)
    if len(v) < n:
        return out
    k = 2 / (n + 1)
    e = sum(v[:n]) / n
    out[n - 1] = e
    for i in range(n, len(v)):
        e = v[i] * k + e * (1 - k)
        out[i] = e
    return out


def _rsi(c: list[float], n: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(c)
    if len(c) <= n:
        return out
    g = l = 0.0
    for i in range(1, n + 1):
        d = c[i] - c[i - 1]
        g += max(d, 0)
        l += max(-d, 0)
    g, l = g / n, l / n
    out[n] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    for i in range(n + 1, len(c)):
        d = c[i] - c[i - 1]
        g = (g * (n - 1) + max(d, 0)) / n
        l = (l * (n - 1) + max(-d, 0)) / n
        out[i] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    return out


def _tr(h: list[float], lo: list[float], c: list[float]) -> list[float]:
    return [h[0] - lo[0]] + [max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1])) for i in range(1, len(c))]


def _wilder(v: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(v)
    if len(v) < n:
        return out
    a = sum(v[:n]) / n
    out[n - 1] = a
    for i in range(n, len(v)):
        a = (a * (n - 1) + v[i]) / n
        out[i] = a
    return out


def _adx(h: list[float], lo: list[float], c: list[float], n: int = 14) -> tuple[float | None, float | None, float | None]:
    if len(c) < 2 * n + 1:
        return None, None, None
    tr = _tr(h, lo, c)
    pdm = [0.0] + [max(h[i] - h[i - 1], 0) if (h[i] - h[i - 1]) > (lo[i - 1] - lo[i]) else 0.0 for i in range(1, len(c))]
    mdm = [0.0] + [max(lo[i - 1] - lo[i], 0) if (lo[i - 1] - lo[i]) > (h[i] - h[i - 1]) else 0.0 for i in range(1, len(c))]
    atr, pw, mw = _wilder(tr, n), _wilder(pdm, n), _wilder(mdm, n)
    pdi = [100 * pw[i] / atr[i] if atr[i] and pw[i] is not None else None for i in range(len(c))]
    mdi = [100 * mw[i] / atr[i] if atr[i] and mw[i] is not None else None for i in range(len(c))]
    dx = [abs(pdi[i] - mdi[i]) / (pdi[i] + mdi[i]) * 100 if pdi[i] is not None and mdi[i] is not None and (pdi[i] + mdi[i]) else None for i in range(len(c))]  # noqa: E501
    dxs = [x for x in dx if x is not None]
    if len(dxs) < n:
        return None, pdi[-1], mdi[-1]
    a = sum(dxs[:n]) / n
    for x in dxs[n:]:
        a = (a * (n - 1) + x) / n
    return a, pdi[-1], mdi[-1]


def _act(kind: str, v: float | None, **kw) -> str:
    if v is None:
        return "—"
    if kind == "band":       # overbought / oversold with a midline
        hi, lo, mid = kw["hi"], kw["lo"], kw.get("mid", (kw["hi"] + kw["lo"]) / 2)
        return "Overbought" if v > hi else "Oversold" if v < lo else "Buy" if v > mid else "Sell"
    if kind == "sign":
        return "Buy" if v > 0 else "Sell" if v < 0 else "Neutral"
    return "Neutral"


def indicators(o: list[float], h: list[float], lo: list[float], c: list[float]) -> list[dict]:
    n = len(c)
    out: list[dict] = []
    rsi = _rsi(c, 14)
    out.append({"name": "RSI (14)", "value": rsi[-1], "action": _act("band", rsi[-1], hi=70, lo=30, mid=50), "decimals": 2})
    # stochastic 9,6
    k = [None] * n
    for i in range(8, n):
        hh, ll = max(h[i - 8:i + 1]), min(lo[i - 8:i + 1])
        k[i] = 50.0 if hh == ll else (c[i] - ll) / (hh - ll) * 100
    ks = [x for x in k if x is not None]
    st = sum(ks[-6:]) / 6 if len(ks) >= 6 else None
    out.append({"name": "STOCH (9,6)", "value": st, "action": _act("band", st, hi=80, lo=20, mid=50), "decimals": 2})
    rs = [x for x in rsi if x is not None]
    srsi = None
    if len(rs) >= 14:
        w = rs[-14:]
        srsi = 50.0 if max(w) == min(w) else (rs[-1] - min(w)) / (max(w) - min(w)) * 100
    out.append({"name": "STOCHRSI (14)", "value": srsi, "action": _act("band", srsi, hi=80, lo=20, mid=50), "decimals": 2})
    e12, e26 = _ema(c, 12), _ema(c, 26)
    macd = [e12[i] - e26[i] if e12[i] is not None and e26[i] is not None else None for i in range(n)]
    ml = [x for x in macd if x is not None]
    sig = _ema(ml, 9)[-1] if len(ml) >= 9 else None
    mv = ml[-1] if ml else None
    out.append({"name": "MACD (12,26)", "value": mv, "action": "—" if mv is None or sig is None else "Buy" if mv > sig else "Sell", "decimals": 2})  # noqa: E501
    adx, pdi, mdi = _adx(h, lo, c, 14)
    out.append({"name": "ADX (14)", "value": adx, "action": "—" if adx is None or pdi is None or mdi is None else ("Buy" if pdi > mdi else "Sell") if adx >= 25 else "Neutral", "decimals": 2})  # noqa: E501
    wr = None
    if n >= 14:
        hh, ll = max(h[-14:]), min(lo[-14:])
        wr = 0.0 if hh == ll else (hh - c[-1]) / (hh - ll) * -100
    out.append({"name": "Williams %R", "value": wr, "action": _act("band", wr, hi=-20, lo=-80, mid=-50), "decimals": 2})
    cci = None
    if n >= 14:
        tp = [(h[i] + lo[i] + c[i]) / 3 for i in range(n)]
        w = tp[-14:]
        m = sum(w) / 14
        md = sum(abs(x - m) for x in w) / 14
        cci = 0.0 if md == 0 else (tp[-1] - m) / (0.015 * md)
    out.append({"name": "CCI (14)", "value": cci, "action": "—" if cci is None else "Buy" if cci > 100 else "Sell" if cci < -100 else "Neutral", "decimals": 2})  # noqa: E501
    atr = _wilder(_tr(h, lo, c), 14)[-1] if n >= 14 else None
    out.append({"name": "ATR (14)", "value": atr, "action": "—" if atr is None else ("High volatility" if atr / c[-1] > 0.02 else "Less volatility"), "decimals": 2})  # noqa: E501
    hl = None
    if n >= 14:
        hl = (c[-1] - min(lo[-14:])) - (max(h[-14:]) - c[-1])
    out.append({"name": "Highs / Lows (14)", "value": hl, "action": _act("sign", hl), "decimals": 2})
    uo = None
    if n >= 29:
        bp = [c[i] - min(lo[i], c[i - 1]) for i in range(1, n)]
        tr = [max(h[i], c[i - 1]) - min(lo[i], c[i - 1]) for i in range(1, n)]
        def avg(m: int) -> float:
            t = sum(tr[-m:])
            return sum(bp[-m:]) / t if t else 0.0
        uo = 100 * (4 * avg(7) + 2 * avg(14) + avg(28)) / 7
    out.append({"name": "Ultimate oscillator", "value": uo, "action": _act("band", uo, hi=70, lo=30, mid=50), "decimals": 2})
    roc = (c[-1] / c[-13] - 1) * 100 if n >= 13 and c[-13] else None
    out.append({"name": "ROC (12)", "value": roc, "action": _act("sign", roc), "decimals": 2})
    e13 = _ema(c, 13)[-1]
    bb = (h[-1] - e13) + (lo[-1] - e13) if e13 is not None else None
    out.append({"name": "Bull / Bear power (13)", "value": bb, "action": _act("sign", bb), "decimals": 2})
    for r in out:
        if r["value"] is not None and (not isfinite(r["value"])):
            r["value"], r["action"] = None, "—"
        if r["value"] is not None:
            r["value"] = round(r["value"], r["decimals"])
    return out


def moving_averages(c: list[float]) -> list[dict]:
    out = []
    for p in MA_PERIODS:
        s, e = _sma(c, p)[-1], _ema(c, p)[-1]
        out.append({"period": p, "sma": round(s, 2) if s is not None else None, "sma_action": "—" if s is None else "Buy" if c[-1] > s else "Sell",  # noqa: E501
                    "ema": round(e, 2) if e is not None else None, "ema_action": "—" if e is None else "Buy" if c[-1] > e else "Sell"})
    return out


def pivots(o: float, h: float, lo: float, c: float) -> dict:
    rng = h - lo
    p = (h + lo + c) / 3
    classic = {"S3": lo - 2 * (h - p), "S2": p - rng, "S1": 2 * p - h, "P": p, "R1": 2 * p - lo, "R2": p + rng, "R3": h + 2 * (p - lo)}
    fib = {"S3": p - rng, "S2": p - 0.618 * rng, "S1": p - 0.382 * rng, "P": p, "R1": p + 0.382 * rng, "R2": p + 0.618 * rng, "R3": p + rng}
    cam = {"S3": c - rng * 1.1 / 4, "S2": c - rng * 1.1 / 6, "S1": c - rng * 1.1 / 12, "P": p, "R1": c + rng * 1.1 / 12, "R2": c + rng * 1.1 / 6, "R3": c + rng * 1.1 / 4}  # noqa: E501
    pw = (h + lo + 2 * c) / 4
    wood = {"S3": lo - 2 * (h - pw), "S2": pw - rng, "S1": 2 * pw - h, "P": pw, "R1": 2 * pw - lo, "R2": pw + rng, "R3": h + 2 * (pw - lo)}
    x = (h + 2 * lo + c) if c < o else (2 * h + lo + c) if c > o else (h + lo + 2 * c)
    dm = {"S3": None, "S2": None, "S1": x / 2 - h, "P": x / 4, "R1": x / 2 - lo, "R2": None, "R3": None}
    rnd = lambda d: {k: (round(v, 2) if v is not None else None) for k, v in d.items()}  # noqa: E731
    return {"basis": {"open": o, "high": h, "low": lo, "close": c}, "methods": [{"name": "Classic", **rnd(classic)}, {"name": "Fibonacci", **rnd(fib)},  # noqa: E501
                                                                                {"name": "Camarilla", **rnd(cam)}, {"name": "Woodie", **rnd(wood)}, {"name": "DeMark", **rnd(dm)}]}  # noqa: E501


def summarise(ind: list[dict], mas: list[dict]) -> dict:
    ib = sum(1 for r in ind if r["action"] == "Buy") + sum(1 for r in ind if r["action"] == "Oversold")
    isell = sum(1 for r in ind if r["action"] == "Sell") + sum(1 for r in ind if r["action"] == "Overbought")
    ineu = sum(1 for r in ind if r["action"] == "Neutral")
    mb = sum(1 for m in mas for k in ("sma_action", "ema_action") if m[k] == "Buy")
    ms = sum(1 for m in mas for k in ("sma_action", "ema_action") if m[k] == "Sell")

    def verdict(b: int, s: int) -> str:
        if b + s == 0:
            return "Neutral"
        if b >= 2 * max(s, 1) and b >= 4:
            return "Strong buy"
        if s >= 2 * max(b, 1) and s >= 4:
            return "Strong sell"
        return "Buy" if b > s else "Sell" if s > b else "Neutral"
    return {"indicators": {"buy": ib, "sell": isell, "neutral": ineu, "verdict": verdict(ib, isell)},
            "moving_averages": {"buy": mb, "sell": ms, "verdict": verdict(mb, ms)}, "overall": verdict(ib + mb, isell + ms)}


def analyse(bars: list[dict], timeframe: str = "daily") -> dict:
    """bars: dicts with open/high/low/close, oldest first."""
    if len(bars) < 15:
        return {"timeframe": timeframe, "label": TIMEFRAMES.get(timeframe, ("", timeframe))[1], "bars": len(bars), "error": "not enough bars"}  # noqa: E501
    o = [b["open"] for b in bars]
    h = [b["high"] for b in bars]
    lo = [b["low"] for b in bars]
    c = [b["close"] for b in bars]
    ind = indicators(o, h, lo, c)
    mas = moving_averages(c)
    prev = bars[-2]
    return {"timeframe": timeframe, "label": TIMEFRAMES.get(timeframe, ("", timeframe))[1], "bars": len(bars), "last": c[-1],
            "summary": summarise(ind, mas), "indicators": ind, "moving_averages": mas,
            "pivots": pivots(prev["open"], prev["high"], prev["low"], prev["close"])}
