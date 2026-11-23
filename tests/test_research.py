"""Research teams: the task graph, the risk maths, a full Investment Committee run and its routes (synthetic data, no network)."""
import time

from deltadesk.markets.llm import LLM, LLMError
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


class _FakeLLM:
    """A scripted tool-calling model: each agent calls tools on its first turn and answers with its judgement on the next."""
    provider, model, available, supports_tools = "fake", "m", True, True
    PLAN = {"Bull-side": (["get_market_data", "nope"], '**Bull thesis bullets**\n- Price above average\n```json\n{"points": [{"text": "Momentum +9 %", "weight": 2}]}\n```'),  # noqa: E501
            "Bear-side": (["risk_metrics"], '**Bear risk bullets**\n- Rich\n```json\n{"points": [{"text": "P/E 40", "weight": 1}]}\n```'),
            "Chief Risk": (["peer_comparison"], '**Risk review conclusion**\n- Oppose\n```json\n{"stance": "oppose"}\n```'),
            "Portfolio": None}

    def label(self):
        return "fake · m"

    def chat(self, system, messages, max_tokens=700, temperature=0.2):
        raise LLMError("fake 500: down")

    def chat_tools(self, messages, tools, max_tokens=900, temperature=0.2, choice="auto"):
        role = next(k for k in self.PLAN if k in messages[0]["content"])
        if role == "Portfolio":
            raise LLMError("fake 500: down")
        names, final = self.PLAN[role]
        if not any(m["role"] == "tool" for m in messages):
            return {"content": None, "tool_calls": [{"id": f"c{i}", "function": {"name": n, "arguments": "{}"}} for i, n in enumerate(names)]}  # noqa: E501
        return {"content": final, "tool_calls": []}


def test_agentic_run_model_judges_rules_guard(tmp_path):
    run = Research(MarketsService(), _FakeLLM(), tmp_path / "r.json").start("HDFCBANK", wait=True)
    by = {a["id"]: a for a in run["agents"]}
    assert run["status"] == "completed" and run["agentic"] and [by[k]["mode"] for k in by] == ["model", "model", "model", "rules"]
    assert [s["tool"] for s in by["bull_advocate"]["steps"]] == ["get_market_data"]            # only what the model asked for
    assert by["bull_advocate"]["output"] == "1 bull points · score 2" and "```" not in by["bull_advocate"]["report"]
    assert by["risk_officer"]["output"].startswith("oppose · cap 0.0 %")                       # the model's stance, the desk's sizing
    assert "rules used" in by["portfolio_manager"]["note"] and by["portfolio_manager"]["report"].startswith("**PM decision statement**")
    assert run["decision"]["action"] == "avoid" and run["decision"]["size_pct"] == 0.0
