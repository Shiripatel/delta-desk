"""Fundamental agent and Technical agent chat: grounded, structured answers about one stock.

The agent never sees the open web. It gets a DATA block built from the desk's own read model (quote, filings,
ratios, pros and cons, peers, technicals, council votes, headlines) and answers from that in a fixed shape:
one summary line, a small markdown table of the numbers that matter for the question, and two to four short
bullets. With a language model configured (see llm.py) the model writes it; without one, rules compose the
same shape from the same data. Either way it ends with the disclaimer and is explanation, not advice.
"""
from __future__ import annotations

import json
import re

from deltadesk.markets.llm import LLM, LLMError

MODES = {"fundamental": "Fundamental agent", "technical": "Technical agent"}
SYSTEM = (
    "You are Delta Desk's {label} for Indian markets, talking to a retail investor. Answer ONLY from the DATA block (JSON). "
    "Quote the numbers you use; if something is not in the data, say you do not have it. Never tell the user to buy, sell or hold, "
    "and never predict prices.\n\n"
    "FORMAT, exactly this, in markdown, no headings, no long paragraphs:\n"
    "1. One summary line, at most 25 words, that answers the question directly.\n"
    "2. A table with 4 to 8 rows of the numbers that matter for this question, columns: Metric | Value | Read. "
    "'Read' is two or three words (e.g. 'below peers', 'rising', 'thin'). Use ₹ crore for money, % for ratios that are percentages.\n"
    "3. Two to four bullets, each under 20 words, on what the numbers mean and what would change the read.\n"
    "4. The last line: Not investment advice.\n"
    "Keep the whole answer under 170 words outside the table."
)
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
                                  "eps": f["statements"]["annual"]["DilutedEPS"].get(dt), "roe": f["ratios"]["annual"]["roe"].get(dt),
                                  "debt_equity": f["ratios"]["annual"]["debt_equity"].get(dt)} for dt in ad]
            else:
                ctx["snapshot"] = None
                ctx["fundamentals_note"] = (f or {}).get("error") or "no filings for this instrument (index, FX or commodity)"
            try:
                pe = m.peers(sym)
                ctx["peers"] = [{"symbol": r["symbol"], "name": r["name"], "pe": r["pe"], "roe": r["roe"], "market_cap_cr": r["market_cap_cr"], "net_margin": r["net_margin"]}  # noqa: E501
                                for r in pe["rows"][:6]]
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
        note = ""
        if self.llm.available and question:
            system = SYSTEM.format(label=MODES[mode]) + "\n\nDATA:\n" + json.dumps(ctx, ensure_ascii=False, default=str)
            try:
                text, model = self.llm.chat(system, history).strip(), self.llm.label()
            except LLMError as exc:
                text, model, note = rules_answer(ctx, mode, question), "rules v0 (fallback)", f"language model unavailable: {exc}"
        else:
            text, model = rules_answer(ctx, mode, question), "rules v0"
        if "not investment advice" not in text.lower():
            text = text.rstrip() + "\n\nNot investment advice."
        return {"symbol": ctx["symbol"], "name": ctx["name"], "mode": mode, "reply": text, "model": model, "grounded": True, "note": note,
                "suggestions": SUGGEST[mode], "context": ctx}


# ---- rules fallback: the same shape, composed without a model ---------------------------------------
def _n(v, d=1, suffix=""):
    return "—" if v is None else f"{v:,.{d}f}{suffix}"


def _table(rows: list[tuple[str, str, str]]) -> str:
    return "| Metric | Value | Read |\n|---|---|---|\n" + "\n".join(f"| {a} | {b} | {c} |" for a, b, c in rows if b != "—")


def _median(xs: list[float]) -> float | None:
    s = sorted(xs)
    if not s:
        return None
    return s[len(s) // 2] if len(s) % 2 else (s[len(s) // 2 - 1] + s[len(s) // 2]) / 2


def rules_answer(ctx: dict, mode: str, question: str) -> str:
    q = (question or "").lower()
    name, sym = ctx["name"], ctx["symbol"]
    qt = ctx.get("quote") or {}
    bullets: list[str] = []
    if mode == "fundamental":
        s = ctx.get("snapshot")
        if not s:
            return f"No filings for {name}. {ctx.get('fundamentals_note', '')}".strip()
        peers = ctx.get("peers") or []
        pes = [p["pe"] for p in peers[1:] if p.get("pe")]
        med = _median(pes)
        rel = ("below" if s.get("pe") and med and s["pe"] < med else "above") if s.get("pe") and med else None
        if any(w in q for w in ("expensive", "cheap", "valuation", "p/e", "pe ", "price", "value")):
            summary = f"{name} trades at {_n(s.get('pe'))}× earnings, {rel} the sector median of {_n(med)}×." if rel else f"{name} trades at {_n(s.get('pe'))}× earnings; no peer median available."  # noqa: E501
            rows = [("P/E (TTM)", _n(s.get("pe")), rel + " peers" if rel else "—"), ("Peer median P/E", _n(med), f"{len(pes)} peers"), ("P/B", _n(s.get("pb"), 2), "—"),  # noqa: E501
                    ("EV / EBITDA", _n(s.get("ev_ebitda")), "—"), ("Market cap", "₹" + _n(s.get("market_cap_cr"), 0) + " cr", "—"), ("EPS growth 3y", _n(s.get("eps_cagr_3y"), 1, " %"), "per year"),  # noqa: E501
                    ("ROE", _n(s.get("roe"), 1, " %"), "high" if (s.get("roe") or 0) >= 18 else "modest")]
            bullets += [f"A P/E {rel} the peer median usually reflects {'slower growth or lower returns' if rel == 'below' else 'faster growth or higher returns'}; check the growth row." if rel else "No peer multiple to compare against; judge the P/E against the company's own growth.",  # noqa: E501
                        "A re-rating needs earnings growth to speed up or the sector multiple to move."]
            if rel:
                bullets.append(f"Peer set: {', '.join(p['symbol'] for p in peers[1:])}; median P/E {_n(med)}, so {sym} trades {rel} the group.")  # noqa: E501
        elif any(w in q for w in ("grow", "growth", "revenue", "sales", "profit", "earning")):
            summary = f"Revenue compounded {_n(s.get('revenue_cagr_3y'), 1, ' %')} a year and EPS {_n(s.get('eps_cagr_3y'), 1, ' %')} over three years."  # noqa: E501
            rows = [("Revenue CAGR 3y", _n(s.get("revenue_cagr_3y"), 1, " %"), "per year"), ("EPS CAGR 3y", _n(s.get("eps_cagr_3y"), 1, " %"), "per year"),  # noqa: E501
                    ("Revenue growth TTM", _n(s.get("revenue_ttm_growth"), 1, " %"), "latest year"), ("Profit growth TTM", _n(s.get("net_income_ttm_growth"), 1, " %"), "latest year"),  # noqa: E501
                    ("Net margin", _n(s.get("net_margin"), 1, " %"), "—")]
            for a in ctx.get("annual", []):
                rows.append((f"FY{a['fy'][:4]} revenue / profit", f"₹{_n(a['revenue_cr'], 0)} / ₹{_n(a['net_income_cr'], 0)} cr", "—"))
            bullets += ["Growth above 15 % a year is strong for a large company; below 8 % is slow.", "Watch whether margins expand with revenue; profit growing faster than sales is the good sign."]  # noqa: E501
        elif any(w in q for w in ("debt", "balance", "leverage", "cash", "strong", "solvent")):
            summary = f"Debt to equity is {_n(s.get('debt_equity'), 2)} and interest is covered {_n(s.get('interest_coverage'))}×."
            rows = [("Debt / equity", _n(s.get("debt_equity"), 2), "low" if (s.get("debt_equity") or 9) <= 0.5 else "high" if (s.get("debt_equity") or 0) >= 1.5 else "moderate"),  # noqa: E501
                    ("Interest coverage", _n(s.get("interest_coverage")) + "×", "thin" if (s.get("interest_coverage") or 9) < 2 else "comfortable"),  # noqa: E501
                    ("Free cash flow (TTM)", "₹" + _n(s.get("fcf_ttm_cr"), 0) + " cr", "positive" if (s.get("fcf_ttm_cr") or 0) > 0 else "negative"),  # noqa: E501
                    ("ROCE", _n(s.get("roce"), 1, " %"), "—"), ("ROE", _n(s.get("roe"), 1, " %"), "—")]
            bullets += ["Leverage under 0.5 and coverage above 5× leave room for a bad year.", "Negative free cash flow with rising debt is the combination to watch."]  # noqa: E501
        elif any(w in q for w in ("risk", "con", "worry", "bad", "weak", "wrong")):
            summary = f"The filings flag {len(ctx.get('cons') or [])} concerns for {name}." if ctx.get("cons") else f"Nothing in the filings stands out as a concern for {name}."  # noqa: E501
            rows = [("ROE", _n(s.get("roe"), 1, " %"), "—"), ("Debt / equity", _n(s.get("debt_equity"), 2), "—"), ("Revenue CAGR 3y", _n(s.get("revenue_cagr_3y"), 1, " %"), "—"),  # noqa: E501
                    ("Profit growth TTM", _n(s.get("net_income_ttm_growth"), 1, " %"), "—"), ("P/B", _n(s.get("pb"), 2), "—")]
            bullets += list(ctx.get("cons") or [])[:4] or ["No red flags from the rules; read the annual report's risk section for what numbers cannot show."]  # noqa: E501
        else:
            summary = f"{name}: P/E {_n(s.get('pe'))}×, ROE {_n(s.get('roe'), 1, ' %')}, revenue growing {_n(s.get('revenue_cagr_3y'), 1, ' %')} a year."  # noqa: E501
            rows = [("Market cap", "₹" + _n(s.get("market_cap_cr"), 0) + " cr", "—"), ("P/E (TTM)", _n(s.get("pe")), rel + " peers" if rel else "—"), ("P/B", _n(s.get("pb"), 2), "—"),  # noqa: E501
                    ("ROE", _n(s.get("roe"), 1, " %"), "—"), ("Debt / equity", _n(s.get("debt_equity"), 2), "—"), ("Revenue CAGR 3y", _n(s.get("revenue_cagr_3y"), 1, " %"), "—"),  # noqa: E501
                    ("EPS CAGR 3y", _n(s.get("eps_cagr_3y"), 1, " %"), "—"), ("Dividend yield", _n(s.get("dividend_yield"), 1, " %"), "—")]
            bullets += (ctx.get("pros") or [])[:2] + (ctx.get("cons") or [])[:2]
        c = ctx.get("council")
        if c:
            bullets.append(f"Council at one year: {c['stance']} with {c['confidence'] * 100:.0f} % confidence.")
    else:
        t = ctx.get("technicals")
        if not t:
            return f"Technicals unavailable for {name}. {ctx.get('technicals_note', '')}".strip()
        sm = t.get("summary") or {}
        ind = {i["name"]: i for i in t.get("indicators", [])}
        mas = {m["period"]: m for m in t.get("moving_averages", [])}
        piv = t.get("pivots_classic") or {}

        def ir(nm):
            i = ind.get(nm)
            return (f"{i['value']:,.2f}" if i and i.get("value") is not None else "—", i["action"] if i else "—")
        tfs = t.get("timeframes", [])
        if any(w in q for w in ("overbought", "oversold", "rsi", "stoch", "momentum")):
            summary = f"RSI is {ir('RSI (14)')[0]} ({ir('RSI (14)')[1].lower()}); stochastic {ir('STOCH (9,6)')[0]} ({ir('STOCH (9,6)')[1].lower()})."  # noqa: E501
            rows = [("RSI (14)", *ir("RSI (14)")), ("STOCH (9,6)", *ir("STOCH (9,6)")), ("STOCHRSI (14)", *ir("STOCHRSI (14)")), ("Williams %R", *ir("Williams %R")),  # noqa: E501
                    ("CCI (14)", *ir("CCI (14)")), ("Ultimate oscillator", *ir("Ultimate oscillator"))]
            bullets += ["Above 70 on RSI or 80 on the stochastics is stretched; below 30 / 20 is washed out.", "Oversold in a downtrend can stay oversold; pair it with the trend read."]  # noqa: E501
        elif any(w in q for w in ("level", "support", "resistance", "pivot", "target", "stop")):
            summary = f"Pivot {_n(piv.get('P'), 2)}: supports {_n(piv.get('S1'), 2)} and {_n(piv.get('S2'), 2)}, resistances {_n(piv.get('R1'), 2)} and {_n(piv.get('R2'), 2)}."  # noqa: E501
            rows = [("R2", _n(piv.get("R2"), 2), "resistance"), ("R1", _n(piv.get("R1"), 2), "resistance"), ("Pivot", _n(piv.get("P"), 2), "balance"),  # noqa: E501
                    ("S1", _n(piv.get("S1"), 2), "support"), ("S2", _n(piv.get("S2"), 2), "support"), ("MA 50", _n(mas.get(50, {}).get("sma"), 2), mas.get(50, {}).get("action", "—").lower()),  # noqa: E501
                    ("MA 200", _n(mas.get(200, {}).get("sma"), 2), mas.get(200, {}).get("action", "—").lower())]
            bullets += ["Classic pivots come from yesterday's high, low and close; they reset every session.", "A close beyond R1 or S1 with volume is the usual sign the level has given way."]  # noqa: E501
        elif any(w in q for w in ("timeframe", "agree", "weekly", "monthly", "hour", "minute")):
            verdicts = [x["verdict"] for x in tfs]
            agree = len(set(verdicts)) == 1
            summary = ("All timeframes agree: " + verdicts[0] + ".") if agree and verdicts else "The timeframes disagree; short-term and long-term reads differ."  # noqa: E501
            rows = [(x["tf"], x["verdict"], "—") for x in tfs]
            bullets += ["Agreement across daily, weekly and monthly is rarer and carries more weight than any one of them.", "When they split, the longer timeframe usually sets the direction and the shorter one the timing."]  # noqa: E501
        else:
            summary = f"Daily read is {sm.get('overall', '—')}: moving averages {sm.get('moving_averages', {}).get('verdict', '—').lower()}, indicators {sm.get('indicators', {}).get('verdict', '—').lower()}."  # noqa: E501
            rows = [("Overall (daily)", sm.get("overall", "—"), "—"), ("Moving averages", f"{sm.get('moving_averages', {}).get('buy', 0)} buy / {sm.get('moving_averages', {}).get('sell', 0)} sell", sm.get("moving_averages", {}).get("verdict", "—").lower()),  # noqa: E501
                    ("Indicators", f"{sm.get('indicators', {}).get('buy', 0)} buy / {sm.get('indicators', {}).get('sell', 0)} sell", sm.get("indicators", {}).get("verdict", "—").lower()),  # noqa: E501
                    ("RSI (14)", *ir("RSI (14)")), ("MACD (12,26)", *ir("MACD (12,26)")), ("ADX (14)", *ir("ADX (14)")), ("MA 200", _n(mas.get(200, {}).get("sma"), 2), mas.get(200, {}).get("action", "—").lower())]  # noqa: E501
            bullets += ["ADX above 25 means the trend has strength; below 20 the market is drifting.", "Price above the 200-day average keeps the long-term read constructive."]  # noqa: E501
        ai = ctx.get("ai_score")
        if ai:
            bullets.append(f"AI score {ai['score']}/10 short term; 1-month {_n(ai['ret_1m'], 1, ' %')}, 3-month {_n(ai['ret_3m'], 1, ' %')}, past win rate {_n(ai['win_rate'], 0, ' %')}.")  # noqa: E501
        c = ctx.get("council")
        if c:
            bullets.append(f"Council at one day: {c['stance']} with {c['confidence'] * 100:.0f} % confidence.")
    heads = ctx.get("headlines") or []
    if heads and any(w in q for w in ("news", "headline", "why", "today")):
        bullets.append("Wire: " + "; ".join(f"{h['title']} ({h['impact']})" for h in heads[:2]) + ".")
    head = f"**{name}** ({sym}) · ₹{_n(qt.get('ltp'), 2)} · {_n(qt.get('change_pct'), 2, ' %')} today"
    return head + "\n\n" + summary + "\n\n" + _table(rows) + "\n\n" + "\n".join(f"- {b}" for b in bullets[:4]) + "\n\nNot investment advice."  # noqa: E501


def find_mode(text: str) -> str:
    return "technical" if re.search(r"trend|rsi|macd|level|support|resistance|overbought|oversold|chart|pivot|moving average", (text or "").lower()) else "fundamental"  # noqa: E501
