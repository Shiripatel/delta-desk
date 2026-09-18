"""Desk assistant v0: answers questions about a stock or a headline from the desk's own data.

Deterministic and transparent: it looks up the quote, the council verdict at the horizon the question
implies, the agent readings behind it, and the latest tagged headlines with their impact calls, then writes
a short answer that cites them. An LLM can replace `compose()` later; the inputs stay the same.
"""
from __future__ import annotations

import re

from deltadesk.markets.council import HORIZONS
from deltadesk.markets.news import ALIASES
from deltadesk.markets.universe import all_symbols

HZ_WORDS = [("15m", ["15 min", "15m", "scalp"]), ("1h", ["hour", "intraday", "today"]), ("1d", ["day", "daily", "swing"]),
            ("1w", ["week"]), ("1mo", ["month"]), ("3mo", ["quarter", "3 month"]), ("1y", ["year", "long term", "long-term", "invest"]),
            ("3y", ["3 year", "three year"]), ("10y", ["decade", "10 year"])]


def find_symbol(text: str) -> str | None:
    t = " " + text.lower() + " "
    syms = all_symbols()
    for s in syms:
        if re.search(r"(?<![a-z0-9])" + re.escape(s.lower()) + r"(?![a-z0-9])", t):
            return s
    for s, c in syms.items():
        names = [c.name.lower()] + ALIASES.get(s, [])
        if any(re.search(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])", t) for n in names if len(n) >= 3):
            return s
    return None


def find_horizon(text: str, default: str = "1d") -> str:
    t = text.lower()
    for h, words in HZ_WORDS:
        if any(w in t for w in words):
            return h
    return default


class DeskAssistant:
    name = "desk assistant v0 (rules, cites the desk's own numbers)"

    def __init__(self, markets) -> None:
        self.m = markets

    def answer(self, question: str, symbol: str | None = None, news_id: str | None = None) -> dict:
        q = (question or "").strip()
        item = self.m.news.item(news_id) if news_id else None
        sym = (symbol or "").upper() or find_symbol(q) or (item["symbols"][0] if item and item["symbols"] else None)
        horizon = find_horizon(q)
        sources: list[dict] = []
        parts: list[str] = []
        if item:
            parts.append(f"Headline ({item['source']}): {item['title']}. Impact call: {item['impact']} "
                         f"({int(item['confidence'] * 100)} % · {item['reason']}).")
            sources.append({"kind": "news", "id": item["id"], "title": item["title"], "link": item["link"]})
        if not sym:
            ind = {i["key"]: i for i in self.m.indicators()}
            n = ind.get("NIFTY50", {}).get("quote")
            tr = self.m.trending().get("entries", [])[:5]
            parts.append("I could not find a stock in the question. " + (f"NIFTY 50 is at {n['ltp']:,.2f} ({n['change_pct']:+.2f} %). " if n else "")  # noqa: E501
                         + ("Trending in the news: " + ", ".join(t["term"] for t in tr) + "." if tr else ""))
            return {"answer": " ".join(parts), "symbol": None, "horizon": horizon, "sources": sources, "assistant": self.name}
        meta = all_symbols().get(sym)
        name = meta.name if meta else sym
        q_ = self.m.quotes.quotes([sym]).get(sym)
        if q_:
            parts.append(f"{name} ({sym}) last {q_.ltp:,.2f}, {q_.change_pct:+.2f} % on the day, range {q_.low:,.2f} to {q_.high:,.2f}.")
            sources.append({"kind": "quote", "symbol": sym, "ltp": q_.ltp})
        c = self.m.council_run(sym, horizon)
        v = c["verdict"]
        avail = [a for a in c["agents"] if a["available"]]
        strongest = sorted(avail, key=lambda a: -abs(a["signal"]) * a["horizon_weight"])[:3]
        parts.append(f"At the {HORIZONS[horizon][3]} horizon the council says {v['stance'].upper()} (score {v['score']:+.2f}, "
                     f"confidence {int(v['confidence'] * 100)} %, coverage {int(v['coverage'] * 100)} %). "
                     + " ".join(f"{a['name'].capitalize()} votes {a['signal']:+.2f}: {a['reading']}." for a in strongest))
        sources.append({"kind": "council", "symbol": sym, "horizon": horizon, "stance": v["stance"], "score": v["score"]})
        missing = [a["name"] for a in c["agents"] if not a["available"]]
        if missing:
            parts.append("No data for: " + ", ".join(missing) + ".")
        news = self.m.news.for_symbol(sym, limit=3)
        if news:
            parts.append("Latest news: " + " · ".join(f"{h.title} [{h.impact}]" for h in news) + ".")
            sources += [{"kind": "news", "id": h.id, "title": h.title, "link": h.link} for h in news]
        else:
            parts.append("No headline in the current feeds mentions this stock.")
        parts.append("Rules model v0, not advice.")
        return {"answer": " ".join(parts), "symbol": sym, "horizon": horizon, "sources": sources, "assistant": self.name}
