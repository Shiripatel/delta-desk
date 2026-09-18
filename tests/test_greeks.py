import math

from deltadesk.analytics.greeks import greeks, implied_vol, price


def test_put_call_parity():
    F, K, T, r, s = 25_400.0, 25_600.0, 5 / 365, 0.065, 0.13
    c, p = price(F, K, T, r, s, True), price(F, K, T, r, s, False)
    assert abs((c - p) - math.exp(-r * T) * (F - K)) < 1e-6


def test_iv_roundtrip():
    F, K, T, r, s = 25_400.0, 25_200.0, 4 / 365, 0.065, 0.142
    px = price(F, K, T, r, s, False)
    assert abs(implied_vol(px, F, K, T, r, False) - s) < 1e-4


def test_greek_signs():
    g = greeks(25_400.0, 25_400.0, 4 / 365, 0.065, 0.13, True)
    assert 0.45 < g["delta"] < 0.6
    assert g["gamma"] > 0 and g["vega"] > 0 and g["theta"] < 0
    gp = greeks(25_400.0, 25_400.0, 4 / 365, 0.065, 0.13, False)
    assert -0.6 < gp["delta"] < -0.4


def test_iv_outside_bounds_is_none():
    assert implied_vol(0.01, 25_400.0, 25_000.0, 4 / 365, 0.065, True) is None
