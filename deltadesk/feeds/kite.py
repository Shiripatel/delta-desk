"""Zerodha Kite Connect feed. Needs the paid Connect plan for market data (Personal plan has none).

Install with `uv sync --extra kite`. Set KITE_API_KEY and KITE_ACCESS_TOKEN (the access token is the
result of the daily request-token exchange; automate it with TOTP in a small login job).
Instrument master: https://api.kite.trade/instruments  (CSV, refreshed daily).
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import datetime

from deltadesk.config import Settings
from deltadesk.feeds.base import IST, next_weekly_expiry, option_symbol
from deltadesk.schemas import Bar, Instrument, Kind, Tick


class KiteFeed:
    name = "kite"

    def __init__(self, settings: Settings, **_: object) -> None:
        try:
            from kiteconnect import KiteConnect, KiteTicker  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("pip install kiteconnect  (uv sync --extra kite)") from e
        self.s = settings
        self.api_key = os.environ["KITE_API_KEY"]
        self.access_token = os.environ["KITE_ACCESS_TOKEN"]
        self.kite = KiteConnect(api_key=self.api_key)
        self.kite.set_access_token(self.access_token)
        self.ticker = KiteTicker(self.api_key, self.access_token)
        self.queue: asyncio.Queue[Tick] = asyncio.Queue(maxsize=50_000)
        self.loop: asyncio.AbstractEventLoop | None = None
        self._tokens: list[int] = []
        self._by_token: dict[int, Instrument] = {}

    async def connect(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.ticker.on_ticks = self._on_ticks
        self.ticker.on_connect = lambda ws, resp: ws.subscribe(self._tokens) or ws.set_mode(ws.MODE_FULL, self._tokens)
        self.ticker.connect(threaded=True)

    def _on_ticks(self, ws, ticks) -> None:  # runs on the ticker thread
        now = datetime.now(IST)
        for t in ticks:
            depth = t.get("depth") or {}
            buy, sell = depth.get("buy") or [], depth.get("sell") or []
            tick = Tick(ts=t.get("exchange_timestamp") or now, token=str(t["instrument_token"]),
                        ltp=float(t["last_price"]),
                        bid=float(buy[0]["price"]) if buy else None,
                        ask=float(sell[0]["price"]) if sell else None,
                        volume=int(t.get("volume_traded") or 0), oi=int(t.get("oi") or 0))
            if self.loop:
                self.loop.call_soon_threadsafe(self._put, tick)

    def _put(self, tick: Tick) -> None:
        if self.queue.full():
            self.queue.get_nowait()
        self.queue.put_nowait(tick)

    async def instruments(self, underlying: str) -> list[Instrument]:
        rows = await asyncio.to_thread(self.kite.instruments, "NFO")
        idx = await asyncio.to_thread(self.kite.instruments, "NSE")
        expiry = next_weekly_expiry(datetime.now(IST).date())
        out: list[Instrument] = []
        for r in idx:
            if r["tradingsymbol"] in (f"{underlying} 50" if underlying == "NIFTY" else underlying, "INDIA VIX"):
                out.append(Instrument(token=str(r["instrument_token"]), symbol=r["tradingsymbol"],
                                      underlying=r["tradingsymbol"], kind=Kind.IDX))
        for r in rows:
            if r["name"] != underlying or r["expiry"] != expiry:
                continue
            kind = {"CE": Kind.CE, "PE": Kind.PE, "FUT": Kind.FUT}.get(r["instrument_type"])
            if kind is None:
                continue
            out.append(Instrument(token=str(r["instrument_token"]),
                                  symbol=option_symbol(underlying, expiry, float(r["strike"]), kind)
                                  if kind != Kind.FUT else r["tradingsymbol"],
                                  underlying=underlying, kind=kind, strike=float(r["strike"]) or None,
                                  expiry=expiry, lot_size=int(r["lot_size"])))
        self._by_token = {int(i.token): i for i in out}
        return out

    async def subscribe(self, tokens: list[str], mode: str = "full") -> None:
        self._tokens = [int(t) for t in tokens]
        if self.ticker.is_connected():
            self.ticker.subscribe(self._tokens)
            self.ticker.set_mode(self.ticker.MODE_FULL, self._tokens)

    async def history(self, underlying: str) -> list[Bar]:
        # Requires the historical add-on; token for NIFTY 50 index is 256265 on Kite.
        raise NotImplementedError("Kite historical: kite.historical_data(token, from, to, 'minute')")

    async def ticks(self) -> AsyncIterator[Tick]:
        while True:
            yield await self.queue.get()

    async def close(self) -> None:
        self.ticker.close()
