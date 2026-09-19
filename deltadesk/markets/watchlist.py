"""Watchlists persisted as JSON on disk (data/watchlist.json). Multi-user storage is a later phase.

Rules: up to MAX_LISTS named lists, up to MAX_SYMBOLS symbols per list. Presets (index constituents, key
indicators) fill a list named after the preset so the user's own lists are never overwritten.
"""
from __future__ import annotations

import json
from pathlib import Path

from deltadesk.markets import universe

MAX_SYMBOLS = 50
MAX_LISTS = 12
DEFAULT = {"My watchlist": ["NIFTY50", "BANKNIFTY", "INDIAVIX", "HDFCBANK", "RELIANCE", "INFY", "TCS", "ICICIBANK"]}


class WatchlistError(ValueError):
    """Raised for user-facing rule violations (list full, too many lists, unknown preset)."""


def presets() -> list[dict]:
    """Predefined lists a user can load: the main indices' constituents plus two indicator baskets."""
    out = []
    for code in ("NIFTY50", "BANKNIFTY", "FINNIFTY", "NIFTYNEXT50", "MIDCPNIFTY", "SENSEX"):
        ix = universe.INDICES[code]
        if ix.constituents:
            out.append({"code": code, "name": ix.name, "kind": "index", "count": min(MAX_SYMBOLS, len(ix.constituents)),
                        "note": f"{len(ix.constituents)} constituents" + (f", first {MAX_SYMBOLS} by weight" if len(ix.constituents) > MAX_SYMBOLS else "")})  # noqa: E501
    out.append({"code": "INDICES", "name": "Indian indices", "kind": "basket", "count": len(universe.INDICES), "note": "NIFTY 50, BANK NIFTY, FIN NIFTY, SENSEX, VIX and more"})  # noqa: E501
    keys = [g[0] for g in universe.GLOBAL] + [f[0] for f in universe.FX]
    out.append({"code": "WORLD", "name": "Commodities, FX and world", "kind": "basket", "count": min(MAX_SYMBOLS, len(keys)),
                "note": "gold, silver, crude, rupee, dollar index, US and Asian indices, crypto, yields"})
    return out


def preset_symbols(code: str) -> tuple[str, list[str]]:
    code = code.upper()
    if code in universe.INDICES and universe.INDICES[code].constituents:
        ix = universe.INDICES[code]
        cons = sorted(ix.constituents, key=lambda c: -(c.weight or 0))
        return ix.name, [c.symbol for c in cons][:MAX_SYMBOLS]
    if code == "INDICES":
        return "Indian indices", list(universe.INDICES)[:MAX_SYMBOLS]
    if code == "WORLD":
        return "Commodities, FX and world", ([g[0] for g in universe.GLOBAL] + [f[0] for f in universe.FX])[:MAX_SYMBOLS]
    raise WatchlistError(f"unknown preset {code}")


class Watchlist:
    def __init__(self, path: Path = Path("data") / "watchlist.json") -> None:
        self.path = path
        self.lists: dict[str, list[str]] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self.lists = {str(k): [str(s) for s in v][:MAX_SYMBOLS] for k, v in raw.items()}
                if self.lists:
                    return
            except (json.JSONDecodeError, AttributeError):
                pass
        self.lists = {k: list(v) for k, v in DEFAULT.items()}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.lists, indent=2), encoding="utf-8")

    @staticmethod
    def _clean(name: str) -> str:
        name = " ".join((name or "").split())[:40]
        if not name:
            raise WatchlistError("a list needs a name")
        return name

    def add(self, name: str, symbol: str) -> list[str]:
        name = self._clean(name)
        if name not in self.lists and len(self.lists) >= MAX_LISTS:
            raise WatchlistError(f"at most {MAX_LISTS} lists")
        lst = self.lists.setdefault(name, [])
        if symbol not in lst:
            if len(lst) >= MAX_SYMBOLS:
                raise WatchlistError(f"a list holds at most {MAX_SYMBOLS} symbols")
            lst.append(symbol)
            self._save()
        return lst

    def remove(self, name: str, symbol: str) -> list[str]:
        lst = self.lists.setdefault(name, [])
        if symbol in lst:
            lst.remove(symbol)
            self._save()
        return lst

    def create(self, name: str) -> None:
        name = self._clean(name)
        if name in self.lists:
            return
        if len(self.lists) >= MAX_LISTS:
            raise WatchlistError(f"at most {MAX_LISTS} lists")
        self.lists[name] = []
        self._save()

    def rename(self, name: str, new: str) -> None:
        new = self._clean(new)
        if name not in self.lists or new == name:
            return
        if new in self.lists:
            raise WatchlistError(f"a list called {new} already exists")
        self.lists = {(new if k == name else k): v for k, v in self.lists.items()}
        self._save()

    def delete(self, name: str) -> None:
        if name in self.lists and len(self.lists) > 1:
            del self.lists[name]
            self._save()

    def load_preset(self, code: str) -> str:
        """Fill (or refresh) a list named after the preset; returns the list name."""
        name, syms = preset_symbols(code)
        if name not in self.lists and len(self.lists) >= MAX_LISTS:
            raise WatchlistError(f"at most {MAX_LISTS} lists; delete one first")
        self.lists[name] = list(syms)
        self._save()
        return name

    def reorder(self, name: str, symbols: list[str]) -> list[str]:
        lst = self.lists.get(name, [])
        keep = [s for s in symbols if s in lst]
        rest = [s for s in lst if s not in keep]
        self.lists[name] = (keep + rest)[:MAX_SYMBOLS]
        self._save()
        return self.lists[name]
