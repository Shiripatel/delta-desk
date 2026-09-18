from __future__ import annotations

from typing import Literal

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class Limits(BaseModel):
    account: float = 500_000.0          # paper account, rupees
    margin_cap: float = 350_000.0
    max_loss_per_trade: float = 50_000.0
    daily_drawdown: float = 25_000.0
    max_lots: int = 4
    max_open_structures: int = 2
    net_vega_min: float = -2_000.0      # rupees per vol point across the book
    net_vega_max: float = 2_000.0
    net_delta_abs_max: float = 1.0      # in lot-equivalents of the underlying, per open structure
    trading_window: tuple[str, str] = ("09:30", "14:45")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DD_", env_file=".env", extra="ignore")

    feed: Literal["synthetic", "replay", "kite", "upstox", "dhan"] = "synthetic"
    mode: Literal["paper", "live"] = "paper"
    underlying: str = "NIFTY"
    lot_size: int = 65                  # NIFTY lot; overridden by the instrument master at start
    strike_step: float = 50.0
    strikes_each_side: int = 20
    cycle_seconds: float = 2.0
    confidence_threshold: float = 0.65
    auto_approve: bool = False
    risk_free: float = 0.065
    limits: Limits = Limits()
