import math

from deltadesk.markets import technicals as ta


def _bars(n: int = 300, drift: float = 0.003, amp: float = 0.002) -> list[dict]:
    out, px = [], 100.0
    for i in range(n):
        px *= 1 + drift + amp * math.sin(i / 3)
        out.append({"open": px * 0.995, "high": px * 1.01, "low": px * 0.99, "close": px})
    return out


def test_analyse_trending_up_reads_buy():
    r = ta.analyse(_bars(), "daily")
    assert r["summary"]["overall"] in ("Buy", "Strong buy") and r["summary"]["moving_averages"]["buy"] >= 10
    names = [i["name"] for i in r["indicators"]]
    assert names[0] == "RSI (14)" and "MACD (12,26)" in names and "ATR (14)" in names and len(names) == 12
    assert all(m["sma"] is not None and m["ema"] is not None for m in r["moving_averages"])
    p = r["pivots"]["methods"]
    classic = p[0]
    assert classic["S1"] < classic["P"] < classic["R1"] and p[4]["name"] == "DeMark" and p[4]["R2"] is None


def test_analyse_trending_down_and_short_series():
    r = ta.analyse(_bars(300, -0.003), "weekly")
    assert r["summary"]["overall"] in ("Sell", "Strong sell") and r["label"] == "Weekly"
    short = ta.analyse(_bars(10), "daily")
    assert short["error"] == "not enough bars"
    mid = ta.analyse(_bars(60), "1h")
    assert mid["moving_averages"][-1]["sma"] is None and mid["moving_averages"][0]["sma"] is not None


def test_pros_cons_rules():
    from deltadesk.markets.fundamentals import pros_cons
    pros, cons = pros_cons({"eps_cagr_3y": 22.0, "revenue_cagr_3y": 18.0, "roe": 25.0, "roce": 30.0, "debt_equity": 0.1, "pb": 8.0, "pe": 20.0,  # noqa: E501
                            "fcf_ttm_cr": 100.0, "net_income_ttm_cr": 110.0, "net_income_ttm_growth": 12.0})
    assert any("EPS" in p for p in pros) and any("debt free" in p for p in pros) and any("book value" in c for c in cons)
    pros, cons = pros_cons({"eps_cagr_3y": 2.0, "revenue_cagr_3y": 3.0, "roe": 6.0, "debt_equity": 2.0, "interest_coverage": 1.2, "fcf_ttm_cr": -5.0, "net_income_ttm_growth": -20.0})  # noqa: E501
    assert not pros and len(cons) == 6
