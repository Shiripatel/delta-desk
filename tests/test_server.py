"""Routes and static assets served by the app (synthetic feed, no network)."""
import warnings

from deltadesk.config import Settings
from deltadesk.feeds.synthetic import SyntheticFeed
from deltadesk.pipeline import Pipeline
from deltadesk.server.app import create_app


def _client():
    warnings.simplefilter("ignore")
    import os
    import tempfile
    from pathlib import Path

    from fastapi.testclient import TestClient

    from deltadesk.beta import Alerts, Notifier, Waitlist

    d = Path(tempfile.mkdtemp())
    os.environ["DD_SNIPER_CFG"] = str(d / "sniper.json")      # the sniper desk config must not touch the repo's data/
    os.environ["DD_RESEARCH_STORE"] = str(d / "research.json")
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
        fav = c.get("/favicon.ico")
        assert fav.status_code == 200 and fav.headers["content-type"].startswith("image/svg") and 'rel="icon"' in home
        assert c.get("/chart", follow_redirects=False).status_code == 307 and "/analysis" in c.get("/chart", follow_redirects=False).headers["location"]  # noqa: E501
        bars = c.get("/markets/bars?symbol=NIFTY50&range=1d").json()
        assert bars["intraday"] and bars["interval"] == "5m" and len(bars["bars"]) > 20 and {"open", "high", "low", "close", "volume"} <= set(bars["bars"][0])  # noqa: E501
        assert c.get("/markets/radar?index=BANKNIFTY&days=3&mode=long").json()["mode"] == "long"
        feed = c.get("/news/feed?impact=good&limit=5").json()
        assert "counts" in feed and feed["analyzer"].startswith("lexicon")
        assert c.get("/news").headers["cache-control"] == "no-cache" and "max-age" in c.get("/static/js/nav.js").headers["cache-control"]
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
        for page in ("/", "/news", "/research", "/sniper", "/watchlist", "/analysis", "/beta", "/legal", "/heatmap"):
            body = c.get(page).text
            nav = body[body.index('<nav class="nav">'):body.index("</nav>")]
            for h in ("/", "/heatmap", "/news", "/research", "/sniper"):
                assert 'href="' + h + '"' in nav, (page, h)
            for h in ("/watchlist", "/desk", "/ipo", "/forex", "/global", "/investors"):   # parked, merged or deleted: out of the nav
                assert 'href="' + h + '"' not in nav, (page, h)
        wl = c.get("/watchlist").text
        assert 'id="preset"' in wl and 'href="/watchlist"' not in home   # parked: served by URL, no nav link
        assert c.get("/markets/watchlist/presets").json()[0]["code"] == "NIFTY50"
        st = c.get("/markets/watchlist/stats?symbols=HDFCBANK,RELIANCE").json()
        assert {"ret_1w", "ret_1m", "hi_52w", "lo_52w"} <= set(st["HDFCBANK"]) and st["HDFCBANK"]["hi_52w"] >= st["HDFCBANK"]["lo_52w"]
        assert c.get("/agent/model").json()["available"] is False
        ag = c.post("/agent/chat", json={"symbol": "HDFCBANK", "mode": "technical", "messages": [{"role": "user", "content": "What is the trend right now?"}]}).json()  # noqa: E501
        assert ag["model"] == "rules v0" and "Daily read" in ag["reply"] and "| Metric | Value | Read |" in ag["reply"] and ag["reply"].strip().endswith("Not investment advice.") and len(ag["suggestions"]) == 4  # noqa: E501
        af = c.post("/agent/chat", json={"symbol": "HDFCBANK", "mode": "fundamental", "messages": [{"role": "user", "content": "Is it expensive?"}]}).json()  # noqa: E501
        assert af["mode"] == "fundamental" and "HDFC Bank" in af["reply"]
        wl2 = c.get("/watchlist").text
        assert 'id="chat"' in wl2 and 'data-mode="technical"' in wl2 and 'id="pager"' in wl2
        pl = c.post("/markets/watchlist/preset/BANKNIFTY").json()
        assert pl["loaded"] == "NIFTY BANK" and len(pl["lists"]["NIFTY BANK"]) > 5 and pl["max_symbols"] == 50
        assert c.post("/markets/watchlist/preset/NOPE").status_code == 409
        assert c.get("/ipo").status_code == 404 and c.get("/markets/ipo").status_code == 404
        assert 'href="/markets"' not in home and "rdMovers" not in home and 'class="how"' not in home
        desk = c.get("/desk", follow_redirects=False)
        assert desk.status_code == 307 and desk.headers["location"] == "/research"
        sn = c.get("/sniper").text
        assert 'id="shelf"' in sn and 'id="gate"' in sn and 'id="order"' in sn and 'id="chart"' in sn and 'id="blotter"' in sn and 'id="kill"' not in sn and 'id="edges"' in sn  # noqa: E501
        cfg = c.get("/sniper/config").json()
        assert cfg["monitors"] == ["volume", "ma_vwap", "rsi", "trend"] and cfg["required"] is None and len(cfg["available"]) == 6
        assert {a["name"] for a in cfg["available"]} >= {"volume", "ma_vwap", "rsi", "trend", "options", "levels"}
        r = c.post("/sniper/config", json={"monitors": ["rsi", "trend", "options"], "required": 2})
        assert r.status_code == 200 and r.json()["monitors"] == ["rsi", "trend", "options"] and r.json()["required_effective"] == 2
        assert c.post("/sniper/config", json={"monitors": ["bogus"]}).status_code == 400
        assert c.post("/sniper/config", json={"monitors": [], "required": None}).status_code == 400
        assert c.post("/sniper/config", json={"monitors": ["volume", "ma_vwap", "rsi", "trend"]}).status_code == 200
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


def test_owner_lock():
    """DD_OWNER_TOKEN empty: every route open. Set: state-changing routes need the header, query or cookie; reads stay open."""
    import os

    with _client() as c:
        assert c.post("/kill").status_code == 200 and c.get("/healthz").json()["locked"] is False
        os.environ["DD_OWNER_TOKEN"] = "0wn3r-t0k3n"
        try:
            assert c.get("/healthz").json()["locked"] is True and c.get("/owner").json() == {"locked": True, "owner": False}
            locked = (("post", "/kill", None), ("post", "/sniper/config", {"monitors": ["rsi"]}), ("post", "/markets/watchlist/mine", None),
                      ("post", "/markets/watchlist/My%20watchlist/HDFCBANK", None),
                      ("delete", "/markets/watchlist/My%20watchlist/HDFCBANK", None),
                      ("post", "/markets/watchlist/preset/BANKNIFTY", None), ("post", "/alerts/run", None),
                      ("post", "/alerts", {"contact": "+911", "symbol": "HDFCBANK", "kind": "price_move", "value": 1}),
                      ("post", "/alerts/test", {"contact": "+911"}), ("post", "/markets/refresh-constituents", None),
                      ("post", "/decisions/nope/approve", None))
            for method, path, body in locked:
                r = getattr(c, method)(path, json=body) if body is not None else getattr(c, method)(path)
                assert r.status_code == 401 and "owner only" in r.json()["detail"], (method, path, r.status_code)
            # reads, the waitlist and the chat stay public
            assert c.get("/markets/watchlist").status_code == 200 and c.get("/sniper/config").status_code == 200
            assert c.post("/waitlist", json={"name": "Visitor", "email": "v@example.com"}).json()["ok"]
            # header and query forms
            assert c.post("/kill", headers={"X-Owner-Token": "0wn3r-t0k3n"}).status_code == 200
            assert c.post("/kill", headers={"X-Owner-Token": "wrong"}).status_code == 401
            assert c.post("/kill?token=0wn3r-t0k3n").status_code == 200
            # cookie form: /owner?token= sets it once, /owner/logout clears it, only same-site paths are redirect targets
            assert c.get("/owner?token=wrong").status_code == 401
            r = c.get("/owner?token=0wn3r-t0k3n&next=/sniper", follow_redirects=False)
            assert r.status_code == 303 and r.headers["location"] == "/sniper" and "dd_owner=" in r.headers["set-cookie"] and "HttpOnly" in r.headers["set-cookie"]  # noqa: E501
            assert c.get("/owner").json() == {"locked": True, "owner": True}
            assert c.post("/sniper/config", json={"monitors": ["rsi", "trend"], "required": None}).status_code == 200
            assert c.get("/owner?token=0wn3r-t0k3n&next=//evil.example", follow_redirects=False).headers["location"] == "/"
            assert c.get("/owner/logout", follow_redirects=False).status_code == 303
            assert c.post("/kill").status_code == 401 and c.get("/owner").json()["owner"] is False
        finally:
            del os.environ["DD_OWNER_TOKEN"]
        assert c.post("/kill").status_code == 200


def test_track_record_endpoint_and_home_section():
    with _client() as c:
        t = c.get("/markets/track?index=BANKNIFTY").json()
        assert t["index"] == "BANKNIFTY" and t["unit"] == "sessions" and t["horizons"] == [5, 20] and t["stocks"] == 12
        assert [z["zone"] for z in t["zones"]] == ["buy", "hold", "sell"] and t["windows"] == sum(z["n"] for z in t["zones"]) > 0
        assert set(t["base"]) == {"5", "20"} and "rate" in t["hit"]["20"] and t["headline"] and t["note"].endswith("Not investment advice.")
        assert c.get("/markets/track?index=BANKNIFTY&mode=long").json()["unit"] == "weeks"
        home = c.get("/").text
        assert 'id="trBody"' in home and 'id="trLine"' in home and "track record" in home
        assert "DDAI.track(" in home and "track:track" in c.get("/static/js/ai.js").text and ".zdot" in c.get("/static/css/ai.css").text
