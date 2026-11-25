"""Desk assistant v0: answers questions about a stock or a headline from the desk's own data.

Deterministic and transparent: it looks up the quote, the council verdict at the horizon the question
implies, the agent readings behind it, and the latest tagged headlines with their impact calls, then writes
a short answer that cites them. An LLM can replace `compose()` later; the inputs stay the same.
"""
from __future__ import annotations

import re

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
