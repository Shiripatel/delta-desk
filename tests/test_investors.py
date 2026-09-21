import json

from deltadesk.markets import investors as inv


class Q:
    def __init__(self, ltp, chg):
        self.ltp, self.change_pct = ltp, chg

    def json(self):
        return {"ltp": self.ltp, "change_pct": self.change_pct}


def test_seed_loads_and_values(tmp_path, monkeypatch):
    d = inv.load(quotes=lambda keys: {k: Q(100.0, 1.0) for k in keys}, market_caps=lambda keys: {k: 10000 for k in keys}, names=lambda k: (k.title(), "stock", "Consumer"))  # noqa: E501
    assert d["count"] >= 6 and all(i["seed"] for i in d["investors"]) and "seed" in d["source"]
    top = d["investors"][0]
    assert top["summary"]["value_cr"] > 0 and top["holdings"][0]["value_cr"] >= top["holdings"][-1]["value_cr"] and top["summary"]["day_avg_pct"] == 1.0  # noqa: E501
    assert inv.one("vijay-kedia")["name"].startswith("Vijay") and inv.one("nobody") is None
    f = tmp_path / "investors.json"
    f.write_text(json.dumps([{"name": "Test Investor", "known_for": "tests", "style": ["x"], "holdings": [{"symbol": "ABC", "stake_pct": 2.0}]}]))  # noqa: E501
    monkeypatch.setattr(inv, "PATH", f)
    e = inv.load()
    assert e["source"] == str(f) and e["investors"][0]["slug"] == "test-investor" and e["investors"][0]["holdings"][0]["value_cr"] is None and "seed" not in e["investors"][0]  # noqa: E501
