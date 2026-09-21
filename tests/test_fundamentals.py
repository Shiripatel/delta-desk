import json
import time

from deltadesk.markets import fundamentals as fm
from deltadesk.markets.council import Council, SyntheticBars

SERIES = {
    "annual": {"TotalRevenue": {"2023-03-31": 100e7, "2024-03-31": 120e7, "2025-03-31": 150e7, "2026-03-31": 180e7},
               "GrossProfit": {"2026-03-31": 90e7}, "NetIncome": {"2023-03-31": 10e7, "2024-03-31": 12e7, "2025-03-31": 18e7, "2026-03-31": 27e7},  # noqa: E501
               "DilutedEPS": {"2023-03-31": 10.0, "2026-03-31": 27.0}, "StockholdersEquity": {"2026-03-31": 100e7}, "TotalDebt": {"2026-03-31": 40e7},  # noqa: E501
               "TotalAssets": {"2026-03-31": 300e7}, "CurrentAssets": {"2026-03-31": 60e7}, "CurrentLiabilities": {"2026-03-31": 30e7}, "FreeCashFlow": {"2026-03-31": 20e7}},  # noqa: E501
    "quarterly": {"TotalRevenue": {"2025-09-30": 40e7, "2025-12-31": 45e7, "2026-03-31": 50e7, "2026-06-30": 55e7},
                  "NetIncome": {"2025-09-30": 5e7, "2025-12-31": 6e7, "2026-03-31": 8e7, "2026-06-30": 9e7}},
    "trailing": {"PeRatio": {"2026-09-01": 30.0, "2026-09-18": 25.0}, "PbRatio": {"2026-09-18": 4.0}, "MarketCap": {"2026-09-18": 5000e7}},
    "monthly": [{"date": "2026-03-31", "close": 500.0}], "dividends": [{"date": "2025-08-01", "amount": 5.0}, {"date": "2026-08-01", "amount": 6.0}], "splits": [], "meta": {"regularMarketPrice": 520.0},  # noqa: E501
}


def test_compose_statements_ratios_snapshot():
    a = fm.compose({"symbol": "TESTCO", "yahoo": "TESTCO.NS", "fetched_at": time.time(), "series": SERIES})
    assert a["periods"]["annual"][-1] == "2026-03-31" and a["statements"]["annual"]["TotalRevenue"]["2026-03-31"] == 180.0
    r = a["ratios"]["annual"]
    assert r["gross_margin"]["2026-03-31"] == 50.0 and r["revenue_growth"]["2026-03-31"] == 20.0 and r["roe"]["2026-03-31"] == 27.0
    assert r["debt_equity"]["2026-03-31"] == 0.4 and r["current_ratio"]["2026-03-31"] == 2.0 and r["revenue_growth"]["2023-03-31"] is None
    assert a["ttm"]["TotalRevenue"] == 190.0 and a["ttm"]["NetIncome"] == 28.0
    s = a["snapshot"]
    assert s["pe"] == 25.0 and s["pb"] == 4.0 and s["market_cap_cr"] == 5000 and s["revenue_cagr_3y"] == 21.6 and s["eps_cagr_3y"] == 39.2
    assert s["net_margin"] == 14.7 and a["council"]["roe"] == 28.0
    assert a["dividends"]["years_paying"] == 2 and a["dividends"]["by_fy"][-1]["dps"] == 6.0 and a["tables"]["ratios"]["annual"][0]["label"] == "Period-end price"  # noqa: E501
    assert a["statistics"]["Scores"][1]["label"] == "Piotroski F-score" and a["fiscal_note"].startswith("Financials in")


def test_symbols_and_cache(tmp_path, monkeypatch):
    f = fm.YahooFundamentals(cache_dir=tmp_path)
    assert f.yahoo_symbol("RELIANCE") == "RELIANCE.NS" and f.yahoo_symbol("NIFTY50") is None and f.yahoo_symbol("GOLD") is None and f.yahoo_symbol("USDINR") is None  # noqa: E501
    assert f.analysis("NIFTY50") is None
    (tmp_path / "TESTCO.json").write_text(json.dumps({"symbol": "TESTCO", "yahoo": "TESTCO.NS", "fetched_at": time.time(), "series": SERIES}))  # noqa: E501
    a = f.analysis("TESTCO")
    assert a["snapshot"]["pe"] == 25.0                      # served from the disk cache, no network
    summary, src = f.council_summary("TESTCO")
    assert summary["pe"] == 25.0 and src.startswith("yahoo fundamentals")
    monkeypatch.setattr(f, "_fetch", lambda ysym: (_ for _ in ()).throw(OSError("offline")))
    bad = f.analysis("NOPE")
    assert bad["error"] == "offline"
    c = Council(SyntheticBars(), fundamentals=f.council_summary)
    r = c.run("TESTCO", "1y")
    assert r["sources"]["fundamentals"].startswith("yahoo fundamentals") and any(a["group"] == "fundamental" and a["available"] for a in r["agents"])  # noqa: E501
