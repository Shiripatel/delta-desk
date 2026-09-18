"""Minimal in-process topic bus. Swap for Redis Streams when the desk spans processes.

Subscribe to "*" to receive every message as a (topic, msg) tuple.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any


class Bus:
    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self.latest: dict[str, Any] = {}
        self.history: dict[str, list[Any]] = defaultdict(list)
        self.history_limit = 500

    def subscribe(self, topic: str, maxsize: int = 1000) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subs[topic].append(q)
        return q

    def unsubscribe(self, topic: str, q: asyncio.Queue) -> None:
        if q in self._subs[topic]:
            self._subs[topic].remove(q)

    def publish(self, topic: str, msg: Any) -> None:
        self.latest[topic] = msg
        h = self.history[topic]
        h.append(msg)
        if len(h) > self.history_limit:
            del h[: len(h) - self.history_limit]
        for q in self._subs[topic]:
            self._offer(q, msg)
        for q in self._subs["*"]:
            self._offer(q, (topic, msg))

    @staticmethod
    def _offer(q: asyncio.Queue, item: Any) -> None:
        if q.full():
            q.get_nowait()          # drop oldest, keep the stream fresh
        q.put_nowait(item)
