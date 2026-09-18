"""Routes and static assets served by the app (synthetic feed, no network)."""
import warnings

from deltadesk.config import Settings
from deltadesk.feeds.synthetic import SyntheticFeed
from deltadesk.pipeline import Pipeline
from deltadesk.server.app import create_app


def _client():
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

    s = Settings(feed="synthetic", cycle_seconds=30, _env_file=None)
    return TestClient(create_app(Pipeline(s, SyntheticFeed(s, speed=0.0)), cycles=1))


def test_pages_and_assets():
    with _client() as c:
        home = c.get("/").text
        assert "AI RADAR" in home and 'id="rdSvg"' in home and 'id="aiBody"' in home and "/static/ai.js" in home
        desk = c.get("/desk").text
        assert "agent pipeline" in desk and 'id="wlPane"' in desk
        mk = c.get("/markets").text
        assert "DDAI.radar(" in mk and "DDAI.ranking(" in mk and "/static/ai.css" in mk
        for path in ("/static/ai.js", "/static/ai.css", "/static/watchlist.js", "/static/watchlist.css"):
            assert c.get(path).status_code == 200, path
        src = c.get("/markets/source").json()
        assert src["name"] == "synthetic" and src["history"] == "synthetic"
        ai = c.get("/markets/ai?index=BANKNIFTY&limit=3").json()
        assert ai["count"] == 12 and len(ai["entries"]) == 3
        rd = c.get("/markets/radar?index=BANKNIFTY&days=3").json()
        assert len(rd["frames"]) == 3
