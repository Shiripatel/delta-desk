"""Upstox Market Data Feed V3 (free). Protobuf over WebSocket; pushes option Greeks in `full` mode.

Docs: https://upstox.com/developer/api-documentation/v3/get-market-data-feed/
Limits (free): 2 connections per user; per connection ltpc 5,000 keys, option_greeks 3,000, full 2,000.
Instrument master: https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz
Install with `uv sync --extra upstox` and set UPSTOX_ACCESS_TOKEN.

Phase 1 work item: decode MarketDataFeed.proto messages into `Tick` and map instrument keys such as
"NSE_INDEX|Nifty 50", "NSE_INDEX|India VIX" and "NSE_FO|<token>". Until then this adapter refuses to start.
"""
from __future__ import annotations

from deltadesk.config import Settings


class UpstoxFeed:
    name = "upstox"

    def __init__(self, settings: Settings, **_: object) -> None:
        raise NotImplementedError("Upstox adapter is a phase-1 task; see docs/PLAN.md section 5")
