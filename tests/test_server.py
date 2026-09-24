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
    from deltadesk.markets.watchlist import Watchlist as WL
    m = MarketsService(watchlist=WL(d / "watch.json"))
    from deltadesk.server.traffic import Traffic
    return TestClient(create_app(Pipeline(s, SyntheticFeed(s, speed=0.0)), cycles=1, markets=m, waitlist=Waitlist(d / "wl.jsonl"),
                                 alerts=Alerts(m, notifier=Notifier(), path=d / "a.json", log_path=d / "log.jsonl"), alert_interval=3600,
                                 traffic_log_store=Traffic(d / "traffic.jsonl", salt="test")))


def test_pages_and_assets():
    with _client() as c:
        home = c.get("/").text
        assert "LLM agents" in home and 'id="rdSvg"' in home and 'id="aiBody"' in home and "/static/js/ai.js" in home
        for path, marker in (("/news", 'id="flow"'), ("/analysis", "lightweight-charts"), ("/static/vendor/lightweight-charts.standalone.production.js", "createChart")):  # noqa: E501
            assert marker in c.get(path).text, path
        assert 'href="/news">News</a>' in home and 'href="/sniper">Sniper</a>' in home
        dom = c.get("/markets/domains").json()
        assert dom["HDFCBANK"] == "hdfcbank.com" and len(dom) > 100
        assert c.get("/static/js/ui.js").status_code == 200 and "/static/js/ui.js" in home
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
        assert "TradingView" not in an and "addAreaSeries" in an and "/static/js/common.js" in an and 'id="pane-fundamental"' in an and 'id="pivBody"' in an  # noqa: E501
        assert c.get("/healthz").json()["ok"] is True
        assert c.get("/chart", follow_redirects=False).status_code == 307 and "/analysis" in c.get("/chart", follow_redirects=False).headers["location"]  # noqa: E501
        bars = c.get("/markets/bars?symbol=NIFTY50&range=1d").json()
        assert bars["intraday"] and bars["interval"] == "5m" and len(bars["bars"]) > 20 and {"open", "high", "low", "close", "volume"} <= set(bars["bars"][0])  # noqa: E501
        assert c.get("/markets/radar?index=BANKNIFTY&days=3&mode=long").json()["mode"] == "long"
        feed = c.get("/news/feed?impact=good&limit=5").json()
        assert "counts" in feed and feed["analyzer"].startswith("lexicon")
        chat = c.post("/chat", json={"question": "what does the council say about HDFC Bank for the week?"}).json()
        assert chat["symbol"] == "HDFCBANK" and chat["horizon"] == "1w" and "council says" in chat["answer"]
        assert c.get("/ipo").headers["cache-control"] == "no-cache" and "max-age" in c.get("/static/js/nav.js").headers["cache-control"]
        import os as _os
        _os.environ["DD_ADMIN_TOKEN"] = "t0k"
        assert c.get("/admin/traffic").status_code == 401
        tr = c.get("/admin/traffic?token=t0k").json()
        assert tr["views"] >= 3 and tr["visitors"] >= 1 and any(p["path"] == "/" for p in tr["pages"]) and tr["today"]["views"] == tr["views"]  # noqa: E501
        navjs = c.get("/static/js/nav.js").text
        assert "ddPalette" in navjs and "ddBottom" in navjs and "D.toast" in c.get("/static/js/common.js").text
        assert 'id="wlAdd"' in c.get("/analysis").text and "[01]" not in c.get("/").text
        hm = c.get("/heatmap").text
        assert 'id="tm"' in hm and 'href="/heatmap" aria-current="page"' in hm
        fu = c.get("/markets/fundamentals/RELIANCE").json()
        assert fu["symbol"] == "RELIANCE" and "error" in fu          # no provider in tests: explains itself instead of failing
        an = c.get("/analysis").text
        assert 'id="pane-fundamental"' in an and 'id="pane-technical"' in an and 'data-t="fundamental"' in an
        ta = c.get("/markets/technicals/HDFCBANK?tf=daily").json()
        assert ta["summary"]["overall"] in ("Strong buy", "Buy", "Neutral", "Sell", "Strong sell") and len(ta["indicators"]) == 12 and len(ta["strip"]) == 5  # noqa: E501
        assert ta["pivots"]["methods"][0]["name"] == "Classic" and ta["moving_averages"][-1]["period"] == 200
        pe = c.get("/markets/peers/HDFCBANK").json()
        assert pe["sector"] == "Financials" and pe["rows"][0]["self"] and len(pe["rows"]) > 3
        gl = c.get("/global").text
        assert 'id="map"' in gl and 'id="regions"' in gl and 'href="/global" aria-current="page"' in gl
        g = c.get("/markets/global").json()
        assert [r["code"] for r in g["regions"]][:2] == ["world", "us"] and any(m["key"] == "HSI" and m["region"] == "cn" for m in g["markers"])  # noqa: E501
        assert g["sections"][0]["name"] == "Index futures" and g["markers"][0]["quote"] is not None
        for page in ("/", "/news", "/ipo", "/forex", "/desk", "/sniper", "/watchlist", "/analysis", "/beta", "/legal", "/global", "/heatmap"):  # noqa: E501
            body = c.get(page).text
            for h in ("/watchlist", "/heatmap", "/news", "/ipo", "/forex", "/global", "/investors", "/desk", "/sniper"):
                assert 'href="' + h + '"' in body, (page, h)
        wl = c.get("/watchlist").text
        assert 'id="preset"' in wl and 'href="/watchlist" aria-current="page"' in wl and 'href="/watchlist">Watchlist</a>' in home
        assert c.get("/markets/watchlist/presets").json()[0]["code"] == "NIFTY50"
        iv = c.get("/markets/investors").json()
        assert iv["count"] >= 6 and iv["investors"][0]["holdings"] and "summary" in iv["investors"][0] and iv["investors"][0]["seed"]
        assert 'id="grid"' in c.get("/investors").text and 'href="/investors">Investors</a>' in home
        st = c.get("/markets/watchlist/stats?symbols=HDFCBANK,RELIANCE").json()
        assert {"ret_1w", "ret_1m", "hi_52w", "lo_52w"} <= set(st["HDFCBANK"]) and st["HDFCBANK"]["hi_52w"] >= st["HDFCBANK"]["lo_52w"]
        assert c.get("/agent/model").json()["available"] is False
        ag = c.post("/agent/chat", json={"symbol": "HDFCBANK", "mode": "technical", "messages": [{"role": "user", "content": "What is the trend right now?"}]}).json()  # noqa: E501
        assert ag["model"] == "rules v0" and "Daily read" in ag["reply"] and ag["reply"].strip().endswith("Not investment advice.") and len(ag["suggestions"]) == 4  # noqa: E501
        af = c.post("/agent/chat", json={"symbol": "HDFCBANK", "mode": "fundamental", "messages": [{"role": "user", "content": "Is it expensive?"}]}).json()  # noqa: E501
        assert af["mode"] == "fundamental" and "HDFC Bank" in af["reply"]
        wl2 = c.get("/watchlist").text
        assert 'id="chat"' in wl2 and 'data-mode="technical"' in wl2 and 'id="pager"' in wl2
        pl = c.post("/markets/watchlist/preset/BANKNIFTY").json()
        assert pl["loaded"] == "NIFTY BANK" and len(pl["lists"]["NIFTY BANK"]) > 5 and pl["max_symbols"] == 50
        assert c.post("/markets/watchlist/preset/NOPE").status_code == 409
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
        assert 'id="flow"' in desk and "/static/css/design.css" in desk and "wlPane" not in desk
        sn = c.get("/sniper").text
        assert 'id="stepper"' in sn and 'id="targets"' in sn and 'id="pipe"' in sn and 'id="oc"' in sn
        cn = c.get("/markets/council?symbol=HDFCBANK&horizon=1h").json()
        assert len(cn["agents"]) == 10 and cn["verdict"]["stance"] in ("buy", "hold", "sell")
        assert 'data-ix="SENSEX"' in home and "limit=10" in home and 'data-ix=""' not in home
        assert len(c.get("/markets/indicators").json()) == 18
        for path in ("/static/js/ai.js", "/static/css/ai.css", "/static/css/design.css", "/static/js/nav.js", "/static/js/common.js", "/static/js/ui.js"):  # noqa: E501
            assert c.get(path).status_code == 200, path
        src = c.get("/markets/source").json()
        assert src["name"] == "synthetic" and src["history"] == "synthetic"
        ai = c.get("/markets/ai?index=BANKNIFTY&limit=3").json()
        assert ai["count"] == 12 and len(ai["entries"]) == 3
        rd = c.get("/markets/radar?index=BANKNIFTY&days=3").json()
        assert len(rd["frames"]) == 3
