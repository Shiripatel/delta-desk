from pathlib import Path

from deltadesk.beta import Alerts, Notifier, Waitlist
from deltadesk.markets.service import MarketsService
from deltadesk.markets.watchlist import Watchlist
from tests.test_news_chat import CannedNews


def test_waitlist_validates_and_dedupes(tmp_path: Path):
    w = Waitlist(tmp_path / "wl.jsonl")
    assert w.join("A", "bad", "")["ok"] is False
    assert w.join("Shirish", "s@x.com", "12", [])["ok"] is False
    r = w.join("Shirish", "S@X.com", "+919999999999", ["fno", "ipo", "nope"], "2-5y", True)
    assert r["ok"] and r["position"] == 1 and not r["duplicate"]
    again = w.join("Shirish", "s@x.com")
    assert again["duplicate"] and again["position"] == 1
    st = w.stats()
    assert st["total"] == 1 and st["whatsapp"] == 1 and st["interests"] == {"fno": 1, "ipo": 1}


class Recorder(Notifier):
    name = "recorder"

    def __init__(self):
        self.sent = []

    def send(self, to, text):
        self.sent.append((to, text))
        return {"sent": True, "channel": self.name, "to": to}


def test_alert_rules_fire_and_cool_down(tmp_path: Path):
    m = MarketsService(watchlist=Watchlist(tmp_path / "w.json"), news=CannedNews())
    rec = Recorder()
    a = Alerts(m, notifier=rec, path=tmp_path / "a.json", log_path=tmp_path / "log.jsonl", cooldown=3600)
    assert a.add("+919999999999", "price_move", "NOPE", 1)["ok"] is False
    assert a.add("", "price_move", "HDFCBANK", 1)["ok"] is False
    assert a.add("+919999999999", "price_move", "HDFCBANK", 0.0)["ok"] is False
    r1 = a.add("+919999999999", "price_move", "HDFCBANK", 0.0001)          # any move fires
    r2 = a.add("+919999999999", "bad_news", "RELIANCE")                    # canned feed has a bad Reliance story
    r3 = a.add("chat123", "verdict_flip", "TCS", horizon="1d")              # needs a change; first pass only records
    assert r1["ok"] and r2["ok"] and r3["ok"] and len(a.for_contact("+919999999999")) == 2
    fired = a.evaluate(now=1_000_000)
    kinds = sorted(f["kind"] for f in fired)
    assert kinds == ["bad_news", "price_move"] and len(rec.sent) == 2
    assert "not advice" in rec.sent[0][1]
    assert a.evaluate(now=1_000_100) == []                                  # cooldown + news already seen
    assert len(a.log()) == 2 and a.log()[0]["sent"] is True
    assert a.remove(r1["rule"]["id"]) and not a.remove("nope")
    assert Notifier().send("x", "y")["sent"] is False


def test_waitlist_store_falls_back_without_database(monkeypatch):
    from deltadesk.beta import Waitlist, WaitlistDB, waitlist_from_env
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert type(waitlist_from_env()) is Waitlist
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@127.0.0.1:1/none")   # unreachable: must fall back, not crash
    assert type(waitlist_from_env()) is Waitlist
    assert issubclass(WaitlistDB, Waitlist)
