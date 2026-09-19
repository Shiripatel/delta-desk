import json
from datetime import date

from deltadesk.markets import ipo


def test_status_and_derived_fields():
    d = ipo.load(date(2026, 9, 19))
    by = {e["symbol"]: e for e in d["entries"]}
    assert by["MERIDIAN"]["status"] == "open" and by["NORTHLINE"]["status"] == "upcoming"
    assert by["TRIDENTF"]["status"] == "closed"          # lists today, no listing price yet
    assert by["SAFFRON"]["status"] == "listed" and by["SAFFRON"]["listing_gain_pct"] == 28.04
    assert by["MERIDIAN"]["min_investment"] == 150 * 99 and by["MERIDIAN"]["subscribed_x"] == 2.35
    assert d["stats"]["open"] == 2 and d["stats"]["listed_gain"] + d["stats"]["listed_loss"] == 8
    assert [e["status"] for e in d["entries"]] == sorted([e["status"] for e in d["entries"]], key=["open", "upcoming", "closed", "listed"].index)  # noqa: E501


def test_detail_agent_and_timeline():
    x = ipo.detail("meridian", date(2026, 9, 19), headlines=[{"title": "Meridian Foods IPO subscribed 2x", "description": "", "impact": "good"}])  # noqa: E501
    assert x["timeline"][0]["state"] == "done" and x["timeline"][-1]["state"] == "upcoming"
    names = [c["name"] for c in x["agent"]["checks"]]
    assert names == ["demand", "growth", "valuation", "issue structure", "news"]
    assert x["agent"]["checks"][-1]["reading"].startswith("1 headlines") and x["agent"]["stance"] in ("positive", "neutral", "cautious")
    assert ipo.detail("does-not-exist", date(2026, 9, 19)) is None


def test_performance_tracker_and_custom_file(tmp_path, monkeypatch):
    p = ipo.performance(2026, None, date(2026, 9, 19))
    assert p["years"] == [2026, 2025] and p["summary"]["count"] == 6 and p["summary"]["best"]["slug"] == "vistah"
    sme = ipo.performance(2026, "SME", date(2026, 9, 19))
    assert all(r["segment"] == "SME" for r in sme["rows"]) and sme["summary"]["count"] == 1
    f = tmp_path / "ipo.json"
    f.write_text(json.dumps([{"name": "Real Co Ltd", "symbol": "REALCO", "segment": "Mainboard", "open": "2026-09-01", "close": "2026-09-03",  # noqa: E501
                              "listing": "2026-09-08", "price_lo": 100, "price_hi": 110, "lot": 100, "issue_size_cr": 500, "listing_close": 132}]))  # noqa: E501
    monkeypatch.setattr(ipo, "PATH", f)
    d = ipo.load(date(2026, 9, 19), quotes=lambda keys: {})
    assert d["source"] == str(f) and d["entries"][0]["slug"] == "realco" and d["entries"][0]["listing_gain_pct"] == 20.0
    assert d["entries"][0]["current_price"] is None
