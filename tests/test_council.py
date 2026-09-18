from deltadesk.markets.council import HORIZONS, Bar, Council, SyntheticBars, agent_macd, agent_momentum, agent_trend


def _bars(n=120, daily=0.004):
    import math
    out, px = [], 100.0
    for i in range(n):
        o = px
        px = 100 * math.exp(daily * (i + 1))
        out.append(Bar(1e9 + i * 86400, o, max(o, px) * 1.002, min(o, px) * 0.998, px, 1e6))
    return out


def test_technical_agents_read_a_clean_uptrend():
    b = _bars()
    assert agent_trend(b)["signal"] > 0.5
    assert agent_momentum(b)["signal"] > 0.3
    assert agent_macd(b)["signal"] > 0.3
    assert agent_trend(_bars(daily=-0.004))["signal"] < -0.5


def test_council_weights_shift_with_horizon():
    c = Council(SyntheticBars())
    short = c.run("HDFCBANK", "15m")
    long = c.run("HDFCBANK", "10y")
    assert short["weights"]["technical"] > 0.9 and long["weights"]["fundamental"] > 0.8
    assert {a["name"] for a in short["agents"]} == {"trend", "momentum", "macd", "volume", "volatility", "levels",
                                                    "valuation", "growth", "quality", "ownership"}
    assert abs(sum(a["horizon_weight"] for a in short["agents"]) - 1) < 1e-3
    assert short["verdict"]["stance"] in ("buy", "hold", "sell") and -1 <= short["verdict"]["score"] <= 1
    assert short["sources"]["fundamentals"] == "example data"


def test_council_without_fundamentals_redistributes_weight():
    c = Council(SyntheticBars())
    r = c.run("BAJFINANCE", "3y")                      # no example fundamentals for this one
    fund = [a for a in r["agents"] if a["group"] == "fundamental"]
    assert all(not a["available"] and a["horizon_weight"] == 0 for a in fund)
    assert r["verdict"]["coverage"] < 0.5 and r["sources"]["fundamentals"].startswith("no data")
    assert Council(SyntheticBars()).run("TCS", "bogus")["horizon"] == "1d"
    assert set(HORIZONS) == {"15m", "1h", "1d", "1w", "1mo", "3mo", "1y", "3y", "10y"}
