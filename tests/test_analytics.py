from deltadesk.server.analytics import Traffic


def test_traffic_log_and_summary(tmp_path):
    t = Traffic(tmp_path / "t.jsonl", salt="s")
    t.record("/", "1.2.3.4", "Mozilla/5.0 (iPhone)", "https://twitter.com/x")
    t.record("/", "1.2.3.4", "Mozilla/5.0 (iPhone)", "")
    t.record("/ipo/meridian", "5.6.7.8", "Mozilla/5.0 (Windows)", "https://www.google.com/")
    t.record("/static/css/design.css", "5.6.7.8", "x", "")          # not a page: ignored
    t.record("/markets/ai", "5.6.7.8", "x", "")                      # api: ignored
    s = t.summary()
    assert s["views"] == 3 and s["visitors"] == 2 and s["pages"][0] == {"path": "/", "views": 2}
    assert {r["ref"] for r in s["referrers"]} == {"twitter.com", "direct", "www.google.com"}
    assert {d["ua"] for d in s["devices"]} == {"mobile", "desktop"} and s["daily"][0]["visitors"] == 2
    assert t.visitor("1.2.3.4", "ua") != Traffic(tmp_path / "u.jsonl", salt="other").visitor("1.2.3.4", "ua")
