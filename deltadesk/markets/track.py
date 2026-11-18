"""Track record of the AI score (rules model v0): how each zone fared, measured on history instead of promised.

For every stock in the universe and every bar t that has a full window of history before it, the score is
computed exactly as the live ranking computes it (`features` and `score` over the last `window` closes up to
and including t), the zone is noted (buy 7–10, hold 4–6, sell 1–3) and the forward return over each horizon
is recorded. Per zone: how many windows, what share closed higher, the mean and median forward move; next to
the base rate of every window in the same period, so the reader can see whether the zone added anything.

Walk-forward, no look-ahead. It is still a description of a rule on the past, not a forecast and not a backtest
of a strategy: no costs, no sizing, and the windows overlap. Long-term mode is scored on weekly closes without
the fundamentals blend, because today's fundamentals would leak into past scores.
"""
from __future__ import annotations

import statistics
import time

from deltadesk.markets.ai_rank import HistoryProvider, features, score
from deltadesk.markets.universe import INDICES, all_symbols

ZONES = (("buy", "7–10 buy zone", 7, 10), ("hold", "4–6 hold · no trade", 4, 6), ("sell", "1–3 sell zone", 1, 3))
SPEC = {"short": {"window": 63, "horizons": (5, 20), "unit": "sessions", "label": "short term · 3-month momentum on daily closes"},
        "long": {"window": 104, "horizons": (4, 13), "unit": "weeks", "label": "long term · 2-year momentum on weekly closes (price only)"}}


def zone_of(ai: int) -> str:
    for name, _label, lo, hi in ZONES:
        if lo <= ai <= hi:
            return name
    return "hold"


def windows(closes: list[float], window: int, horizons: tuple[int, ...]) -> list[tuple[int, str, dict[int, float]]]:
    """(bar index, zone, {horizon: forward return}) for every bar with a full window behind it and every horizon ahead."""
    out = []
    far = max(horizons)
    for t in range(window - 1, len(closes) - far):
        cl = closes[t - window + 1: t + 1]
        f = features(cl)
        if f is None or closes[t] <= 0:
            continue
        ai, _, _ = score(f)
        out.append((t, zone_of(ai), {h: closes[t + h] / closes[t] - 1 for h in horizons}))
    return out


def _stats(rets: list[float]) -> dict:
    if not rets:
        return {"n": 0, "up": None, "mean": None, "median": None}
    return {"n": len(rets), "up": round(100 * sum(1 for r in rets if r > 0) / len(rets), 1),
            "mean": round(100 * statistics.fmean(rets), 2), "median": round(100 * statistics.median(rets), 2)}


def summarise(samples: list[tuple[int, str, dict[int, float]]], horizons: tuple[int, ...]) -> dict:
    total = len(samples)
    zones = []
    for name, label, lo, hi in ZONES:
        mine = [s for s in samples if s[1] == name]
        zones.append({"zone": name, "label": label, "lo": lo, "hi": hi, "n": len(mine),
                      "share": round(100 * len(mine) / total, 1) if total else 0.0,
                      "h": {str(h): _stats([s[2][h] for s in mine]) for h in horizons}})
    base = {str(h): _stats([s[2][h] for s in samples]) for h in horizons}
    hit = {}
    for h in horizons:
        calls = [(s[1], s[2][h]) for s in samples if s[1] in ("buy", "sell")]
        right = sum(1 for z, r in calls if (r > 0) == (z == "buy"))
        hit[str(h)] = {"n": len(calls), "rate": round(100 * right / len(calls), 1) if calls else None}
    return {"windows": total, "zones": zones, "base": base, "hit": hit}


def headline(rep: dict) -> str:
    h = str(rep["horizons"][-1])
    unit = rep["unit"]
    by = {z["zone"]: z for z in rep["zones"]}
    base = rep["base"][h]
    if not rep["windows"] or base["up"] is None:
        return "Not enough history yet to score the rule on the past."
    parts = []
    for name in ("buy", "sell"):
        z = by[name]["h"][h]
        if z["n"]:
            zone = by[name]["label"].split(" ", 1)[1].capitalize()
            parts.append(f"{zone}: {z['up']:.0f} % of {z['n']:,} windows were higher {h} {unit} later")
    return ". ".join(parts) + f". Base rate for every window: {base['up']:.0f} %." if parts else "No buy or sell calls in the period."


class TrackRecord:
    def __init__(self, history: HistoryProvider, history_long: HistoryProvider | None = None, ttl: float = 6 * 3600.0) -> None:
        self.history = history
        self.history_long = history_long or history
        self.ttl = ttl
        self._cache: dict[str, tuple[float, dict]] = {}

    def _universe(self, index: str | None) -> list:
        if index and index.upper() in INDICES and index.upper() != "INDIAVIX":
            return list(INDICES[index.upper()].constituents)
        return list(all_symbols().values())

    def report(self, index: str | None = None, mode: str = "short") -> dict:
        mode = mode if mode in SPEC else "short"
        spec = SPEC[mode]
        prov = self.history_long if mode == "long" else self.history
        key = f"{(index or 'ALL').upper()}:{mode}"
        now = time.time()
        c = self._cache.get(key)
        if c and now - c[0] < self.ttl:
            return c[1]
        cons = self._universe(index)
        pre = getattr(prov, "prefetch", None)
        if pre:
            pre([x.symbol for x in cons])
        samples, stocks, first, last = [], 0, None, None
        for x in cons:
            h = prov.history(x.symbol)
            closes = [p for _, p in h]
            w = windows(closes, spec["window"], spec["horizons"])
            if not w:
                continue
            stocks += 1
            samples.extend(w)
            d0, d1 = h[w[0][0]][0], h[w[-1][0]][0]
            first = d0 if first is None or d0 < first else first
            last = d1 if last is None or d1 > last else last
        rep = {"index": (index or "ALL").upper(), "mode": mode, "mode_label": spec["label"], "unit": spec["unit"],
               "horizons": list(spec["horizons"]), "window": spec["window"], "source": prov.name, "computed_at": now,
               "stocks": stocks, "from": first, "to": last, **summarise(samples, spec["horizons"])}
        rep["headline"] = headline(rep)
        rep["note"] = ("Rules model v0 scored on every past bar the way it is scored today, then compared with what the price did next. "
                       "Walk-forward, no look-ahead; windows overlap, no costs or sizing. A description of the rule on the past, "
                       "not a forecast. Not investment advice.")
        self._cache[key] = (now, rep)
        return rep
