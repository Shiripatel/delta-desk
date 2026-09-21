"""The agent council: several narrow analysis agents read one stock at one horizon and feed a verdict.

Horizons run from 15 minutes to 10 years. Short horizons weight the technical agents, long horizons
the fundamental ones. Every agent returns a signal in [-1, +1], a confidence in [0, 1], a one-line
reading and the evidence behind it, so the page can draw the flow and the user can audit each vote.

Bars come from a BarsProvider (Yahoo chart endpoint with the right range/interval, or synthetic).
Fundamentals come from data/fundamentals/<SYMBOL>.json when present (schema in FUND_FIELDS); until a
data source is wired, a few example files are built in and flagged `example`.
"""
from __future__ import annotations

import json
import math
import random
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from deltadesk.markets.universe import all_symbols

# horizon -> (yahoo range, yahoo interval, technical weight, label)
HORIZONS: dict[str, tuple[str, str, float, str]] = {
    "15m": ("5d", "15m", 0.95, "15 minutes"),
    "1h": ("1mo", "1h", 0.92, "1 hour"),
    "1d": ("6mo", "1d", 0.85, "1 day"),
    "1w": ("1y", "1d", 0.75, "1 week"),
    "1mo": ("2y", "1wk", 0.60, "1 month"),
    "3mo": ("5y", "1wk", 0.50, "3 months"),
    "1y": ("10y", "1mo", 0.35, "1 year"),
    "3y": ("max", "1mo", 0.25, "3 years"),
    "10y": ("max", "1mo", 0.15, "10 years"),
}
FUND_FIELDS = {"pe": "price to earnings", "pb": "price to book", "roe": "return on equity %", "debt_equity": "debt to equity",
               "revenue_growth": "revenue growth % (3y CAGR)", "eps_growth": "EPS growth % (3y CAGR)", "dividend_yield": "dividend yield %",
               "promoter_holding": "promoter holding %", "fii_holding": "FII holding %"}
FUND_EXAMPLES = {
    "HDFCBANK": {"pe": 19.5, "pb": 2.8, "roe": 16.5, "debt_equity": 0.0, "revenue_growth": 18.0, "eps_growth": 15.0, "dividend_yield": 1.1,
                 "promoter_holding": 0.0, "fii_holding": 48.0},
    "RELIANCE": {"pe": 24.0, "pb": 2.1, "roe": 9.5, "debt_equity": 0.4, "revenue_growth": 12.0, "eps_growth": 8.0, "dividend_yield": 0.4,
                 "promoter_holding": 50.3, "fii_holding": 21.0},
    "TCS": {"pe": 27.0, "pb": 13.0, "roe": 50.0, "debt_equity": 0.0, "revenue_growth": 9.0, "eps_growth": 10.0, "dividend_yield": 1.6,
            "promoter_holding": 71.8, "fii_holding": 12.5},
}


@dataclass
class Bar:
    ts: float
    open: float
    high: float
    low: float
    close: float
    volume: float


class BarsProvider(Protocol):
    name: str

    def bars(self, symbol: str, horizon: str) -> list[Bar]: ...


CHART_RANGES: dict[str, tuple[str, str]] = {"1d": ("1d", "5m"), "5d": ("5d", "15m"), "1m": ("1mo", "1h"), "3m": ("3mo", "1d"),
                                            "6m": ("6mo", "1d"), "1y": ("1y", "1d"), "5y": ("5y", "1wk"), "all": ("max", "1mo")}
STEP = {"5m": 300, "15m": 900, "1h": 3600, "1d": 86400, "1wk": 7 * 86400, "1mo": 30 * 86400}


class SyntheticBars:
    name = "synthetic"

    def bars_for(self, symbol: str, rng_: str, itv: str) -> list[Bar]:
        return self._gen(symbol, f"{rng_}:{itv}", STEP.get(itv, 86400), {"1d": 75, "5d": 125, "1mo": 150, "3mo": 65, "6mo": 125, "1y": 250}.get(rng_, 160))  # noqa: E501

    def bars(self, symbol: str, horizon: str) -> list[Bar]:
        return self._gen(symbol, horizon, {"15m": 900, "1h": 3600, "1d": 86400, "1w": 86400, "1mo": 7 * 86400, "3mo": 7 * 86400}.get(horizon, 30 * 86400), 160)  # noqa: E501

    def _gen(self, symbol: str, seed: str, step: int, n: int) -> list[Bar]:
        rng = random.Random(f"{symbol}:{seed}")
        px = rng.uniform(100, 3000)
        drift, vol = rng.gauss(0.0006, 0.002), rng.uniform(0.008, 0.02) * (0.25 if step < 3600 else 1.0)
        t0 = time.time() - n * step
        out = []
        for i in range(n):
            o = px
            px *= math.exp(drift + rng.gauss(0, vol))
            h, l = max(o, px) * (1 + abs(rng.gauss(0, vol / 2))), min(o, px) * (1 - abs(rng.gauss(0, vol / 2)))
            out.append(Bar(t0 + i * step, o, h, l, px, abs(rng.gauss(1e6, 4e5))))
        return out


class YahooBars:
    name = "yahoo"
    CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval={itv}"

    def __init__(self, timeout: float = 12.0) -> None:
        from deltadesk.markets.quotes_yahoo import YahooQuotes
        self.map_symbol = YahooQuotes.map_symbol
        self.timeout = timeout
        self._cache: dict[tuple[str, str], tuple[float, list[Bar]]] = {}
        self._lock = threading.Lock()

    def bars(self, symbol: str, horizon: str) -> list[Bar]:
        rng_, itv, _, _ = HORIZONS[horizon]
        return self.bars_for(symbol, rng_, itv)

    def bars_for(self, symbol: str, rng_: str, itv: str) -> list[Bar]:
        ttl = 120 if itv in ("5m", "15m", "1h") else 3600
        key = (symbol, f"{rng_}:{itv}")
        now = time.time()
        with self._lock:
            c = self._cache.get(key)
            if c and now - c[0] < ttl:
                return c[1]
        sym = self.map_symbol(symbol)
        out: list[Bar] = []
        if sym:
            try:
                url = self.CHART.format(sym=urllib.parse.quote(sym, safe="^="), rng=rng_, itv=itv)
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (DeltaDesk)"})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    data = json.load(r)
                res = ((data.get("chart") or {}).get("result") or [None])[0] or {}
                q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
                for t, o, h, l, c_, v in zip(res.get("timestamp") or [], q.get("open") or [], q.get("high") or [],
                                             q.get("low") or [], q.get("close") or [], q.get("volume") or [], strict=False):
                    if c_ is not None and o is not None:
                        out.append(Bar(float(t), float(o), float(h or c_), float(l or c_), float(c_), float(v or 0)))
            except Exception:  # noqa: BLE001 - offline or symbol unknown: empty bars
                out = []
        with self._lock:
            self._cache[key] = (now, out)
        return out


# ---- indicators ---------------------------------------------------------------------------------
def _ema(xs: list[float], n: int) -> list[float]:
    k, out = 2 / (n + 1), []
    for i, x in enumerate(xs):
        out.append(x if i == 0 else x * k + out[-1] * (1 - k))
    return out


def _sma(xs: list[float], n: int) -> float:
    return sum(xs[-n:]) / min(n, len(xs))


def _rsi(closes: list[float], n: int = 14) -> float:
    if len(closes) < n + 1:
        return 50.0
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    ag, al = gains / n, losses / n
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# ---- technical agents ----------------------------------------------------------------------------
def agent_trend(b: list[Bar]) -> dict:
    c = [x.close for x in b]
    if len(c) < 30:
        return _na("trend", "technical", "not enough bars")
    f, s = _sma(c, 20), _sma(c, 50) if len(c) >= 50 else _sma(c, len(c))
    px = c[-1]
    sig = _clip((f - s) / s * 25) * 0.6 + _clip((px - f) / f * 25) * 0.4
    conf = min(1.0, abs(f - s) / s * 40 + 0.3)
    return _agent("trend", "technical", sig, conf, f"SMA20 {'above' if f > s else 'below'} SMA50, price {'above' if px > f else 'below'} SMA20",  # noqa: E501
                  {"sma20": round(f, 2), "sma50": round(s, 2), "close": round(px, 2)}, weight=1.2)


def agent_momentum(b: list[Bar]) -> dict:
    c = [x.close for x in b]
    if len(c) < 16:
        return _na("momentum", "technical", "not enough bars")
    rsi = _rsi(c)
    roc = c[-1] / c[-11] - 1 if len(c) > 11 else 0.0
    sig = _clip((rsi - 50) / 25) * 0.6 + _clip(roc * 10) * 0.4
    if rsi > 75:
        sig -= 0.3  # stretched
    if rsi < 25:
        sig += 0.3
    return _agent("momentum", "technical", _clip(sig), min(1.0, abs(rsi - 50) / 30 + 0.3),
                  f"RSI14 {rsi:.0f} · 10-bar change {roc * 100:+.1f} %", {"rsi14": round(rsi, 1), "roc10_pct": round(roc * 100, 2)})


def agent_macd(b: list[Bar]) -> dict:
    c = [x.close for x in b]
    if len(c) < 35:
        return _na("macd", "technical", "not enough bars")
    e12, e26 = _ema(c, 12), _ema(c, 26)
    macd = [a - b_ for a, b_ in zip(e12, e26, strict=False)]
    sigl = _ema(macd, 9)
    hist = macd[-1] - sigl[-1]
    rising = hist > (macd[-2] - sigl[-2])
    scale = abs(c[-1]) * 0.01 or 1
    sig = _clip(hist / scale) * 0.7 + (0.3 if rising else -0.3)
    return _agent("macd", "technical", _clip(sig), min(1.0, abs(hist / scale) + 0.3),
                  f"histogram {hist:+.2f} and {'rising' if rising else 'falling'}, MACD {'above' if macd[-1] > sigl[-1] else 'below'} signal",  # noqa: E501
                  {"macd": round(macd[-1], 3), "signal": round(sigl[-1], 3), "hist": round(hist, 3)})


def agent_volume(b: list[Bar]) -> dict:
    v = [x.volume for x in b]
    c = [x.close for x in b]
    if len(v) < 25 or sum(v[-20:]) == 0:
        return _na("volume", "technical", "no volume data")
    recent, base = sum(v[-5:]) / 5, sum(v[-25:-5]) / 20
    ratio = recent / base if base else 1.0
    direction = 1 if c[-1] >= c[-6] else -1
    sig = _clip((ratio - 1) * 1.5) * direction
    return _agent("volume", "technical", sig, min(1.0, abs(ratio - 1) + 0.3),
                  f"last 5 bars {ratio:.2f}× the 20-bar average, price {'up' if direction > 0 else 'down'} over them",
                  {"vol_ratio": round(ratio, 2)}, weight=0.8)


def agent_volatility(b: list[Bar]) -> dict:
    if len(b) < 20:
        return _na("volatility", "technical", "not enough bars")
    trs = [max(x.high - x.low, abs(x.high - p.close), abs(x.low - p.close)) for p, x in zip(b[:-1], b[1:], strict=False)]
    atr14, atr_long = sum(trs[-14:]) / 14, sum(trs[-60:]) / min(60, len(trs))
    ratio = atr14 / atr_long if atr_long else 1.0
    # expanding volatility argues for smaller size; the vote is mildly against whichever way price leans
    lean = 1 if b[-1].close >= b[-14].close else -1
    sig = _clip((1 - ratio) * 0.8) * lean
    return _agent("volatility", "technical", sig, min(1.0, abs(ratio - 1) + 0.25),
                  f"ATR14 is {ratio:.2f}× its 60-bar norm ({'expanding' if ratio > 1.1 else 'contracting' if ratio < 0.9 else 'normal'})",
                  {"atr14": round(atr14, 2), "atr_ratio": round(ratio, 2)}, weight=0.7)


def agent_levels(b: list[Bar]) -> dict:
    if len(b) < 25:
        return _na("levels", "technical", "not enough bars")
    hi = max(x.high for x in b[-21:-1])
    lo = min(x.low for x in b[-21:-1])
    px = b[-1].close
    pos = (px - lo) / (hi - lo) if hi > lo else 0.5
    if px > hi:
        sig, txt = 0.8, "breakout above the 20-bar high"
    elif px < lo:
        sig, txt = -0.8, "breakdown below the 20-bar low"
    else:
        sig, txt = _clip((pos - 0.5) * 1.2), f"{pos * 100:.0f} % of the way up the 20-bar range"
    return _agent("levels", "technical", sig, 0.6 + 0.4 * abs(pos - 0.5) * 2, txt,
                  {"range_high": round(hi, 2), "range_low": round(lo, 2), "range_pos": round(pos, 2)}, weight=0.9)


# ---- fundamental agents ---------------------------------------------------------------------------
def load_fundamentals(symbol: str) -> tuple[dict | None, str]:
    p = Path("data") / "fundamentals" / f"{symbol}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8")), str(p)
        except json.JSONDecodeError:
            return None, f"{p} (invalid JSON)"
    if symbol in FUND_EXAMPLES:
        return dict(FUND_EXAMPLES[symbol], example=True), "example data"
    return None, "no data (add data/fundamentals/<SYMBOL>.json)"


def agent_valuation(f: dict | None) -> dict:
    if not f or f.get("pe") is None:
        return _na("valuation", "fundamental", "no P/E data")
    pe, pb = float(f["pe"]), float(f.get("pb") or 0)
    sig = _clip((24 - pe) / 16)                      # cheap vs the index's typical multiple
    return _agent("valuation", "fundamental", sig, 0.7, f"P/E {pe:.1f}" + (f" · P/B {pb:.1f}" if pb else ""),
                  {"pe": pe, "pb": pb}, weight=1.1)


def agent_growth(f: dict | None) -> dict:
    if not f or f.get("eps_growth") is None:
        return _na("growth", "fundamental", "no growth data")
    eps, rev = float(f["eps_growth"]), float(f.get("revenue_growth") or 0)
    sig = _clip((eps - 8) / 15) * 0.6 + _clip((rev - 8) / 15) * 0.4
    return _agent("growth", "fundamental", sig, 0.7, f"EPS growth {eps:+.0f} % · revenue {rev:+.0f} % (3y CAGR)",
                  {"eps_growth": eps, "revenue_growth": rev}, weight=1.2)


def agent_quality(f: dict | None) -> dict:
    if not f or f.get("roe") is None:
        return _na("quality", "fundamental", "no ROE data")
    roe, de = float(f["roe"]), float(f.get("debt_equity") or 0)
    sig = _clip((roe - 12) / 15) * 0.7 - _clip(de / 2) * 0.3
    return _agent("quality", "fundamental", sig, 0.7, f"ROE {roe:.0f} % · debt/equity {de:.1f}", {"roe": roe, "debt_equity": de})


def agent_ownership(f: dict | None) -> dict:
    if not f or f.get("dividend_yield") is None:
        return _na("ownership", "fundamental", "no holding data")
    dy, prom, fii = float(f["dividend_yield"]), float(f.get("promoter_holding") or 0), float(f.get("fii_holding") or 0)
    sig = _clip((dy - 1) / 2) * 0.4 + _clip((prom - 40) / 40) * 0.3 + _clip((fii - 15) / 20) * 0.3
    return _agent("ownership", "fundamental", sig, 0.5, f"dividend {dy:.1f} % · promoters {prom:.0f} % · FII {fii:.0f} %",
                  {"dividend_yield": dy, "promoter_holding": prom, "fii_holding": fii}, weight=0.8)


# ---- helpers + council ------------------------------------------------------------------------------
def _agent(name: str, group: str, signal: float, conf: float, reading: str, evidence: dict, weight: float = 1.0) -> dict:
    return {"name": name, "group": group, "signal": round(_clip(signal), 3), "confidence": round(_clip(conf, 0, 1), 2),
            "reading": reading, "evidence": evidence, "weight": weight, "available": True}


def _na(name: str, group: str, why: str) -> dict:
    return {"name": name, "group": group, "signal": 0.0, "confidence": 0.0, "reading": why, "evidence": {}, "weight": 1.0, "available": False}  # noqa: E501


TECH = [agent_trend, agent_momentum, agent_macd, agent_volume, agent_volatility, agent_levels]
FUND = [agent_valuation, agent_growth, agent_quality, agent_ownership]


class Council:
    def __init__(self, bars: BarsProvider, fundamentals=None) -> None:
        self.bars = bars
        self.fundamentals = fundamentals      # callable(symbol) -> (dict | None, source); None = files / examples

    def run(self, symbol: str, horizon: str = "1d") -> dict:
        symbol = symbol.upper()
        if horizon not in HORIZONS:
            horizon = "1d"
        rng_, itv, w_tech, label = HORIZONS[horizon]
        bars = self.bars.bars(symbol, horizon)
        f, f_src = (None, "")
        if self.fundamentals is not None:
            try:
                f, f_src = self.fundamentals(symbol)
            except Exception as exc:  # noqa: BLE001 - a failing provider must not break the council
                f, f_src = None, f"fundamentals unavailable ({exc})"
        if f is None:
            f, f_src2 = load_fundamentals(symbol)
            f_src = f_src2 if f is not None or not f_src else f_src
        agents = [a(bars) for a in TECH] + [a(f) for a in FUND]
        w_fund = 1 - w_tech
        for a in agents:
            base = w_tech if a["group"] == "technical" else w_fund
            grp = [x for x in agents if x["group"] == a["group"] and x["available"]]
            tot = sum(x["weight"] for x in grp) or 1.0
            a["horizon_weight"] = round(base * a["weight"] / tot, 4) if a["available"] else 0.0
        num = sum(a["horizon_weight"] * a["signal"] * a["confidence"] for a in agents)
        den = sum(a["horizon_weight"] * a["confidence"] for a in agents) or 1.0
        score = _clip(num / den)
        avail = sum(a["horizon_weight"] for a in agents)
        stance = "buy" if score > 0.25 else "sell" if score < -0.25 else "hold"
        c = [b.close for b in bars]
        summary = {"n_bars": len(bars), "interval": itv, "range": rng_, "last": round(c[-1], 2) if c else None,
                   "change_pct": round((c[-1] / c[0] - 1) * 100, 2) if len(c) > 1 and c[0] else None,
                   "spark": [round(x, 2) for x in c[:: max(1, len(c) // 60)]] + ([round(c[-1], 2)] if c else []),
                   "first_ts": bars[0].ts if bars else None, "last_ts": bars[-1].ts if bars else None}
        meta = all_symbols().get(symbol)
        return {"symbol": symbol, "name": meta.name if meta else symbol, "sector": meta.sector if meta else "",
                "horizon": horizon, "horizon_label": label, "weights": {"technical": w_tech, "fundamental": round(w_fund, 2)},
                "agents": agents, "verdict": {"score": round(score, 3), "stance": stance, "coverage": round(avail, 2),
                                              "confidence": round(min(1.0, den / max(avail, 1e-9)), 2) if avail else 0.0},
                "bars": summary, "sources": {"bars": self.bars.name, "fundamentals": f_src},
                "note": "Each agent votes between -1 and +1 with a confidence; the verdict is the horizon-weighted vote. "
                        "Short horizons lean on technical agents, long horizons on fundamentals. Rules model v0, not advice."}


def chart_bars(provider: BarsProvider, symbol: str, range_key: str = "3m") -> dict:
    """OHLCV for the chart page. Intraday ranges carry epoch seconds; daily and coarser carry dates."""
    rng_, itv = CHART_RANGES.get(range_key, CHART_RANGES["3m"])
    bars = provider.bars_for(symbol, rng_, itv) if hasattr(provider, "bars_for") else []
    meta = all_symbols().get(symbol.upper())
    from deltadesk.markets.universe import GLOBAL_BY_KEY, INDICES
    name = meta.name if meta else INDICES[symbol].name if symbol in INDICES else GLOBAL_BY_KEY[symbol][1] if symbol in GLOBAL_BY_KEY else symbol  # noqa: E501
    return {"symbol": symbol.upper(), "name": name, "range": range_key, "interval": itv, "intraday": itv in ("5m", "15m", "1h"),
            "source": provider.name, "delayed": provider.name == "yahoo",
            "bars": [{"ts": b.ts, "open": round(b.open, 2), "high": round(b.high, 2), "low": round(b.low, 2), "close": round(b.close, 2),
                      "volume": int(b.volume)} for b in bars]}
