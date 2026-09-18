"""The contract every market-data source implements. Agents never see a vendor SDK."""
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from deltadesk.schemas import Bar, Instrument, Kind

IST = ZoneInfo("Asia/Kolkata")


class FeedEnded(Exception):
    """Raised when a replay or synthetic feed has no more ticks."""


class Feed(Protocol):
    name: str

    async def connect(self) -> None: ...

    async def instruments(self, underlying: str) -> list[Instrument]:
        """Index, VIX, near future and the option chain around ATM for the nearest weekly expiry."""
        ...

    async def subscribe(self, tokens: list[str], mode: str = "full") -> None: ...

    async def history(self, underlying: str) -> list[Bar]:
        """Previous session's 1-minute bars of the underlying, for the planner and indicator warm-up."""
        ...

    def ticks(self) -> AsyncIterator: ...

    async def close(self) -> None: ...


def next_weekly_expiry(today: date, weekday: int = 1) -> date:
    """NIFTY weekly expiry is Tuesday (weekday 1). Returns the first expiry strictly after today."""
    days = (weekday - today.weekday()) % 7
    if days == 0:
        days = 7
    from datetime import timedelta
    return today + timedelta(days=days)


def option_symbol(underlying: str, expiry: date, strike: float, kind: Kind) -> str:
    return f"{underlying} {expiry:%d%b%y}".upper() + f" {strike:.0f} {kind.value}"


def expiry_ts(expiry: date) -> datetime:
    return datetime(expiry.year, expiry.month, expiry.day, 15, 30, tzinfo=IST)
