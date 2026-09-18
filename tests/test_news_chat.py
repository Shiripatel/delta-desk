"""News tagging, impact rule and the desk assistant, all offline."""
from pathlib import Path

from deltadesk.markets.news import Headline, LexiconAnalyzer, NewsService
from deltadesk.markets.service import MarketsService
from deltadesk.markets.watchlist import Watchlist


class CannedNews(NewsService):
    CANNED = [
        ("HDFC Bank shares surge 4% after strong Q2 results, brokerages upgrade", "https://x/1", 1_789_700_000),
        ("Reliance Industries falls as SEBI probe weighs on sentiment", "https://x/2", 1_789_690_000),
        ("Nifty ends flat; rupee steady near 95.8 against the dollar", "https://x/3", 1_789_680_000),
        ("Tata Motors and Maruti gain on festive demand hopes", "https://x/4", 1_789_670_000),
    ]

    def _fetch_one(self, name, url):
        if name != "Mint · Markets":
            raise OSError("offline")
        import hashlib
        return [Headline(id=hashlib.sha1(link.encode()).hexdigest()[:12], title=t, link=link, source=name, published="", ts=ts)
                for t, link, ts in self.CANNED]


def test_tagging_and_impact():
    n = CannedNews()
    f = n.feed(limit=10)
    by = {h["title"][:10]: h for h in f["entries"]}
    hdfc = by["HDFC Bank "]
    assert hdfc["symbols"] == ["HDFCBANK"] and hdfc["impact"] == "good" and "surge" in hdfc["reason"]
    ril = by["Reliance I"]
    assert ril["symbols"] == ["RELIANCE"] and ril["impact"] == "bad" and "SEBI" in ril["topics"]
    flat = by["Nifty ends"]
    assert flat["impact"] == "neutral" and {"NIFTY50", "USDINR"} <= set(flat["topics"])
    assert set(by["Tata Motor"]["symbols"]) == {"MARUTI", "TATAMOTORS"}
    assert f["counts"]["good"] >= 2 and f["counts"]["bad"] == 1
    assert [h["symbols"] for h in n.feed(symbols=["RELIANCE"])["entries"]] == [["RELIANCE"]]
    assert n.feed(impact="bad")["entries"][0]["symbols"] == ["RELIANCE"]
    assert n.item(hdfc["id"])["title"] == hdfc["title"] and n.item("nope") is None
    assert [h.title[:4] for h in n.for_symbol("HDFCBANK")] == ["HDFC"]


def test_lexicon_edge_cases():
    a = LexiconAnalyzer()
    mk = lambda t: Headline(id="x", title=t, link="", source="", published="", ts=0)  # noqa: E731
    assert a.analyse(mk("Company wins order but shares fall on weak margin"))[0] in ("neutral", "bad")
    assert a.analyse(mk("Board meeting scheduled for Tuesday"))[0] == "neutral"


def test_assistant_answers_from_desk_data(tmp_path: Path):
    s = MarketsService(watchlist=Watchlist(tmp_path / "wl.json"), news=CannedNews())
    r = s.assistant.answer("Is Reliance worth holding long term?")
    assert r["symbol"] == "RELIANCE" and r["horizon"] == "1y"
    assert "council says" in r["answer"] and "SEBI probe" in r["answer"] and any(x["kind"] == "council" for x in r["sources"])
    hid = s.news.feed()["entries"][0]["id"]
    r2 = s.assistant.answer("why is this news good or bad?", news_id=hid)
    assert r2["symbol"] == "HDFCBANK" and "Impact call: good" in r2["answer"]
    r3 = s.assistant.answer("what is the market doing?")
    assert r3["symbol"] is None and "NIFTY 50" in r3["answer"]
