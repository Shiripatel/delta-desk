"""Feed adapters. `make_feed(settings)` returns the one selected by DD_FEED."""
from __future__ import annotations

from deltadesk.config import Settings
from deltadesk.feeds.base import Feed


def make_feed(settings: Settings, **kw) -> Feed:
    if settings.feed == "synthetic":
        from deltadesk.feeds.synthetic import SyntheticFeed
        return SyntheticFeed(settings, **kw)
    if settings.feed == "kite":
        from deltadesk.feeds.kite import KiteFeed
        return KiteFeed(settings, **kw)
    if settings.feed == "upstox":
        from deltadesk.feeds.upstox import UpstoxFeed
        return UpstoxFeed(settings, **kw)
    if settings.feed == "dhan":
        from deltadesk.feeds.dhan import DhanFeed
        return DhanFeed(settings, **kw)
    raise ValueError(f"feed {settings.feed!r} is not implemented yet")
