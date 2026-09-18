"""Option-chain statistics used by the chain agent and the planner."""
from __future__ import annotations

from deltadesk.schemas import ChainRow


def max_pain(chain: list[ChainRow]) -> float:
    strikes = [r.strike for r in chain]
    best, best_pain = strikes[0], float("inf")
    for s in strikes:
        pain = 0.0
        for r in chain:
            pain += r.ce_oi * max(0.0, s - r.strike) + r.pe_oi * max(0.0, r.strike - s)
        if pain < best_pain:
            best, best_pain = s, pain
    return best


def walls(chain: list[ChainRow], atm: float) -> tuple[float, float]:
    above = [r for r in chain if r.strike >= atm] or chain
    below = [r for r in chain if r.strike <= atm] or chain
    call_wall = max(above, key=lambda r: r.ce_oi).strike
    put_wall = max(below, key=lambda r: r.pe_oi).strike
    return call_wall, put_wall


def pcr(chain: list[ChainRow]) -> float:
    ce = sum(r.ce_oi for r in chain)
    pe = sum(r.pe_oi for r in chain)
    return pe / ce if ce else 0.0


def atm_row(chain: list[ChainRow], atm: float) -> ChainRow:
    return min(chain, key=lambda r: abs(r.strike - atm))


def iv_at_delta(chain: list[ChainRow], target: float, call: bool) -> float | None:
    """IV of the strike whose |delta| is closest to target (e.g. 0.25)."""
    rows = [(abs((r.ce_delta if call else r.pe_delta) or 0) - target, r) for r in chain
            if (r.ce_iv if call else r.pe_iv) is not None]
    if not rows:
        return None
    _, r = min(rows, key=lambda t: abs(t[0]))
    return r.ce_iv if call else r.pe_iv
