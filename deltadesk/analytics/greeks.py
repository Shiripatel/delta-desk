"""Black-76 pricing and Greeks on the futures price. Pure Python, no scipy."""
from __future__ import annotations

import math

SQRT2 = math.sqrt(2.0)


def _N(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / SQRT2))


def _n(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _d1d2(F: float, K: float, T: float, sigma: float) -> tuple[float, float]:
    v = sigma * math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * sigma * sigma * T) / v
    return d1, d1 - v


def price(F: float, K: float, T: float, r: float, sigma: float, call: bool) -> float:
    if T <= 0 or sigma <= 0:
        return max(0.0, (F - K) if call else (K - F))
    d1, d2 = _d1d2(F, K, T, sigma)
    df = math.exp(-r * T)
    if call:
        return df * (F * _N(d1) - K * _N(d2))
    return df * (K * _N(-d2) - F * _N(-d1))


def greeks(F: float, K: float, T: float, r: float, sigma: float, call: bool) -> dict[str, float]:
    """delta, gamma, vega (per 1 vol point), theta (per calendar day)."""
    if T <= 0 or sigma <= 0:
        itm = (F > K) if call else (F < K)
        return {"delta": (1.0 if call else -1.0) if itm else 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0}
    d1, d2 = _d1d2(F, K, T, sigma)
    df = math.exp(-r * T)
    sq = math.sqrt(T)
    delta = df * _N(d1) if call else -df * _N(-d1)
    gamma = df * _n(d1) / (F * sigma * sq)
    vega = df * F * _n(d1) * sq / 100.0
    if call:
        theta = -df * F * _n(d1) * sigma / (2 * sq) - r * K * df * _N(d2) + r * F * df * _N(d1)
    else:
        theta = -df * F * _n(d1) * sigma / (2 * sq) + r * K * df * _N(-d2) - r * F * df * _N(-d1)
    return {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta / 365.0}


def implied_vol(target: float, F: float, K: float, T: float, r: float, call: bool,
                lo: float = 1e-4, hi: float = 5.0, tol: float = 1e-6) -> float | None:
    """Bisection. Returns None when the price is outside no-arbitrage bounds."""
    if T <= 0:
        return None
    intrinsic = math.exp(-r * T) * max(0.0, (F - K) if call else (K - F))
    if target <= intrinsic + 1e-9:
        return None
    if target >= price(F, K, T, r, hi, call):
        return None
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if price(F, K, T, r, mid, call) > target:
            hi = mid
        else:
            lo = mid
        if hi - lo < tol:
            break
    return 0.5 * (lo + hi)
