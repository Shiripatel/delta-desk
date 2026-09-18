"""Typed contracts between agents. Every agent consumes and emits these models only."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Kind(str, Enum):
    IDX = "IDX"
    FUT = "FUT"
    CE = "CE"
    PE = "PE"


class Instrument(BaseModel):
    token: str
    symbol: str                 # e.g. "NIFTY 22SEP26 25600 CE"
    underlying: str
    kind: Kind
    strike: float | None = None
    expiry: date | None = None
    lot_size: int = 1


class Tick(BaseModel):
    ts: datetime
    token: str
    ltp: float
    bid: float | None = None
    ask: float | None = None
    volume: int = 0
    oi: int = 0


class Bar(BaseModel):
    ts: datetime                # bar open time
    open: float
    high: float
    low: float
    close: float
    volume: int = 0


class ChainRow(BaseModel):
    strike: float
    expiry: date
    ce_ltp: float
    pe_ltp: float
    ce_oi: int
    pe_oi: int
    ce_iv: float | None = None  # annualised, 0.13 = 13 %
    pe_iv: float | None = None
    ce_delta: float | None = None
    pe_delta: float | None = None
    gamma: float | None = None
    vega: float | None = None   # per 1 vol point, per unit
    theta: float | None = None  # per calendar day, per unit (call side)


class Snapshot(BaseModel):
    ts: datetime
    underlying: str
    spot: float
    fut: float
    vix: float
    expiry: date
    t_years: float              # time to expiry in years
    atm: float
    chain: list[ChainRow]
    bars_1m: list[Bar]          # today's 1-minute bars so far
    prev_bars_1m: list[Bar]     # previous session, for the planner
    feed_latency_ms: float = 0.0
    instruments: dict[str, Instrument] = Field(default_factory=dict)  # symbol -> instrument


class Regime(str, Enum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGE_BOUND = "RANGE_BOUND"
    EVENT = "EVENT"


class RegimeCall(BaseModel):
    regime: Regime
    p: float = Field(ge=0, le=1)
    adx: float
    realised_vol: float         # annualised
    features: dict[str, float] = Field(default_factory=dict)


class ChainStats(BaseModel):
    atm_iv: float
    iv_rank: float | None       # 0..100 against stored history, None if no history
    pcr_oi: float
    max_pain: float
    call_wall: float
    put_wall: float
    expected_move_pts: float    # 1 sigma to expiry
    expected_move_pct: float
    skew: float                 # 25d put IV minus 25d call IV, in vol points
    iv_minus_rv: float          # ATM IV minus realised vol, vol points


class ZoneKind(str, Enum):
    FADE = "FADE"               # expect rejection at level
    BREAK = "BREAK"             # expect continuation through level
    PREMIUM = "PREMIUM"         # sell premium outside expected move


class Zone(BaseModel):
    id: str
    kind: ZoneKind
    lo: float
    hi: float
    source: str                 # "PDH", "PDL", "CPR", "call_wall", "put_wall", "exp_move"
    direction: Literal["UP", "DOWN", "NONE"] = "NONE"
    compatible: list[Regime]
    structures: list[str]       # allowed structures if fired
    armed: bool = False
    fired_at: datetime | None = None


class DayPlan(BaseModel):
    date: date
    underlying: str
    pdh: float
    pdl: float
    pdc: float
    pivot: float
    bc: float
    tc: float
    bias: Literal["LONG", "SHORT", "NEUTRAL"]
    zones: list[Zone]
    notes: list[str] = Field(default_factory=list)


class Trigger(BaseModel):
    ts: datetime
    zone: Zone
    spot: float
    quality: float = Field(ge=0, le=1)
    why: str


class Leg(BaseModel):
    side: Side
    symbol: str
    kind: Kind
    strike: float
    lots: int
    limit: float


class CandidateTrade(BaseModel):
    id: str
    ts: datetime
    structure: str              # "short_strangle", "bull_call_spread", ...
    zone_id: str = ""
    legs: list[Leg]
    lot_size: int
    stop: float | None          # on the structure's net premium per unit
    target: float | None
    confidence: float = Field(ge=0, le=1)
    regime: Regime
    why: str
    valid_until: datetime


class RiskVerdict(BaseModel):
    risk_ok: bool
    reasons: list[str]
    margin: float               # this trade's own margin estimate
    margin_after: float
    max_loss: float
    net_delta: float
    net_vega: float


DecisionState = Literal["held", "awaiting_approval", "approved", "rejected", "executed", "expired", "vetoed"]


class Decision(BaseModel):
    id: str
    ts: datetime
    trade: CandidateTrade
    risk: RiskVerdict
    threshold: float
    state: DecisionState


class Fill(BaseModel):
    ts: datetime
    symbol: str
    side: Side
    qty: int
    price: float


class Position(BaseModel):
    symbol: str
    kind: Kind
    strike: float
    qty: int                    # signed, in units (lots * lot_size)
    avg: float
    ltp: float
    delta: float = 0.0
    theta_day: float = 0.0
    vega: float = 0.0

    @property
    def pnl(self) -> float:
        return (self.ltp - self.avg) * self.qty


class OrderState(BaseModel):
    ts: datetime
    mode: Literal["paper", "live"]
    open_orders: int
    positions: list[Position]
    realised: float
    unrealised: float
    fills_today: list[Fill] = Field(default_factory=list)


class AgentStatus(BaseModel):
    name: str
    version: str
    ok: bool
    ms: float
    summary: str = ""
    error: str | None = None


class CycleReport(BaseModel):
    ts: datetime
    seq: int
    ms: float
    agents: list[AgentStatus]
