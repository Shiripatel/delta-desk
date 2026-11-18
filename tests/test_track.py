"""Track record of the AI score: walk-forward zones versus what happened next."""
import math

from deltadesk.markets.ai_rank import SyntheticHistory
from deltadesk.markets.track import SPEC, TrackRecord, headline, summarise, windows, zone_of


def _trend(n, daily):
    return [100.0 * math.exp(daily * i) for i in range(n)]


def test_zones_and_windows_on_clean_trends():
    assert zone_of(10) == "buy" and zone_of(7) == "buy" and zone_of(6) == "hold" and zone_of(4) == "hold" and zone_of(3) == "sell"
    up = windows(_trend(120, 0.004), 63, (5, 20))
    assert len(up) == 120 - 63 - 20 + 1 and all(z == "buy" for _, z, _ in up) and all(r[20] > 0 for _, _, r in up)
    dn = windows(_trend(120, -0.004), 63, (5, 20))
    assert all(z == "sell" for _, z, _ in dn) and all(r[5] < 0 for _, _, r in dn)
    assert windows(_trend(80, 0.004), 63, (5, 20)) == []          # 63 + 20 bars needed before the first window closes


def test_summary_counts_add_up_and_hit_rate_is_right():
    s = summarise(windows(_trend(120, 0.004), 63, (5, 20)) + windows(_trend(120, -0.004), 63, (5, 20)), (5, 20))
    assert s["windows"] == sum(z["n"] for z in s["zones"]) == 76
    buy, hold, sell = s["zones"]
    assert buy["n"] == 38 and sell["n"] == 38 and hold["n"] == 0 and hold["h"]["5"]["up"] is None
    assert buy["h"]["20"]["up"] == 100.0 and sell["h"]["20"]["up"] == 0.0 and s["base"]["20"]["up"] == 50.0
    assert s["hit"]["5"] == {"n": 76, "rate": 100.0} and buy["h"]["5"]["mean"] > 0 > sell["h"]["5"]["median"]


def test_report_on_synthetic_history_short_and_long():
    tr = TrackRecord(SyntheticHistory(days=260), SyntheticHistory(days=200, weekly=True))
    r = tr.report("BANKNIFTY")
    assert r["mode"] == "short" and r["unit"] == "sessions" and r["horizons"] == [5, 20] and r["window"] == SPEC["short"]["window"]
    assert r["stocks"] == 12 and r["windows"] == sum(z["n"] for z in r["zones"]) > 1000 and r["from"] < r["to"]
    assert 0 <= r["base"]["5"]["up"] <= 100 and r["hit"]["20"]["n"] <= r["windows"] and "windows" in r["headline"]
    assert r["note"].endswith("Not investment advice.")
    assert tr.report("BANKNIFTY") is r                               # cached
    lg = tr.report("BANKNIFTY", "long")
    assert lg["unit"] == "weeks" and lg["horizons"] == [4, 13] and lg["windows"] > 500 and lg["source"] == "synthetic"
    assert headline({"horizons": [5], "unit": "sessions", "windows": 0, "zones": [], "base": {"5": {"up": None}}}).startswith("Not enough")
