"""DhanHQ live market feed (Data APIs subscription, ₹499 + GST per month at time of writing).

Docs: https://dhanhq.co/docs/v2/live-market-feed/
Limits: 5 WebSocket connections per user, 5,000 instruments each; binary responses, per-second snapshots.
Install with `uv sync --extra dhan`, set DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN.

Phase 1 work item: wrap `dhanhq.marketfeed.DhanFeed` and map its packets to `Tick`.
"""
from __future__ import annotations

from deltadesk.config import Settings


class DhanFeed:
    name = "dhan"

    def __init__(self, settings: Settings, **_: object) -> None:
        raise NotImplementedError("Dhan adapter is a phase-1 task; see docs/PLAN.md section 5")
