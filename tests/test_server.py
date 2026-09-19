"""Routes and static assets served by the app (synthetic feed, no network)."""
import warnings

from deltadesk.config import Settings
from deltadesk.feeds.synthetic import SyntheticFeed
from deltadesk.pipeline import Pipeline
from deltadesk.server.app import create_app


def _client():
    warnings.simplefilter("ignore")
    import tempfile
    from pathlib import Path

    from fastapi.testclient import TestClient

    from deltadesk.beta import Alerts, Notifier, Waitlist

    d = Path(tempfile.mkdtemp())
    s = Settings(feed="synthetic", cycle_seconds=30, _env_file=None)
    from deltadesk.markets.service import MarketsService
    m = MarketsService()
    return TestClient(create_app(Pipeline(s, SyntheticFeed(s, speed=0.0)), cycles=1, markets=m, waitlist=Waitlist(d / "wl.jsonl"),
                                 alerts=Alerts(m, notifier=Notifier(), path=d / "a.json", log_path=d / "log.jsonl"), alert_interval=3600))


def test_pages_and_assets():
    with _client() as c:
        home = c.get("/").text
        assert "LLM agents" in home and 'id="rdSvg"' in home and 'id="aiBody"' in home and "/static/ai.js" in home
        for path, marker in (("/news", 'id="flow"'), ("/analysis", "lightweight-charts"), ("/static/vendor/lightweight-charts.standalone.production.js", "createChart")):  # noqa: E501
            assert marker in c.get(path).text, path
        assert 'href="/news">News</a>' in home and 'href="/sniper">Sniper</a>' in home
        dom = c.get("/markets/domains").json()
        assert dom["HDFCBANK"] == "hdfcbank.com" and len(dom) > 100
        assert c.get("/static/ui.js").status_code == 200 and "/static/ui.js" in home
        assert 'id="fxmap"' in c.get("/forex").text and len(c.get("/markets/forex-market").json()["world"]) == 10
        assert "waitlist" in c.get("/beta").text and "Risk disclosure" in c.get("/legal").text
        w = c.post("/waitlist", json={"name": "Test User", "email": "t@example.com", "phone": "+919999999999", "interests": ["ipo"], "whatsapp_ok": True}).json()  # noqa: E501
        assert w["ok"] and w["position"] >= 1 and c.get("/waitlist/stats").json()["total"] >= 1
        a = c.post("/alerts", json={"contact": "+919999999999", "symbol": "HDFCBANK", "kind": "price_move", "value": 0.0001}).json()
        assert a["ok"] and len(c.get("/alerts?contact=%2B919999999999").json()) >= 1
        assert c.get("/alerts/channel").json()["channel"] in ("dry-run", "whatsapp", "telegram")
        fired = c.post("/alerts/run").json()
        assert any(f["symbol"] == "HDFCBANK" for f in fired) and c.get("/alerts/log").json()[0]["sent"] is False
        assert c.delete("/alerts/" + a["rule"]["id"]).json()["ok"]
        lim = c.get("/limits").json()
        assert lim["margin_cap"] > 0 and "max_open_structures" in lim
        an = c.get("/analysis").text
        assert "TradingView" not in an and "addAreaSeries" in an and 'id="pane-overview"' in an and 'id="lvBody"' in an
        assert c.get("/chart", follow_redirects=False).status_code == 307 and "/analysis" in c.get("/chart", follow_redirects=False).headers["location"]  # noqa: E501
        bars = c.get("/markets/bars?symbol=NIFTY50&range=1d").json()
        assert bars["intraday"] and bars["interval"] == "5m" and len(bars["bars"]) > 20 and {"open", "high", "low", "close", "volume"} <= set(bars["bars"][0])  # noqa: E501
        assert c.get("/markets/radar?index=BANKNIFTY&days=3&mode=long").json()["mode"] == "long"
        feed = c.get("/news/feed?impact=good&limit=5").json()
        assert "counts" in feed and feed["analyzer"].startswith("lexicon")
        chat = c.post("/chat", json={"question": "what does the council say about HDFC Bank for the week?"}).json()
        assert chat["symbol"] == "HDFCBANK" and chat["horizon"] == "1w" and "council says" in chat["answer"]
        ipo = c.get("/ipo").text
        assert 'id="body"' in ipo and 'class="pills"' in ipo and 'href="/ipo" aria-current="page"' in ipo and 'id="perfBody"' in ipo
        det = c.get("/ipo/meridian").text
        assert 'id="timeline"' in det and 'id="agent"' in det and 'id="fin"' in det
        lst = c.get("/markets/ipo").json()
        assert lst["stats"]["open"] >= 0 and {"slug", "status", "min_investment"} <= set(lst["entries"][0])
        d = c.get("/markets/ipo/" + lst["entries"][0]["slug"]).json()
        assert d["agent"]["model"] == "rules v0" and len(d["agent"]["checks"]) == 5 and len(d["timeline"]) == 6
        assert c.get("/markets/ipo/nope").status_code == 404
        perf = c.get("/markets/ipo-performance").json()
        assert perf["summary"]["count"] == len(perf["rows"]) and "avg_listing_gain" in perf["summary"]
        assert 'href="/ipo">IPO</a>' in home and 'href="/markets"' not in home
        desk = c.get("/desk").text
        assert 'id="flow"' in desk and "/static/design.css" in desk and "wlPane" not in desk
        sn = c.get("/sniper").text
        assert 'id="stepper"' in sn and 'id="targets"' in sn and 'id="pipe"' in sn and 'id="oc"' in sn
        cn = c.get("/markets/council?symbol=HDFCBANK&horizon=1h").json()
        assert len(cn["agents"]) == 10 and cn["verdict"]["stance"] in ("buy", "hold", "sell")
        mk = c.get("/markets").text
        assert "DDAI.radar(" in mk and "DDAI.ranking(" in mk and "/static/ai.css" in mk and "wlPane" not in mk
        assert 'data-ix="SENSEX"' in home and "limit=10" in home and 'data-ix=""' not in home
        assert 'data-view="overview"' in mk and "/static/nav.js" in mk and "maBtn" not in mk and 'id="ovInd"' in mk
        assert len(c.get("/markets/indicators").json()) == 18
        for path in ("/static/ai.js", "/static/ai.css", "/static/design.css", "/static/nav.js", "/static/watchlist.js", "/static/watchlist.css"):  # noqa: E501
            assert c.get(path).status_code == 200, path
        src = c.get("/markets/source").json()
        assert src["name"] == "synthetic" and src["history"] == "synthetic"
        ai = c.get("/markets/ai?index=BANKNIFTY&limit=3").json()
        assert ai["count"] == 12 and len(ai["entries"]) == 3
        rd = c.get("/markets/radar?index=BANKNIFTY&days=3").json()
        assert len(rd["frames"]) == 3
