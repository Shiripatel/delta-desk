"""Upstox Market Data Feed V3 (free): protobuf over WebSocket via the official SDK's MarketDataStreamerV3.

Limits (free): 2 connections per user; per connection full 2,000 keys, option_greeks 3,000, ltpc 5,000.
Setup: `uv sync --extra upstox`, then `uv run deltadesk login upstox` once per trading day.
The desk subscribes to the index, India VIX, the near-month future and the weekly chain around ATM
in `full` mode: about 90 keys, well inside the free limit.
"""
from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncIterator
from datetime import datetime, timedelta

from deltadesk.auth import load_token
from deltadesk.config import Settings
from deltadesk.feeds.base import IST, option_symbol
from deltadesk.markets.upstox_master import InstrumentMaster, _expiry_date
from deltadesk.schemas import Bar, Instrument, Kind, Tick

INDEX_KEY = {"NIFTY": "NSE_INDEX|Nifty 50", "BANKNIFTY": "NSE_INDEX|Nifty Bank", "FINNIFTY": "NSE_INDEX|Nifty Fin Service",
             "MIDCPNIFTY": "NSE_INDEX|NIFTY MID SELECT"}
VIX_KEY = "NSE_INDEX|India VIX"


def _f(x, default=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def parse_feed(key: str, feed: dict, now: datetime) -> Tick | None:
    """One entry of FeedResponse.feeds (MessageToDict form) into a Tick. Handles ltpc, indexFF and marketFF."""
    full = feed.get("fullFeed") or {}
    ff = full.get("marketFF") or full.get("indexFF") or {}
    ltpc = ff.get("ltpc") or feed.get("ltpc") or (feed.get("firstLevelWithGreeks") or {}).get("ltpc") or {}
    if "ltp" not in ltpc:
        return None
    ltt = ltpc.get("ltt")
    ts = datetime.fromtimestamp(int(ltt) / 1000, IST) if ltt and str(ltt).isdigit() and int(ltt) > 0 else now
    bid = ask = None
    quotes = (ff.get("marketLevel") or {}).get("bidAskQuote") or []
    if quotes:
        bid, ask = _f(quotes[0].get("bidP"), None), _f(quotes[0].get("askP"), None)
    return Tick(ts=ts, token=key, ltp=_f(ltpc.get("ltp")), bid=bid, ask=ask,
                volume=int(_f(ff.get("vtt"))), oi=int(_f(ff.get("oi"))))


class UpstoxFeed:
    name = "upstox"

    def __init__(self, settings: Settings, **_: object) -> None:
        try:
            import upstox_client  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("pip install upstox-python-sdk  (uv sync --extra upstox)") from e
        token = load_token("upstox")
        if not token:
            raise RuntimeError("No Upstox token. Run: uv run deltadesk login upstox")
        self.s = settings
        cfg = upstox_client.Configuration()
        cfg.access_token = token
        self.client = upstox_client.ApiClient(cfg)
        self._sdk = upstox_client
        self.master = InstrumentMaster()
        self.queue: asyncio.Queue[Tick] = asyncio.Queue(maxsize=100_000)
        self.loop: asyncio.AbstractEventLoop | None = None
        self.streamer = None
        self._keys: list[str] = []
        self.expiry = None
        self.last_error: str | None = None

    # ---- Feed protocol --------------------------------------------------------------------
    async def connect(self) -> None:
        self.loop = asyncio.get_running_loop()
        n = await asyncio.to_thread(self.master.load)
        if n == 0:
            raise RuntimeError("Upstox instrument master could not be loaded (offline?)")

    async def instruments(self, underlying: str) -> list[Instrument]:
        und = underlying
        idx_key = INDEX_KEY.get(und) or self.master.index_key(und)
        if not idx_key:
            raise RuntimeError(f"no index key for {und}")
        spot = await asyncio.to_thread(self._ltp, idx_key)
        today = datetime.now(IST).date()
        self.expiry = self.master.nearest_expiry(und, today)
        if self.expiry is None:
            raise RuntimeError(f"no option expiries in the master for {und}")
        fut_expiries = self.master.expiries(und, "FUT")
        fut_exp = next((e for e in fut_expiries if e >= today), None)
        out = [Instrument(token=idx_key, symbol=und, underlying=und, kind=Kind.IDX),
               Instrument(token=VIX_KEY, symbol="INDIA VIX", underlying="INDIA VIX", kind=Kind.IDX)]
        if fut_exp:
            fk = self.master.futures_key(und, fut_exp)
            if fk:
                row = self.master.by_key[fk]
                out.append(Instrument(token=fk, symbol=row.get("trading_symbol", f"{und} FUT"), underlying=und, kind=Kind.FUT,
                                      expiry=fut_exp, lot_size=int(row.get("lot_size") or self.s.lot_size)))
        step = self.s.strike_step
        atm = round(spot / step) * step
        for r in self.master.chain(und, self.expiry, atm, step, self.s.strikes_each_side):
            kind = Kind.CE if r["instrument_type"] == "CE" else Kind.PE
            k = float(r["strike_price"])
            out.append(Instrument(token=r["instrument_key"], symbol=option_symbol(und, self.expiry, k, kind), underlying=und,
                                  kind=kind, strike=k, expiry=self.expiry, lot_size=int(r.get("lot_size") or self.s.lot_size)))
        return out

    def _ltp(self, key: str) -> float:
        api = self._sdk.MarketQuoteV3Api(self.client)
        resp = api.get_ltp(instrument_key=key)
        data = resp.data or {}
        for v in data.values():
            return float(v.last_price)
        raise RuntimeError(f"no LTP for {key}")

    async def subscribe(self, tokens: list[str], mode: str = "full") -> None:
        self._keys = list(tokens)
        st = self._sdk.MarketDataStreamerV3(self.client, self._keys, mode)
        st.on("message", self._on_message)
        st.on("error", lambda e: self._set_error(repr(e)))
        st.on("close", lambda *a: self._set_error("closed"))
        st.auto_reconnect(True, 5, 20)
        self.streamer = st
        await asyncio.to_thread(st.connect)

    def _set_error(self, msg: str) -> None:
        self.last_error = msg

    def _on_message(self, msg: dict) -> None:  # runs on the SDK's socket thread
        now = datetime.now(IST)
        for key, feed in (msg.get("feeds") or {}).items():
            t = parse_feed(key, feed, now)
            if t is not None and self.loop is not None:
                self.loop.call_soon_threadsafe(self._put, t)

    def _put(self, t: Tick) -> None:
        if self.queue.full():
            self.queue.get_nowait()
        self.queue.put_nowait(t)

    async def history(self, underlying: str) -> list[Bar]:
        """Previous session's 1-minute index bars from the historical candle API."""
        key = INDEX_KEY.get(underlying) or self.master.index_key(underlying) or ""
        today = datetime.now(IST).date()
        frm = today - timedelta(days=7)
        candles = await asyncio.to_thread(self._candles, key, frm.isoformat(), (today - timedelta(days=1)).isoformat())
        bars = [Bar(ts=datetime.fromisoformat(c[0]), open=float(c[1]), high=float(c[2]), low=float(c[3]),
                    close=float(c[4]), volume=int(_f(c[5]))) for c in candles]
        bars.sort(key=lambda b: b.ts)
        if not bars:
            return []
        last_day = bars[-1].ts.date()
        return [b for b in bars if b.ts.date() == last_day]

    def _candles(self, key: str, frm: str, to: str) -> list:
        sdk = self._sdk
        if hasattr(sdk, "HistoryV3Api"):
            api = sdk.HistoryV3Api(self.client)
            resp = api.get_historical_candle_data1(key, "minutes", "1", to, frm)
        else:  # pragma: no cover - older SDK
            api = sdk.HistoryApi(self.client)
            resp = api.get_historical_candle_data1(key, "1minute", to, frm, api_version="2.0")
        return list(resp.data.candles or [])

    async def ticks(self) -> AsyncIterator[Tick]:
        while True:
            yield await self.queue.get()

    async def close(self) -> None:
        if self.streamer is not None:
            try:
                self.streamer.disconnect()
            except Exception:  # noqa: BLE001
                pass


def implied_step(spot: float) -> float:
    """Strike step heuristic when the settings do not say: 50 for NIFTY-sized, 100 for BANKNIFTY-sized."""
    return 100.0 if spot > 40_000 else 50.0 if spot > 10_000 else 25.0


_ = (math, _expiry_date)  # re-exported helpers for tests
