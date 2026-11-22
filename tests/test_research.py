"""Research teams: the task graph, the risk maths, a full Investment Committee run and its routes (synthetic data, no network)."""
import time

from deltadesk.markets.llm import LLM
from deltadesk.markets.research import PRESETS, Research, layers, risk_numbers
from deltadesk.markets.service import MarketsService
from tests.test_server import _client


def test_layers_and_risk_numbers():
    rounds = layers(PRESETS["investment_committee"]["tasks"])
    assert [[t["id"] for t in r] for r in rounds] == [["task-bull", "task-bear"], ["task-risk"], ["task-decision"]]
    closes = [100 * (1 + 0.01 * ((i * 7) % 5 - 2)) for i in range(120)]
    r = risk_numbers(closes)
    assert r["available"] and r["n"] == 119 and r["cvar95_1d_pct"] >= r["var95_1d_pct"] > 0 and r["max_drawdown_pct"] <= 0
    assert risk_numbers(closes[:10])["available"] is False


def test_committee_run(tmp_path):
    rs = Research(MarketsService(), LLM("none"), tmp_path / "research.json")
    assert rs.resolve("what about HDFC Bank?") == "HDFCBANK" and rs.resolve("zzzz qqqq") is None
    run = rs.start("HDFCBANK", wait=True)
    assert run["status"] == "completed" and run["done"] == 4 and run["round"] == 3 and run["target"] == "HDFCBANK"
    by = {a["id"]: a for a in run["agents"]}
    assert all(a["status"] == "done" and a["report"] and a["steps"] for a in run["agents"])
    assert [s["tool"] for s in by["bear_advocate"]["steps"]][-1] == "risk_metrics" and "**Risk metrics**" in by["bear_advocate"]["report"]
    d = run["decision"]
    assert d["action"] in ("long", "wait", "avoid") and 35 <= d["confidence"] <= 85 and d["stop_pct"] <= -5 and d["target_pct"] == round(-2 * d["stop_pct"], 1)  # noqa: E501
    assert (d["size_pct"] > 0) == (d["action"] == "long") and d["size_pct"] <= 10
    assert run["report"].startswith("## Portfolio Manager") and run["report"].endswith("Not investment advice.")
    assert rs.start("hdfcbank")["id"] == run["id"]                      # a repeat inside ten minutes reuses the run
    again = Research(MarketsService(), LLM("none"), tmp_path / "research.json")   # finished runs survive a restart
    assert again.get(run["id"])["decision"] == d and again.history()[0]["action"] == d["action"]


def test_research_routes():
    with _client() as c:
        page = c.get("/research").text
        assert 'id="agents"' in page and 'href="/research" aria-current="page"' in page and "/research/run" in page
        p = c.get("/research/presets").json()
        assert p["presets"][0]["name"] == "investment_committee" and p["presets"][0]["rounds"] == 3 and len(p["examples"]) == 3 and p["llm"] is False  # noqa: E501
        assert c.post("/research/run", json={"query": ""}).status_code == 400
        assert c.post("/research/run", json={"query": "RELIANCE", "preset": "nope"}).status_code == 400
        run = c.post("/research/run", json={"query": "Reliance"}).json()
        assert run["target"] == "RELIANCE" and len(run["agents"]) == 4
        for _ in range(100):
            run = c.get("/research/run/" + run["id"]).json()
            if run["status"] in ("completed", "failed"):
                break
            time.sleep(0.1)
        assert run["status"] == "completed" and run["decision"]["risk_stance"] in ("support", "conditional support", "oppose")
        assert c.get("/research/runs").json()[0]["id"] == run["id"] and c.get("/research/run/nope").status_code == 404
