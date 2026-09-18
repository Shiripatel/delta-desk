"""Upstox adapter tests that need no network or token: feed message parsing, instrument-master lookups,
key mapping for the quote provider, token loading order."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from deltadesk.auth import load_token, save_token
from deltadesk.feeds.upstox import parse_feed
from deltadesk.markets.upstox_master import InstrumentMaster

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 9, 18, 10, 0, tzinfo=IST)


def test_parse_market_full_feed():
    feed = {"fullFeed": {"marketFF": {"ltpc": {"ltp": 62.4, "ltt": "1789700000000", "ltq": "75", "cp": 60.1},
                                      "marketLevel": {"bidAskQuote": [{"bidQ": "150", "bidP": 62.3, "askQ": "75", "askP": 62.5}]},
                                      "optionGreeks": {"delta": 0.31, "theta": -9.2, "gamma": 0.0012, "vega": 8.1, "rho": 0.4},
                                      "vtt": "1234567", "oi": 4100000.0, "iv": 0.132}}}
    t = parse_feed("NSE_FO|49480", feed, NOW)
    assert t is not None and t.ltp == 62.4 and t.bid == 62.3 and t.ask == 62.5
    assert t.volume == 1234567 and t.oi == 4100000 and t.ts.year >= 2026


def test_parse_index_and_ltpc_feeds():
    idx = {"fullFeed": {"indexFF": {"ltpc": {"ltp": 25412.4, "ltt": "0", "cp": 25334.25}}}}
    t = parse_feed("NSE_INDEX|Nifty 50", idx, NOW)
    assert t is not None and t.ltp == 25412.4 and t.ts == NOW and t.bid is None
    t2 = parse_feed("NSE_INDEX|India VIX", {"ltpc": {"ltp": 13.42, "cp": 13.7}}, NOW)
    assert t2 is not None and t2.ltp == 13.42
    assert parse_feed("x", {"requestMode": "full"}, NOW) is None


def _fake_master() -> InstrumentMaster:
    exp = int(datetime(2026, 9, 22, 14, 30, tzinfo=IST).timestamp() * 1000)
    exp_m = int(datetime(2026, 9, 29, 14, 30, tzinfo=IST).timestamp() * 1000)
    rows = [
        {"segment": "NSE_EQ", "trading_symbol": "HDFCBANK", "instrument_key": "NSE_EQ|INE040A01034", "name": "HDFC BANK",
         "instrument_type": "EQ"},
        {"segment": "NSE_INDEX", "name": "Nifty 50", "instrument_key": "NSE_INDEX|Nifty 50", "instrument_type": "INDEX"},
        {"segment": "NSE_INDEX", "name": "India VIX", "instrument_key": "NSE_INDEX|India VIX", "instrument_type": "INDEX"},
        {"segment": "NSE_FO", "underlying_symbol": "NIFTY", "instrument_type": "FUT", "expiry": exp_m, "instrument_key": "NSE_FO|1",
         "lot_size": 75, "trading_symbol": "NIFTY FUT 29 SEP 26"},
    ]
    for k in (25200, 25250, 25300, 25350, 25400):
        for kind in ("CE", "PE"):
            rows.append({"segment": "NSE_FO", "underlying_symbol": "NIFTY", "instrument_type": kind, "expiry": exp,
                         "strike_price": float(k), "instrument_key": f"NSE_FO|{k}{kind}", "lot_size": 75})
    m = InstrumentMaster()
    m.index(rows)
    return m


def test_master_lookups():
    m = _fake_master()
    assert m.equity_key("HDFCBANK") == "NSE_EQ|INE040A01034" and m.equity_key("NOPE") is None
    assert m.index_key("NIFTY50") == "NSE_INDEX|Nifty 50" and m.index_key("INDIAVIX") == "NSE_INDEX|India VIX"
    assert m.nearest_expiry("NIFTY50", date(2026, 9, 18)) == date(2026, 9, 22)
    assert m.nearest_expiry("NIFTY50", date(2026, 9, 23)) is None
    assert m.futures_key("NIFTY50", date(2026, 9, 29)) == "NSE_FO|1"
    ch = m.chain("NIFTY50", date(2026, 9, 22), 25300, 50, 1)
    assert [(r["strike_price"], r["instrument_type"]) for r in ch] == [(25250.0, "CE"), (25250.0, "PE"), (25300.0, "CE"),
                                                                        (25300.0, "PE"), (25350.0, "CE"), (25350.0, "PE")]


def test_quote_key_mapping_without_network():
    from deltadesk.markets.quotes_upstox import UpstoxQuotes

    q = UpstoxQuotes.__new__(UpstoxQuotes)      # skip __init__ (needs a token); only test map_key
    q.master = _fake_master()
    assert q.map_key("HDFCBANK") == "NSE_EQ|INE040A01034"
    assert q.map_key("NIFTY50") == "NSE_INDEX|Nifty 50"
    assert q.map_key("FUT:NIFTY50:2026-09-29") == "NSE_FO|1"
    assert q.map_key("USDINR") is None


def test_token_env_then_file(tmp_path, monkeypatch):
    import deltadesk.auth as auth

    monkeypatch.setattr(auth, "TOKEN_DIR", tmp_path)
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN", raising=False)
    assert load_token("upstox") is None
    save_token("upstox", "file-token")
    assert load_token("upstox") == "file-token"
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "env-token")
    assert load_token("upstox") == "env-token"
