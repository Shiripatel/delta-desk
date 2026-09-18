"""Watchlists persisted as JSON on disk (data/watchlist.json). Multi-user storage is a later phase."""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT = {"Core": ["NIFTY50", "BANKNIFTY", "INDIAVIX", "HDFCBANK", "RELIANCE", "INFY", "TCS", "ICICIBANK"]}


class Watchlist:
    def __init__(self, path: Path = Path("data") / "watchlist.json") -> None:
        self.path = path
        self.lists: dict[str, list[str]] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self.lists = json.loads(self.path.read_text(encoding="utf-8"))
                return
            except json.JSONDecodeError:
                pass
        self.lists = {k: list(v) for k, v in DEFAULT.items()}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.lists, indent=2), encoding="utf-8")

    def add(self, name: str, symbol: str) -> list[str]:
        lst = self.lists.setdefault(name, [])
        if symbol not in lst:
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
        self.lists.setdefault(name, [])
        self._save()

    def delete(self, name: str) -> None:
        if name in self.lists and len(self.lists) > 1:
            del self.lists[name]
            self._save()
