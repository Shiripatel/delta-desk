import os

from deltadesk.markets import agent_chat
from deltadesk.markets.llm import LLM


def test_llm_picks_nothing_without_keys(monkeypatch):
    for k in ("GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "DD_LLM"):
        monkeypatch.delenv(k, raising=False)
    llm = LLM()
    assert not llm.available and llm.provider == "none" and "rules" in llm.label()
    monkeypatch.setenv("GROQ_API_KEY", "x")
    assert LLM().provider == "groq" and LLM("gemini").provider == "none" and LLM("none").provider == "none"
    monkeypatch.setenv("GEMINI_API_KEY", "y")
    assert LLM("gemini").model.startswith("gemini")


def test_rules_answer_reads_the_context():
    ctx = {"symbol": "TESTCO", "name": "Test Co", "quote": {"ltp": 100.0, "change_pct": 1.5},
           "snapshot": {"pe": 20.0, "pb": 3.0, "ev_ebitda": 12.0, "market_cap_cr": 5000, "roe": 18.0, "roce": 22.0, "debt_equity": 0.3, "interest_coverage": 8.0,  # noqa: E501
                        "revenue_cagr_3y": 12.0, "eps_cagr_3y": 15.0, "revenue_ttm_growth": 10.0, "net_income_ttm_growth": 9.0, "fcf_ttm_cr": 300},  # noqa: E501
           "pros": ["Almost debt free"], "cons": ["Slow growth"], "annual": [], "peers": [{"symbol": "TESTCO", "pe": 20.0}, {"symbol": "A", "pe": 30.0}, {"symbol": "B", "pe": 40.0}],  # noqa: E501
           "council": {"stance": "hold", "confidence": 0.6}, "headlines": []}
    a = agent_chat.rules_answer(ctx, "fundamental", "is it expensive?")
    assert "P/E 20.0" in a and "median P/E 35.0" in a and "below" in a
    b = agent_chat.rules_answer(ctx, "fundamental", "what are the risks")
    assert "Slow growth" in b
    tctx = {"symbol": "TESTCO", "name": "Test Co", "quote": {"ltp": 100.0, "change_pct": -0.5},
            "technicals": {"summary": {"overall": "Sell", "moving_averages": {"verdict": "Sell", "buy": 2, "sell": 10}, "indicators": {"verdict": "Neutral"}},  # noqa: E501
                           "timeframes": [{"tf": "Daily", "verdict": "Sell"}], "indicators": [{"name": "RSI (14)", "value": 28.0, "action": "Oversold"}],  # noqa: E501
                           "moving_averages": [], "pivots_classic": {"S2": 90, "S1": 95, "P": 100, "R1": 105, "R2": 110}}, "ai_score": None, "council": None, "headlines": []}  # noqa: E501
    c = agent_chat.rules_answer(tctx, "technical", "is it oversold?")
    assert "RSI (14) 28.00 (Oversold)" in c
    d = agent_chat.rules_answer(tctx, "technical", "which levels matter")
    assert "S1 95.00" in d and "R1 105.00" in d
    assert agent_chat.find_mode("what is the trend") == "technical" and agent_chat.find_mode("is it cheap") == "fundamental"
    assert os.environ.get("DD_LLM", "auto") in ("auto", "none", "groq", "gemini", "openrouter", "ollama")
