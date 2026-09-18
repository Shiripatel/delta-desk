"""AI ranking table (rules model v0) over three months of daily closes.

Every number here is computed from price history with a transparent rule, so the page can show it
honestly today; Sprint 3 replaces the rule with a model calibrated on the journal.

  score      1..10  momentum (3M, 1M, 2W returns) plus trend quality (R² of the log-price fit) minus drawdown
  forecast   %      momentum-continuation estimate for the next 3 months, clipped to [-20, +25]
  risk       1..10  10 is the calmest: derived from annualised daily volatility
  win rate   %      share of 10-day windows in the last 3 months where the score's direction was right

History comes from a HistoryProvider: Yahoo (real, no account) or synthetic.
"""
from __future__ import annotations

import concurrent.futures
import json
import math
import random
import threading
import time
import urllib.parse
import urllib.request
from datetime import UTC
from typing import Protocol

from deltadesk.markets.universe import INDICES, all_symbols


class HistoryProvider(Protocol):
    name: str

    def history(self, key: str) -> list[tuple[str, float]]:
        """Ascending (iso date, close) for roughly the last three months. Empty if unavailable."""
        ...


class SyntheticHistory:
    name = "synthetic"

    def __init__(self, days: int = 66, seed: int = 5) -> None:
        self.days, self.seed = days, seed

    def history(self, key: str) -> list[tuple[str, float]]:
        rng = random.Random(f"{self.seed}:{key}")
        px, drift, vol = rng.uniform(100, 3000), rng.gauss(0.0004, 0.0012), rng.uniform(0.010, 0.025)
        out, day = [], 0
        from datetime import date, timedelta
        d = date.today() - timedelta(days=int(self.days * 1.45))
        while len(out) < self.days:
            d += timedelta(days=1)
            if d.weekday() > 4:
                continue
            px *= math.exp(drift + rng.gauss(0, vol))
            out.append((d.isoformat(), round(px, 2)))
            day += 1
        return out


class YahooHistory:
    """Daily closes from the same public chart endpoint the delayed quotes use; cached for an hour."""
    name = "yahoo"
    CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=3mo&interval=1d"

    def __init__(self, ttl: float = 3600.0, workers: int = 8, timeout: float = 12.0) -> None:
        from deltadesk.markets.quotes_yahoo import YahooQuotes
        self.map_symbol = YahooQuotes.map_symbol
        self.ttl, self.workers, self.timeout = ttl, workers, timeout
        self._cache: dict[str, tuple[float, list[tuple[str, float]]]] = {}
        self._lock = threading.Lock()

    def _fetch(self, sym: str) -> list[tuple[str, float]]:
        url = self.CHART.format(sym=urllib.parse.quote(sym, safe="^="))
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (DeltaDesk)"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.load(r)
        res = ((data.get("chart") or {}).get("result") or [None])[0]
        if not res:
            return []
        ts = res.get("timestamp") or []
        closes = ((res.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
        from datetime import datetime
        out = []
        for t, c in zip(ts, closes, strict=False):
            if c is not None:
                out.append((datetime.fromtimestamp(t, UTC).date().isoformat(), float(c)))
        return out

    def history(self, key: str) -> list[tuple[str, float]]:
        sym = self.map_symbol(key)
        if sym is None:
            return []
        now = time.time()
        with self._lock:
            c = self._cache.get(key)
            if c and now - c[0] < self.ttl:
                return c[1]
        try:
            h = self._fetch(sym)
        except Exception:  # noqa: BLE001
            h = []
        with self._lock:
            self._cache[key] = (now, h)
        return h

    def prefetch(self, keys: list[str]) -> None:
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as ex:
            list(ex.map(self.history, keys))


# ---- the rules model ------------------------------------------------------------------------
def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def features(closes: list[float]) -> dict[str, float] | None:
    n = len(closes)
    if n < 25 or closes[-1] <= 0:
        return None
    ret = lambda k: closes[-1] / closes[-1 - k] - 1 if n > k and closes[-1 - k] > 0 else 0.0  # noqa: E731
    logs = [math.log(c) for c in closes if c > 0]
    rets = [logs[i] - logs[i - 1] for i in range(1, len(logs))]
    mean = sum(rets) / len(rets)
    vol = math.sqrt(sum((r - mean) ** 2 for r in rets) / max(1, len(rets) - 1)) * math.sqrt(252)
    xs = list(range(len(logs)))
    xm, ym = sum(xs) / len(xs), sum(logs) / len(logs)
    sxx = sum((x - xm) ** 2 for x in xs)
    sxy = sum((x - xm) * (y - ym) for x, y in zip(xs, logs, strict=False))
    slope = sxy / sxx if sxx else 0.0
    ss_res = sum((y - (ym + slope * (x - xm))) ** 2 for x, y in zip(xs, logs, strict=False))
    ss_tot = sum((y - ym) ** 2 for y in logs)
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    peak, dd = closes[0], 0.0
    for c in closes:
        peak = max(peak, c)
        dd = max(dd, 1 - c / peak)
    return {"ret_3m": ret(min(n - 1, 63)), "ret_1m": ret(min(n - 1, 21)), "ret_2w": ret(min(n - 1, 10)),
            "vol": vol, "r2": r2, "max_dd": dd, "slope": slope}


def score(f: dict[str, float]) -> tuple[int, float, int]:
    """(ai score 1..10, forecast 3M in %, risk 1..10 where 10 is calmest)."""
    m = 0.5 * f["ret_3m"] + 0.3 * f["ret_1m"] + 0.2 * f["ret_2w"]
    raw = 5.0 + 25.0 * _clip(m, -0.2, 0.2) + 1.5 * (f["r2"] - 0.5) * (1 if m >= 0 else -1) - 10.0 * max(0.0, f["max_dd"] - 0.10)
    ai = int(round(_clip(raw, 1, 10)))
    forecast = round(_clip(0.6 * m * 100, -20, 25), 1)
    risk = int(round(_clip(10 - f["vol"] / 0.05, 1, 10)))
    return ai, forecast, risk


def win_rate(closes: list[float], horizon: int = 10, warmup: int = 30) -> float | None:
    hits = samples = 0
    for t in range(warmup, len(closes) - horizon):
        f = features(closes[: t + 1])
        if f is None:
            continue
        ai, _, _ = score(f)
        direction = 1 if ai >= 6 else -1 if ai <= 4 else 0
        if direction == 0 or closes[t] <= 0:
            continue
        realised = closes[t + horizon] / closes[t] - 1
        samples += 1
        hits += 1 if (realised > 0) == (direction > 0) else 0
    return round(100 * hits / samples, 1) if samples >= 5 else None


class AiRanker:
    def __init__(self, history: HistoryProvider, ttl: float = 900.0) -> None:
        self.history = history
        self.ttl = ttl
        self._cache: dict[str, tuple[float, dict]] = {}

    def _universe(self, index: str | None) -> list:
        if index and index.upper() in INDICES and index.upper() != "INDIAVIX":
            return list(INDICES[index.upper()].constituents)
        return list(all_symbols().values())

    def rank(self, index: str | None = None, limit: int = 50) -> dict:
        key = (index or "ALL").upper()
        now = time.time()
        c = self._cache.get(key)
        if c and now - c[0] < self.ttl:
            data = c[1]
        else:
            cons = self._universe(index)
            pre = getattr(self.history, "prefetch", None)
            if pre:
                pre([x.symbol for x in cons])
            rows = []
            for x in cons:
                h = self.history.history(x.symbol)
                closes = [p for _, p in h]
                f = features(closes)
                if f is None:
                    continue
                ai, fc, rk = score(f)
                step = max(1, len(closes) // 24)
                rows.append({"symbol": x.symbol, "name": x.name, "sector": x.sector, "weight": x.weight,
                             "score": ai, "forecast_3m": fc, "risk": rk, "win_rate": win_rate(closes),
                             "ret_3m": round(f["ret_3m"] * 100, 2), "ret_1m": round(f["ret_1m"] * 100, 2),
                             "vol": round(f["vol"] * 100, 1), "max_dd": round(f["max_dd"] * 100, 1),
                             "last": closes[-1], "spark": [round(p, 2) for p in closes[::step]] + [round(closes[-1], 2)],
                             "asof": h[-1][0]})
            rows.sort(key=lambda r: (-r["score"], -(r["win_rate"] or 0), -r["forecast_3m"]))
            for i, r in enumerate(rows, 1):
                r["rank"] = i
            data = {"index": key, "source": self.history.name, "computed_at": now, "count": len(rows), "entries": rows,
                    "note": "Rules model v0 on 3 months of daily closes. Win rate: share of 10-day windows in the last 3 months "
                            "where the score's direction was right. Not investment advice."}
            self._cache[key] = (now, data)
        return {**data, "entries": data["entries"][:limit]}

    def radar(self, index: str | None = None, days: int = 5) -> dict:
        """One frame per trading day (oldest first): every stock's score, risk, forecast as of that day,
        so the page can replay how the field moved over the last `days` sessions."""
        key = f"radar:{(index or 'ALL').upper()}:{days}"
        now = time.time()
        c = self._cache.get(key)
        if c and now - c[0] < self.ttl:
            return c[1]
        cons = self._universe(index)
        pre = getattr(self.history, "prefetch", None)
        if pre:
            pre([x.symbol for x in cons])
        hist = {x.symbol: [p for _, p in self.history.history(x.symbol)] for x in cons}
        dates = {x.symbol: [d for d, _ in self.history.history(x.symbol)] for x in cons}
        frames = []
        for back in range(days - 1, -1, -1):
            pts, asof = [], None
            for x in cons:
                closes = hist[x.symbol]
                if back >= len(closes):
                    continue
                cl = closes[: len(closes) - back]
                f = features(cl)
                if f is None:
                    continue
                ai, fc, rk = score(f)
                asof = asof or dates[x.symbol][len(cl) - 1]
                ret_1d = round((cl[-1] / cl[-2] - 1) * 100, 2) if len(cl) > 1 and cl[-2] > 0 else 0.0
                pts.append({"symbol": x.symbol, "name": x.name, "sector": x.sector, "weight": x.weight, "score": ai,
                            "forecast_3m": fc, "risk": rk, "ret_1d": ret_1d, "ret_1m": round(f["ret_1m"] * 100, 2),
                            "last": round(cl[-1], 2)})
            frames.append({"asof": asof, "points": pts})
        sectors = sorted({x.sector for x in cons})
        out = {"index": (index or "ALL").upper(), "source": self.history.name, "computed_at": now, "days": days,
               "sectors": sectors, "frames": frames,
               "note": "Score 10 at the centre, 1 at the rim; spokes are sectors; dot size is index weight. "
                       "Rules model v0 on daily closes. Not investment advice."}
        self._cache[key] = (now, out)
        return out
