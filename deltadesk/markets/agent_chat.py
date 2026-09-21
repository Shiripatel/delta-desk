"""Fundamental agent and Technical agent chat: grounded answers about one stock.

The agent never sees the open web. It gets a DATA block built from the desk's own read model (quote, filings,
ratios, pros and cons, peers, technicals, council votes, headlines) and answers from that. With a language
model configured (see llm.py) the answer is free-form; without one, the same data is composed by rules.
Either way the reply ends with the disclaimer and is explanation, not advice.
"""
from __future__ import annotations

import json
import re

from deltadesk.markets.llm import LLM, LLMError

MODES = {"fundamental": "Fundamental agent", "technical": "Technical agent"}
SYSTEM = ("You are Delta Desk's {label} for Indian markets, talking to a retail investor. Answer ONLY from the DATA block; quote the numbers you "  # noqa: E501
          "use; if something is not in the data say you do not have it. Plain English, short paragraphs or bullets, under 160 words. Explain what "  # noqa: E501
          "the numbers show and what would change the read. Never tell the user to buy, sell or hold, and never predict prices. End with: "
          "Not investment advice.")
SUGGEST = {"fundamental": ["Is it expensive against its peers?", "How fast is it growing?", "How strong is the balance sheet?", "What are the risks in the filings?"],  # noqa: E501
           "technical": ["What is the trend right now?", "Is it overbought or oversold?", "Which levels matter today?", "Do the timeframes agree?"]}  # noqa: E501


class AgentChat:
    def __init__(self, markets, llm: LLM | None = None) -> None:
        self.m = markets
        self.llm = llm or LLM()

    # ---- context ---------------------------------------------------------------------------------
    def context(self, symbol: str, mode: str) -> dict:
        m = self.m
        sym = symbol.upper()
        name, kind, sector = m._name(sym)
        q = m.quotes.quotes([sym]).get(sym)
        ctx: dict = {"symbol": sym, "name": name, "kind": kind, "sector": sector,
                     "quote": {"ltp": q.ltp, "change_pct": q.change_pct, "day_high": q.high, "day_low": q.low} if q else None}
        try:
            heads = m.news.feed(symbols=[sym], limit=4)["entries"]
            ctx["headlines"] = [{"title": h["title"], "impact": h["impact"], "source": h["source"]} for h in heads]
        except Exception:  # noqa: BLE001
            ctx["headlines"] = []
        if mode == "fundamental":
            f = m.fundamentals(sym) if hasattr(m, "fundamentals") else None
            if f and not f.get("error"):
                ad = f["periods"]["annual"][-4:]
                ctx["snapshot"] = f["snapshot"]
                ctx["pros"], ctx["cons"] = f.get("pros", []), f.get("cons", [])
                ctx["annual"] = [{"fy": dt, "revenue_cr": f["statements"]["annual"]["TotalRevenue"].get(dt), "net_income_cr": f["statements"]["annual"]["NetIncome"].get(dt),  # noqa: E501
                                  "eps": f["statements"]["annual"]["DilutedEPS"].get(dt), "roe": f["ratios"]["annual"]["roe"].get(dt)} for dt in ad]  # noqa: E501
            else:
                ctx["snapshot"] = None
                ctx["fundamentals_note"] = (f or {}).get("error") or "no filings for this instrument (index, FX or commodity)"
            try:
                pe = m.peers(sym)
                ctx["peers"] = [{"symbol": r["symbol"], "pe": r["pe"], "roe": r["roe"], "market_cap_cr": r["market_cap_cr"]} for r in pe["rows"][:6]]  # noqa: E501
            except Exception:  # noqa: BLE001
                ctx["peers"] = []
            try:
                c = m.council_run(sym, "1y")
                ctx["council"] = {"stance": c["verdict"]["stance"], "confidence": c["verdict"]["confidence"],
                                  "fundamental_agents": [{"name": a["name"], "reading": a["reading"]} for a in c["agents"] if a["group"] == "fundamental" and a["available"]]}  # noqa: E501
            except Exception:  # noqa: BLE001
                ctx["council"] = None
        else:
            try:
                t = m.technicals(sym, "daily")
                ctx["technicals"] = {"summary": t.get("summary"), "timeframes": [{"tf": s["label"], "verdict": s["verdict"]} for s in t.get("strip", [])],  # noqa: E501
                                     "indicators": [{"name": i["name"], "value": i["value"], "action": i["action"]} for i in t.get("indicators", [])],  # noqa: E501
                                     "moving_averages": [{"period": x["period"], "sma": x["sma"], "action": x["sma_action"]} for x in t.get("moving_averages", [])],  # noqa: E501
                                     "pivots_classic": next((p for p in t.get("pivots", {}).get("methods", []) if p["name"] == "Classic"), None), "bars": t.get("bars")}  # noqa: E501
            except Exception as exc:  # noqa: BLE001
                ctx["technicals"] = None
                ctx["technicals_note"] = str(exc)
            try:
                rows = m.ai_rank(None, 500, "short")["entries"]
                r = next((x for x in rows if x["symbol"] == sym), None)
                ctx["ai_score"] = {"score": r["score"], "forecast_3m": r["forecast_3m"], "win_rate": r["win_rate"], "ret_1m": r["ret_1m"], "ret_3m": r["ret_3m"]} if r else None  # noqa: E501
            except Exception:  # noqa: BLE001
                ctx["ai_score"] = None
            try:
                c = m.council_run(sym, "1d")
                ctx["council"] = {"stance": c["verdict"]["stance"], "confidence": c["verdict"]["confidence"],
                                  "technical_agents": [{"name": a["name"], "reading": a["reading"]} for a in c["agents"] if a["group"] == "technical" and a["available"]]}  # noqa: E501
            except Exception:  # noqa: BLE001
                ctx["council"] = None
        return ctx

    # ---- reply ------------------------------------------------------------------------------------
    def reply(self, symbol: str, mode: str, messages: list[dict]) -> dict:
        mode = mode if mode in MODES else "fundamental"
        ctx = self.context(symbol, mode)
        history = [{"role": m["role"], "content": str(m.get("content", ""))[:2000]} for m in messages if m.get("role") in ("user", "assistant")][-8:]  # noqa: E501
        question = history[-1]["content"] if history and history[-1]["role"] == "user" else ""
        text, model, grounded = "", self.llm.label(), True
        if self.llm.available and question:
            system = SYSTEM.format(label=MODES[mode]) + "\n\nDATA:\n" + json.dumps(ctx, ensure_ascii=False, default=str)
            try:
                text = self.llm.chat(system, history).strip()
            except LLMError as exc:
                text = rules_answer(ctx, mode, question) + f"\n\n(language model unavailable: {exc}; this answer was composed by rules)"
                model = "rules v0 (fallback)"
        else:
            text = rules_answer(ctx, mode, question)
            model = "rules v0"
        if "not investment advice" not in text.lower():
            text += "\n\nNot investment advice."
        return {"symbol": ctx["symbol"], "name": ctx["name"], "mode": mode, "reply": text, "model": model, "grounded": grounded,
                "suggestions": SUGGEST[mode], "context": ctx}


# ---- rules fallback: the same data, composed without a model ----------------------------------------
def _n(v, d=1, suffix=""):
    return "—" if v is None else f"{v:,.{d}f}{suffix}"


def rules_answer(ctx: dict, mode: str, question: str) -> str:
    q = (question or "").lower()
    name, sym = ctx["name"], ctx["symbol"]
    qt = ctx.get("quote") or {}
    head = f"{name} ({sym}) · ₹{_n(qt.get('ltp'), 2)} · {_n(qt.get('change_pct'), 2, ' %')} today."
    parts = [head]
    if mode == "fundamental":
        s = ctx.get("snapshot")
        if not s:
            parts.append(ctx.get("fundamentals_note", "No filings available."))
            return "\n".join(parts)
        val = f"Valuation: P/E {_n(s.get('pe'))}, P/B {_n(s.get('pb'), 2)}, EV/EBITDA {_n(s.get('ev_ebitda'))}, market cap ₹{_n(s.get('market_cap_cr'), 0)} cr."  # noqa: E501
        qual = f"Quality: ROE {_n(s.get('roe'), 1, ' %')}, ROCE {_n(s.get('roce'), 1, ' %')}, debt to equity {_n(s.get('debt_equity'), 2)}, interest coverage {_n(s.get('interest_coverage'))}×."  # noqa: E501
        gro = f"Growth: revenue {_n(s.get('revenue_cagr_3y'), 1, ' %')} a year and EPS {_n(s.get('eps_cagr_3y'), 1, ' %')} a year over three years; TTM revenue {_n(s.get('revenue_ttm_growth'), 1, ' %')}, TTM profit {_n(s.get('net_income_ttm_growth'), 1, ' %')}."  # noqa: E501
        peers = ctx.get("peers") or []
        pes = [p["pe"] for p in peers[1:] if p.get("pe")]
        peer_line = ""
        if pes and s.get("pe"):
            srt = sorted(pes)
            med = srt[len(srt) // 2] if len(srt) % 2 else (srt[len(srt) // 2 - 1] + srt[len(srt) // 2]) / 2
            peer_line = f"Peers: median P/E {_n(med)} across {len(pes)} sector peers, so {sym} trades {'above' if s['pe'] > med else 'below'} the group."  # noqa: E501
        if any(w in q for w in ("expensive", "cheap", "valuation", "p/e", "pe ", "price")):
            parts += [val, peer_line]
        elif any(w in q for w in ("grow", "growth", "revenue", "sales", "profit")):
            parts += [gro, "Last years: " + "; ".join(f"{a['fy'][:4]} revenue ₹{_n(a['revenue_cr'], 0)} cr, profit ₹{_n(a['net_income_cr'], 0)} cr" for a in ctx.get("annual", [])) + "."]  # noqa: E501
        elif any(w in q for w in ("debt", "balance", "leverage", "cash", "strong")):
            parts += [qual, f"Free cash flow (TTM) ₹{_n(s.get('fcf_ttm_cr'), 0)} cr."]
        elif any(w in q for w in ("risk", "con", "worry", "bad", "weak")):
            parts += ["Cons from the filings: " + ("; ".join(ctx.get("cons") or ["nothing stood out"])) + "."]
        else:
            parts += [val, qual, gro, peer_line]
            if ctx.get("pros"):
                parts.append("Pros: " + "; ".join(ctx["pros"][:3]) + ".")
            if ctx.get("cons"):
                parts.append("Cons: " + "; ".join(ctx["cons"][:3]) + ".")
        c = ctx.get("council")
        if c:
            parts.append(f"Council at one year: {c['stance']} ({c['confidence'] * 100:.0f} % confidence).")
    else:
        t = ctx.get("technicals")
        if not t:
            parts.append(ctx.get("technicals_note", "Technicals unavailable."))
            return "\n".join(parts)
        sm = t["summary"] or {}
        overall = f"Daily read: {sm.get('overall', '—')}; moving averages {sm.get('moving_averages', {}).get('verdict', '—')} ({sm.get('moving_averages', {}).get('buy', 0)} buy / {sm.get('moving_averages', {}).get('sell', 0)} sell), indicators {sm.get('indicators', {}).get('verdict', '—')}."  # noqa: E501
        tfs = "Timeframes: " + ", ".join(f"{x['tf']} {x['verdict']}" for x in t.get("timeframes", [])) + "."
        ind = {i["name"]: i for i in t.get("indicators", [])}

        def rd(nm):
            i = ind.get(nm)
            return f"{nm} {_n(i['value'], 2)} ({i['action']})" if i else nm
        piv = t.get("pivots_classic") or {}
        lv = f"Classic pivots from the previous session: S2 {_n(piv.get('S2'), 2)}, S1 {_n(piv.get('S1'), 2)}, pivot {_n(piv.get('P'), 2)}, R1 {_n(piv.get('R1'), 2)}, R2 {_n(piv.get('R2'), 2)}."  # noqa: E501
        if any(w in q for w in ("overbought", "oversold", "rsi", "stoch")):
            parts += [rd("RSI (14)") + ", " + rd("STOCH (9,6)") + ", " + rd("Williams %R") + "."]
        elif any(w in q for w in ("level", "support", "resistance", "pivot")):
            parts += [lv]
        elif any(w in q for w in ("trend", "average", "ma ", "direction")):
            parts += [overall, rd("ADX (14)") + ", " + rd("MACD (12,26)") + "."]
        elif any(w in q for w in ("timeframe", "agree", "weekly", "monthly", "hour")):
            parts += [tfs]
        else:
            parts += [overall, tfs, rd("RSI (14)") + ", " + rd("MACD (12,26)") + ", " + rd("ADX (14)") + ".", lv]
        ai = ctx.get("ai_score")
        if ai:
            parts.append(f"AI score {ai['score']}/10 (short term), 1-month {_n(ai['ret_1m'], 1, ' %')}, 3-month {_n(ai['ret_3m'], 1, ' %')}, past win rate {_n(ai['win_rate'], 0, ' %')}.")  # noqa: E501
        c = ctx.get("council")
        if c:
            parts.append(f"Council at one day: {c['stance']} ({c['confidence'] * 100:.0f} % confidence).")
    heads = ctx.get("headlines") or []
    if heads and any(w in q for w in ("news", "headline", "why")):
        parts.append("Wire: " + "; ".join(f"{h['title']} ({h['impact']})" for h in heads[:3]) + ".")
    return "\n".join(p for p in parts if p)


def find_mode(text: str) -> str:
    return "technical" if re.search(r"trend|rsi|macd|level|support|resistance|overbought|oversold|chart|pivot|moving average", (text or "").lower()) else "fundamental"  # noqa: E501
