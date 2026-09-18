"""Yahoo delayed-quote provider, with the HTTP call replaced by canned `meta` blocks."""
from deltadesk.markets.quotes_yahoo import YahooQuotes

META = {
    "^NSEI": {"regularMarketPrice": 23328.65, "chartPreviousClose": 23270.6, "regularMarketDayHigh": 23360.55,
              "regularMarketDayLow": 23286.6, "regularMarketVolume": 0, "regularMarketTime": 1789705835},
    "HDFCBANK.NS": {"regularMarketPrice": 721.8, "chartPreviousClose": 713.0, "regularMarketDayHigh": 721.9,
                    "regularMarketDayLow": 715.25, "regularMarketVolume": 2792026, "regularMarketTime": 1789705835},
    "USDINR=X": {"regularMarketPrice": 95.73, "previousClose": 95.92, "regularMarketDayHigh": 95.93,
                 "regularMarketDayLow": 95.7, "regularMarketTime": 1789705827},
}


class Fake(YahooQuotes):
    def _fetch_chart(self, sym: str) -> dict:
        if sym not in META:
            raise ValueError("404")
        return META[sym]


def test_mapping():
    assert YahooQuotes.map_symbol("NIFTY50") == "^NSEI"
    assert YahooQuotes.map_symbol("HDFCBANK") == "HDFCBANK.NS"
    assert YahooQuotes.map_symbol("M&M") == "M&M.NS"
    assert YahooQuotes.map_symbol("USDINR") == "USDINR=X"
    assert YahooQuotes.map_symbol("GOLD") == "GC=F" and YahooQuotes.map_symbol("US10Y") == "^TNX"
    assert YahooQuotes.map_symbol("MIDCPNIFTY") is None
    assert YahooQuotes.map_symbol("FUT:NIFTY50:2026-09-29") is None


def test_quotes_values_cache_and_errors():
    y = Fake(ttl=60)
    q = y.quotes(["NIFTY50", "HDFCBANK", "USDINR", "MIDCPNIFTY", "NOPE", "FUT:NIFTY50:2026-09-29"])
    assert set(q) == {"NIFTY50", "HDFCBANK", "USDINR"}
    n = q["NIFTY50"]
    assert n.ltp == 23328.65 and n.prev_close == 23270.6 and n.change == 58.05 and n.change_pct == 0.25
    assert q["HDFCBANK"].volume == 2792026 and q["HDFCBANK"].high == 721.9
    assert q["USDINR"].ltp == 95.73 and q["USDINR"].change == -0.19
    assert "NOPE" in y.errors and "MIDCPNIFTY" not in y.errors
    assert y.fetches == 3
    y.quotes(["NIFTY50", "HDFCBANK"])          # inside ttl: no new fetches
    assert y.fetches == 3
    assert y.delay_min == 15 and y.name == "yahoo"


def test_service_runs_on_yahoo(tmp_path):
    from deltadesk.markets.service import MarketsService
    from deltadesk.markets.watchlist import Watchlist

    s = MarketsService(quotes=Fake(), watchlist=Watchlist(tmp_path / "wl.json"))
    idx = {i["code"]: i["quote"] for i in s.indices()}
    assert idx["NIFTY50"]["ltp"] == 23328.65 and idx["MIDCPNIFTY"] is None
    n50 = s.index("NIFTY50")
    assert any(r["symbol"] == "HDFCBANK" and r["quote"] for r in n50["constituents"])
    assert n50["breadth"]["advances"] + n50["breadth"]["declines"] + n50["breadth"]["unchanged"] == 1
    w = s.watchlists()["lists"]["Core"]
    assert any(r["key"] == "HDFCBANK" and r["quote"] for r in w)
    assert any(r["key"] == "TCS" and r["quote"] is None for r in w)   # unavailable rows still render
