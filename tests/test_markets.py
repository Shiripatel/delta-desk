from pathlib import Path

from deltadesk.markets import universe
from deltadesk.markets.news import NewsService
from deltadesk.markets.service import MarketsService
from deltadesk.markets.watchlist import Watchlist


class OfflineNews(NewsService):
    def _fetch_one(self, name, url):
        raise OSError("offline")


def _svc(tmp_path: Path) -> MarketsService:
    return MarketsService(watchlist=Watchlist(tmp_path / "wl.json"), news=OfflineNews())


def test_indices_and_constituents(tmp_path):
    s = _svc(tmp_path)
    idx = s.indices()
    assert {i["code"] for i in idx} >= {"NIFTY50", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNEXT50", "SENSEX", "INDIAVIX"}
    assert all(i["quote"] and i["quote"]["ltp"] > 0 for i in idx)
    n50 = s.index("NIFTY50")
    assert n50 and len(n50["constituents"]) == 50
    assert all(r["quote"] for r in n50["constituents"])
    assert abs(sum(r["weight"] for r in n50["constituents"]) - 100) < 5
    b = n50["breadth"]
    assert b["advances"] + b["declines"] + b["unchanged"] == 50
    assert b["advances"] + b["declines"] > 0, "warm-up should produce dispersion"
    assert len(n50["gainers"]) == 5 and len(n50["losers"]) == 5
    assert n50["gainers"][0]["quote"]["change_pct"] >= n50["losers"][0]["quote"]["change_pct"]
    assert sum(sec["n"] for sec in n50["sectors"]) == 50
    assert s.index("NOPE") is None


def test_indicators_and_global_search(tmp_path):
    s = _svc(tmp_path)
    ind = s.indicators()
    groups = {i["group"] for i in ind}
    assert groups == {"india", "currency", "commodity", "crypto", "rates", "global"}
    assert all(i["quote"] and i["quote"]["ltp"] > 0 for i in ind)
    gold = next(i for i in ind if i["key"] == "GOLD")
    assert gold["decimals"] == 1 and "oz" in gold["unit"]
    assert any(h["kind"] == "global" and h["key"] == "BTC" for h in s.search("bitcoin"))
    assert s.known("US10Y")
    s.watchlist.add("My watchlist", "GOLD")
    assert any(r["key"] == "GOLD" and r["kind"] == "global" and r["quote"] for r in s.watchlists()["lists"]["My watchlist"])


def test_watchlist_persists_and_quotes(tmp_path):
    s = _svc(tmp_path)
    s.watchlist.add("My watchlist", "TITAN")
    s.watchlist.add("My watchlist", "USDINR")
    s.watchlist.remove("My watchlist", "INFY")
    again = Watchlist(tmp_path / "wl.json")
    assert "TITAN" in again.lists["My watchlist"] and "INFY" not in again.lists["My watchlist"]
    w = s.watchlists()["lists"]["My watchlist"]
    assert any(r["key"] == "NIFTY50" and r["kind"] == "index" and r["quote"] for r in w)
    assert any(r["key"] == "USDINR" and r["kind"] == "forex" and r["quote"] for r in w)
    assert s.known("GOLDBEES") and not s.known("NOPE")


def test_watchlist_limits_and_presets(tmp_path):
    import pytest

    from deltadesk.markets.watchlist import MAX_SYMBOLS, WatchlistError

    s = _svc(tmp_path)
    loaded = s.watchlist.load_preset("NIFTY50")
    assert loaded == "NIFTY 50" and len(s.watchlist.lists["NIFTY 50"]) == MAX_SYMBOLS
    with pytest.raises(WatchlistError):
        s.watchlist.add("NIFTY 50", "GOLD")            # full
    assert [p["code"] for p in s.watchlist_presets()][:2] == ["NIFTY50", "BANKNIFTY"]
    s.watchlist.rename("NIFTY 50", "Blue chips")
    assert "Blue chips" in s.watchlist.lists and "NIFTY 50" not in s.watchlist.lists
    with pytest.raises(WatchlistError):
        s.watchlist.load_preset("NOPE")
    for i in range(20):
        try:
            s.watchlist.create(f"list {i}")
        except WatchlistError:
            break
    assert len(s.watchlist.lists) == 12


def test_nse_csv_parser_overrides_seed():
    text = "Company Name,Industry,Symbol,Series,ISIN Code\nTest Co,Widgets,TESTCO,EQ,INE000A01001\n"
    old = universe.INDICES["BANKNIFTY"].constituents
    try:
        assert universe._apply_csv("BANKNIFTY", text) == 1
        c = universe.INDICES["BANKNIFTY"].constituents[0]
        assert c.symbol == "TESTCO" and c.sector == "Widgets" and c.weight == 100.0
    finally:
        universe.INDICES["BANKNIFTY"].constituents = old

