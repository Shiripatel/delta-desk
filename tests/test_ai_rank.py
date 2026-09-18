import math

from deltadesk.markets.ai_rank import AiRanker, SyntheticHistory, features, score, win_rate


def _trend(n=66, daily=0.004, start=100.0):
    return [start * math.exp(daily * i) for i in range(n)]


def test_features_and_score_on_clean_trends():
    up = features(_trend())
    assert up and up["ret_3m"] > 0.2 and up["r2"] > 0.99 and up["max_dd"] == 0
    ai, fc, risk = score(up)
    assert ai >= 9 and fc > 10 and risk >= 9
    dn = features(_trend(daily=-0.004))
    ai2, fc2, _ = score(dn)
    assert ai2 <= 2 and fc2 < -5
    assert features([100.0] * 10) is None


def test_win_rate_is_high_on_a_clean_trend_and_none_when_short():
    assert win_rate(_trend()) == 100.0
    assert win_rate(_trend(n=30)) is None


def test_ranker_on_synthetic_history():
    r = AiRanker(SyntheticHistory()).rank("BANKNIFTY", limit=5)
    assert r["count"] == 12 and len(r["entries"]) == 5 and r["source"] == "synthetic"
    e = r["entries"][0]
    assert e["rank"] == 1 and 1 <= e["score"] <= 10 and 1 <= e["risk"] <= 10 and len(e["spark"]) >= 20
    scores = [x["score"] for x in r["entries"]]
    assert scores == sorted(scores, reverse=True)
    r_all = AiRanker(SyntheticHistory()).rank(None, limit=1000)
    assert r_all["count"] > 100


def test_radar_frames_on_synthetic_history():
    r = AiRanker(SyntheticHistory()).radar("BANKNIFTY", days=5)
    assert len(r["frames"]) == 5 and r["sectors"] == ["Financials"]
    last = r["frames"][-1]
    assert len(last["points"]) == 12 and last["asof"] >= r["frames"][0]["asof"]
    p = last["points"][0]
    assert {"symbol", "score", "risk", "forecast_3m", "weight", "ret_1d"} <= set(p)
