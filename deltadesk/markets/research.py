"""Research teams: a small swarm of agents researches one stock and hands back a typed decision and a report.

The flow is a port of the swarm in HKUDS/Vibe-Trading (MIT licence, Copyright (c) 2026 Vibe-Trading Contributors):
a preset names agents and tasks, tasks form a graph through `depends_on`, each round runs the tasks whose inputs
are ready, every agent calls named tools and its report is handed to the tasks downstream. The first preset is
their Investment Committee: a bull-side and a bear-side researcher work in parallel, the chief risk officer
reviews both, the portfolio manager rules. Required outputs per agent follow that preset.

What differs here: the tools read Delta Desk's own read model (bars, technicals, filings, peers, wire, council),
and every number in the decision (stance, size cap, stop, target, confidence) is computed by rules so it is the
same with or without a language model. With a model configured (llm.py) each agent's prose is written by the
model from its DATA block; without one the same sections are composed by rules. Rules model v0, not advice.
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from deltadesk.markets.chat import find_symbol
from deltadesk.markets.llm import LLM, LLMError

PRESETS: dict[str, dict] = {
    "investment_committee": {
        "title": "Investment Committee",
        "description": "Long–short debate → risk review → PM final call.",
        "agents": [
            {"id": "bull_advocate", "role": "Bull-side Researcher",
             "tools": ["get_market_data", "technical_indicators", "get_financial_statements", "get_stock_news"],
             "brief": "Build the bullish case from technicals, fundamentals and sentiment. Sections: Bull thesis bullets; Technical detail; "  # noqa: E501
                      "Fundamental upside; Sentiment & flow support; Main risk to the bull case."},
            {"id": "bear_advocate", "role": "Bear-side Researcher",
             "tools": ["get_market_data", "technical_indicators", "get_financial_statements", "risk_metrics"],
             "brief": "Build the bear case: technical breakdown risk, valuation, fundamental deterioration, computed risk metrics. Sections: "  # noqa: E501
                      "Bear risk bullets; Technical breakdown risk; Valuation assessment; Risk metrics; What would disprove the bear case."},  # noqa: E501
            {"id": "risk_officer", "role": "Chief Risk Officer",
             "tools": ["risk_metrics", "peer_comparison"],
             "brief": "Review both cases independently. Sections: Risk review conclusion; Risk scorecard on bull points; Risk scorecard on "
                      "bear points; Blind-spot risks; Position sizing; Stop & hedge; Risk conditions."},
            {"id": "portfolio_manager", "role": "Portfolio Manager",
             "tools": ["council_vote"],
             "brief": "Make the final call. Sections: PM decision statement; Ruling on arguments; How risk input was used; Execution plan; "
                      "Targets & stops; Confidence & review triggers."},
        ],
        "tasks": [
            {"id": "task-bull", "agent_id": "bull_advocate", "depends_on": []},
            {"id": "task-bear", "agent_id": "bear_advocate", "depends_on": []},
            {"id": "task-risk", "agent_id": "risk_officer", "depends_on": ["task-bull", "task-bear"]},
            {"id": "task-decision", "agent_id": "portfolio_manager", "depends_on": ["task-risk"]},
        ],
    },
}
EXAMPLES = [
    {"category": "Research teams", "title": "Investment Committee on HDFC Bank", "desc": "Bull and bear debate, risk review, PM call.", "query": "HDFCBANK"},  # noqa: E501
    {"category": "Research teams", "title": "Should the desk own Reliance?", "desc": "Four agents, one typed decision.", "query": "Reliance"},  # noqa: E501
    {"category": "Research teams", "title": "Stress-test the case for TCS", "desc": "VaR, drawdown, stop and size cap.", "query": "TCS"},
]
SYSTEM = (
    "You are the {role} on Delta Desk's investment committee for Indian markets. {brief}\n"
    "Write ONLY from the DATA block (JSON). Quote the numbers you use; if something is not in the data, say it is unavailable. "
    "The fields under 'computed' are final: restate them exactly, never change a stance, size, stop, target or confidence.\n"
    "FORMAT: markdown. One bold label per section (e.g. **Bull thesis bullets**) followed by 1 to 4 short bullets, each under 22 words. "
    "No headings, no preamble, no closing line. Under 220 words."
)
LAYERS_MAX = 8
MAX_ACTIVE = 3
KEEP = 40
REUSE_S = 600.0


def _n(v, d: int = 1, suffix: str = "") -> str:
    return "—" if v is None else f"{v:,.{d}f}{suffix}"


def layers(tasks: list[dict]) -> list[list[dict]]:
    """Rounds of the task graph: a task runs in the first round after everything it depends on."""
    done: set[str] = set()
    left = list(tasks)
    out: list[list[dict]] = []
    while left and len(out) < LAYERS_MAX:
        ready = [t for t in left if set(t["depends_on"]) <= done]
        if not ready:
            raise ValueError("task graph has a cycle or an unknown dependency")
        out.append(ready)
        done |= {t["id"] for t in ready}
        left = [t for t in left if t["id"] not in done]
    return out


def risk_numbers(closes: list[float]) -> dict:
    """Asset-level risk from daily closes: realised volatility, 1-day 95 % historical VaR and CVaR, drawdown."""
    rets = [b / a - 1 for a, b in zip(closes[:-1], closes[1:], strict=False) if a]
    if len(rets) < 30:
        return {"available": False, "n": len(rets)}
    mean = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))
    srt = sorted(rets)
    k = max(1, int(len(srt) * 0.05))
    peak, mdd = closes[0], 0.0
    for c in closes:
        peak = max(peak, c)
        mdd = min(mdd, c / peak - 1)
    hi = max(closes)
    return {"available": True, "n": len(rets), "last": round(closes[-1], 2), "vol_daily_pct": round(sd * 100, 2), "vol_annual_pct": round(sd * math.sqrt(252) * 100, 1),  # noqa: E501
            "var95_1d_pct": round(-srt[k - 1] * 100, 2), "cvar95_1d_pct": round(-sum(srt[:k]) / k * 100, 2),
            "max_drawdown_pct": round(mdd * 100, 1), "worst_day_pct": round(srt[0] * 100, 2), "from_high_pct": round((closes[-1] / hi - 1) * 100, 1)}  # noqa: E501


class Research:
    def __init__(self, markets, llm: LLM | None = None, path: Path | str | None = None) -> None:
        self.m = markets
        self.llm = llm or LLM()
        self.path = Path(path or os.environ.get("DD_RESEARCH_STORE") or Path("data") / "research.json")
        self._runs: dict[str, dict] = {}
        self._lock = threading.Lock()
        try:
            for r in json.loads(self.path.read_text(encoding="utf-8")):
                self._runs[r["id"]] = r
        except (OSError, ValueError, KeyError, TypeError):
            pass

    # ---- public --------------------------------------------------------------------------------------
    def presets(self) -> dict:
        return {"presets": [{"name": k, "title": p["title"], "description": p["description"],
                             "agents": [{"id": a["id"], "role": a["role"]} for a in p["agents"]], "rounds": len(layers(p["tasks"]))}
                            for k, p in PRESETS.items()],
                "examples": EXAMPLES, "model": self.llm.label(), "llm": self.llm.available}

    def resolve(self, query: str) -> str | None:
        q = (query or "").strip()
        if not q:
            return None
        if self.m.known(q.upper()) and self.m._name(q.upper())[1] == "stock":
            return q.upper()
        sym = find_symbol(q)
        if sym:
            return sym
        hits = [r for r in self.m.search(q, 5) if r.get("kind") == "stock"]
        return hits[0]["key"] if hits else None

    def start(self, query: str, preset: str = "investment_committee", wait: bool = False) -> dict:
        if preset not in PRESETS:
            raise ValueError(f"unknown preset {preset}")
        sym = self.resolve(query)
        if not sym:
            raise ValueError("no stock found in that request; name one, e.g. HDFCBANK or Reliance")
        p = PRESETS[preset]
        now = time.time()
        with self._lock:
            for r in self._runs.values():   # an identical recent run is reused, so repeat clicks cost nothing
                if r["target"] == sym and r["preset"] == preset and r["status"] in ("running", "pending", "completed") and now - r["created"] < REUSE_S:  # noqa: E501
                    return self._view(r)
            if sum(1 for r in self._runs.values() if r["status"] in ("running", "pending")) >= MAX_ACTIVE:
                raise RuntimeError("three research runs are already in progress; try again in a moment")
            name, _, sector = self.m._name(sym)
            task_of = {t["agent_id"]: t["id"] for t in p["tasks"]}
            run = {"id": uuid.uuid4().hex[:12], "preset": preset, "title": p["title"], "query": query.strip()[:200], "target": sym, "name": name,  # noqa: E501
                   "sector": sector, "status": "pending", "round": 0, "rounds": len(layers(p["tasks"])), "created": now, "finished": None,
                   "model": self.llm.label(), "decision": None, "report": "", "error": "",
                   "agents": [{"id": a["id"], "role": a["role"], "task": task_of[a["id"]], "status": "waiting", "tool": "", "started": None,
                               "elapsed_s": None, "steps": [], "output": "", "report": "", "error": ""} for a in p["agents"]]}
            self._runs[run["id"]] = run
        if wait:
            self._execute(run)
        else:
            threading.Thread(target=self._execute, args=(run,), daemon=True, name=f"research-{run['id']}").start()
        return self._view(run)

    def get(self, run_id: str) -> dict | None:
        with self._lock:
            r = self._runs.get(run_id)
            return self._view(r) if r else None

    def history(self, limit: int = 12) -> list[dict]:
        with self._lock:
            rows = sorted(self._runs.values(), key=lambda r: -r["created"])[:limit]
            return [{"id": r["id"], "target": r["target"], "name": r["name"], "title": r["title"], "status": r["status"], "created": r["created"],  # noqa: E501
                     "action": (r.get("decision") or {}).get("action"), "confidence": (r.get("decision") or {}).get("confidence")} for r in rows]  # noqa: E501

    @staticmethod
    def _view(r: dict) -> dict:
        out = json.loads(json.dumps(r, default=str))
        now = time.time()
        for a in out["agents"]:
            if a["status"] == "running" and a["started"]:
                a["elapsed_s"] = round(now - a["started"], 1)
        out["elapsed_s"] = round((r["finished"] or now) - r["created"], 1)
        out["done"] = sum(1 for a in out["agents"] if a["status"] in ("done", "failed"))
        return out

    # ---- runtime ---------------------------------------------------------------------------------------
    def _execute(self, run: dict) -> None:
        p = PRESETS[run["preset"]]
        agents = {a["id"]: a for a in p["agents"]}
        state = {a["id"]: a for a in run["agents"]}
        memo: dict[str, dict] = {}
        memo_lock = threading.Lock()
        results: dict[str, dict] = {}
        run["status"] = "running"
        try:
            for i, layer in enumerate(layers(p["tasks"]), 1):
                run["round"] = i

                def work(task: dict) -> None:
                    st = state[task["agent_id"]]
                    spec = agents[task["agent_id"]]
                    st["status"], st["started"] = "running", time.time()
                    try:
                        data = {t: self._tool(run["target"], t, st, memo, memo_lock) for t in spec["tools"]}
                        upstream = {d: results[d] for d in task["depends_on"]}
                        res = COMPOSE[spec["id"]](run, data, upstream)
                        res["text"] = self._write(spec, run, data, upstream, res)
                        results[task["id"]] = res
                        st["report"], st["output"], st["status"] = res["text"], res["line"], "done"
                    except Exception as exc:  # noqa: BLE001 - one agent failing is shown on its row, the run reports it
                        st["status"], st["error"], st["output"] = "failed", str(exc)[:200], str(exc)[:200]
                        raise
                    finally:
                        st["tool"] = ""
                        st["elapsed_s"] = round(time.time() - st["started"], 1)
                with ThreadPoolExecutor(max_workers=len(layer)) as ex:
                    list(ex.map(work, layer))
            last = results[p["tasks"][-1]["id"]]
            run["decision"] = last.get("decision")
            run["report"] = "\n\n".join(f"## {a['role']}\n\n{state[a['id']]['report']}" for a in reversed(p["agents"])) + "\n\nNot investment advice."  # noqa: E501
            run["status"] = "completed"
        except Exception as exc:  # noqa: BLE001
            run["status"], run["error"] = "failed", str(exc)[:300]
        run["finished"] = time.time()
        self._save()

    def _tool(self, sym: str, tool: str, st: dict, memo: dict, memo_lock: threading.Lock) -> dict:
        step = {"tool": tool, "status": "running", "elapsed_ms": None, "preview": ""}
        st["steps"].append(step)
        st["tool"] = tool
        t0 = time.time()
        try:
            with memo_lock:
                hit = memo.get(tool)
            if hit is None:
                hit = TOOLS[tool](self.m, sym, memo)
                with memo_lock:
                    memo[tool] = hit
            step["status"], step["preview"] = "ok", hit.get("preview", "")
            return hit
        except Exception as exc:  # noqa: BLE001 - a failed tool is a step with an error; the agent works with what it has
            step["status"], step["preview"] = "error", str(exc)[:160]
            return {"available": False, "preview": str(exc)[:160]}
        finally:
            step["elapsed_ms"] = int((time.time() - t0) * 1000)

    def _write(self, spec: dict, run: dict, data: dict, upstream: dict, res: dict) -> str:
        if not self.llm.available:
            return res["text"]
        block = {"target": run["target"], "name": run["name"], "sector": run["sector"], "computed": res.get("computed", {}),
                 "points": res.get("points", []), "tools": {k: {x: y for x, y in v.items() if x != "raw"} for k, v in data.items()},
                 "upstream": {k: {"line": v["line"], "points": v.get("points", []), "computed": v.get("computed", {})} for k, v in upstream.items()}}  # noqa: E501
        try:
            text = self.llm.chat(SYSTEM.format(role=spec["role"], brief=spec["brief"]) + "\n\nDATA:\n" + json.dumps(block, ensure_ascii=False, default=str),  # noqa: E501
                                 [{"role": "user", "content": f"Write your committee report on {run['name']} ({run['target']})."}], max_tokens=600).strip()  # noqa: E501
            return text or res["text"]
        except LLMError:
            return res["text"]

    def _save(self) -> None:
        with self._lock:
            rows = sorted(self._runs.values(), key=lambda r: -r["created"])
            for r in rows[KEEP:]:
                self._runs.pop(r["id"], None)
            keep = [r for r in rows[:KEEP] if r["status"] in ("completed", "failed")]
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(keep, default=str), encoding="utf-8")
            except OSError:
                pass


# ---- tools: each returns facts plus a one-line preview for the step row ------------------------------------
def _closes(m, sym: str, memo: dict) -> list[float]:
    if "_closes" not in memo:
        memo["_closes"] = [b["close"] for b in m.bars(sym, "1y")["bars"] if b.get("close")]
    return memo["_closes"]


def t_market(m, sym: str, memo: dict) -> dict:
    c = _closes(m, sym, memo)
    if len(c) < 30:
        return {"available": False, "preview": f"{len(c)} daily bars, not enough"}
    q = m.quotes.quotes([sym]).get(sym)
    last = c[-1]
    ret = lambda n: round((last / c[-n - 1] - 1) * 100, 1) if len(c) > n else None  # noqa: E731
    sma = lambda n: round(sum(c[-n:]) / n, 2) if len(c) >= n else None  # noqa: E731
    hi, lo = max(c), min(c)
    return {"available": True, "last": round(last, 2), "change_pct": q.change_pct if q else None, "bars": len(c), "ret_1m": ret(21), "ret_3m": ret(63),  # noqa: E501
            "ret_1y": round((last / c[0] - 1) * 100, 1), "sma50": sma(50), "sma200": sma(200), "high_52w": round(hi, 2), "low_52w": round(lo, 2),  # noqa: E501
            "range_pos": round((last - lo) / (hi - lo), 2) if hi > lo else 0.5, "source": m.council.bars.name,
            "preview": f"{len(c)} daily bars · last {last:,.2f} · 3m {_n(ret(63), 1, ' %')}"}


def t_technicals(m, sym: str, memo: dict) -> dict:
    t = m.technicals(sym, "daily")
    sm = t.get("summary") or {}
    ind = {i["name"]: i for i in t.get("indicators", [])}
    val = lambda k: (ind.get(k) or {}).get("value")  # noqa: E731
    return {"available": bool(sm), "overall": sm.get("overall", "—"), "ma": (sm.get("moving_averages") or {}).get("verdict", "—"),
            "ind": (sm.get("indicators") or {}).get("verdict", "—"), "rsi": val("RSI (14)"), "adx": val("ADX (14)"),
            "macd": (ind.get("MACD (12,26)") or {}).get("action", "—"),
            "timeframes": [{"tf": s["label"], "verdict": s["verdict"]} for s in t.get("strip", [])],
            "preview": f"daily {sm.get('overall', '—')} · RSI {_n(val('RSI (14)'), 0)} · ADX {_n(val('ADX (14)'), 0)}"}


def t_statements(m, sym: str, memo: dict) -> dict:
    f = m.fundamentals(sym)
    if not f or f.get("error"):
        return {"available": False, "preview": "no filings from this data source"}
    s = f.get("snapshot") or {}
    keys = ("pe", "pb", "ev_ebitda", "roe", "roce", "debt_equity", "interest_coverage", "net_margin", "revenue_cagr_3y", "eps_cagr_3y",
            "dividend_yield", "market_cap_cr", "fcf_ttm_cr")
    return {"available": True, **{k: s.get(k) for k in keys}, "pros": (f.get("pros") or [])[:3], "cons": (f.get("cons") or [])[:3],
            "preview": f"P/E {_n(s.get('pe'))} · ROE {_n(s.get('roe'), 1, ' %')} · D/E {_n(s.get('debt_equity'), 2)}"}


def t_news(m, sym: str, memo: dict) -> dict:
    rows = m.news.feed(symbols=[sym], limit=8)["entries"]
    good, bad = sum(1 for h in rows if h["impact"] == "good"), sum(1 for h in rows if h["impact"] == "bad")
    return {"available": True, "count": len(rows), "good": good, "bad": bad, "headlines": [{"title": h["title"], "impact": h["impact"]} for h in rows[:4]],  # noqa: E501
            "preview": f"{len(rows)} headlines · {good} good · {bad} bad"}


def t_risk(m, sym: str, memo: dict) -> dict:
    r = risk_numbers(_closes(m, sym, memo))
    if not r["available"]:
        return {**r, "preview": "not enough bars for risk metrics"}
    return {**r, "preview": f"VaR 95 % 1d {r['var95_1d_pct']} % · max drawdown {r['max_drawdown_pct']} % · vol {r['vol_annual_pct']} %"}


def t_peers(m, sym: str, memo: dict) -> dict:
    p = m.peers(sym)
    pes = sorted(r["pe"] for r in p["rows"][1:] if r.get("pe"))
    med = (pes[len(pes) // 2] if len(pes) % 2 else (pes[len(pes) // 2 - 1] + pes[len(pes) // 2]) / 2) if pes else None
    return {"available": bool(p["rows"]), "sector": p["sector"], "peers": [r["symbol"] for r in p["rows"][1:]], "median_pe": med,
            "preview": f"{max(0, len(p['rows']) - 1)} peers in {p['sector'] or 'no sector'}" + (f" · median P/E {med:.1f}" if med else "")}


def t_council(m, sym: str, memo: dict) -> dict:
    c = m.council_run(sym, "3mo")
    v = c["verdict"]
    return {"available": True, "stance": v["stance"], "score": v["score"], "confidence": v["confidence"], "horizon": c["horizon_label"],
            "preview": f"council at 3 months: {v['stance']} {v['score']:+.2f}"}


TOOLS = {"get_market_data": t_market, "technical_indicators": t_technicals, "get_financial_statements": t_statements, "get_stock_news": t_news,  # noqa: E501
         "risk_metrics": t_risk, "peer_comparison": t_peers, "council_vote": t_council}


# ---- agents: rules compose the points, the numbers and the fallback prose ----------------------------------
def _points(data: dict, side: str) -> list[dict]:
    """Evidence for one side, each point with the weight the committee gives it (high 2, medium 1)."""
    pts: list[dict] = []

    def add(text: str, w: int = 1) -> None:
        pts.append({"text": text, "weight": w, "confidence": "high" if w > 1 else "medium"})
    mk, ta, fs, nw = (data.get(k) or {} for k in ("get_market_data", "technical_indicators", "get_financial_statements", "get_stock_news"))
    bull = side == "bull"
    if mk.get("available"):
        last = mk["last"]
        for n, w in ((200, 2), (50, 1)):
            s = mk.get(f"sma{n}")
            if s and (last > s) == bull:
                add(f"Price {last:,.2f} is {'above' if bull else 'below'} its {n}-day average {s:,.2f}", w)
        r3 = mk.get("ret_3m")
        if r3 is not None and abs(r3) >= 5 and (r3 > 0) == bull:
            add(f"3-month return {r3:+.1f} %")
        if bull and mk["range_pos"] >= 0.85:
            add(f"Trading in the top of its 52-week range ({mk['range_pos'] * 100:.0f} %)")
        if not bull and mk["range_pos"] <= 0.25:
            add(f"Near the bottom of its 52-week range ({mk['range_pos'] * 100:.0f} %)")
    if ta.get("available"):
        ov = ta["overall"].lower()
        if ("buy" in ov) == bull and ov not in ("neutral", "—"):
            add(f"Daily technical read is {ta['overall']} (moving averages {ta['ma'].lower()}, indicators {ta['ind'].lower()})", 2 if "strong" in ov else 1)  # noqa: E501
        rsi = ta.get("rsi")
        if rsi is not None and rsi >= 70 and not bull:
            add(f"RSI {rsi:.0f} is stretched")
        if rsi is not None and rsi <= 30 and bull:
            add(f"RSI {rsi:.0f} is washed out")
    if fs.get("available"):
        checks = (("roe", 18, 10, "ROE {:.1f} %"), ("revenue_cagr_3y", 12, 5, "Revenue growth {:.1f} % a year over three years"),
                  ("eps_cagr_3y", 12, 0, "EPS growth {:.1f} % a year over three years"))
        for key, good, weak, label in checks:
            v = fs.get(key)
            if v is not None and ((bull and v >= good) or (not bull and v < weak)):
                add(label.format(v))
        de = fs.get("debt_equity")
        if de is not None and ((bull and de <= 0.5) or (not bull and de >= 1.5)):
            add(f"Debt to equity {de:.2f}")
        pe = fs.get("pe")
        if pe is not None and ((bull and pe < 18) or (not bull and pe > 40)):
            add(f"P/E {pe:.1f}× is {'modest' if bull else 'rich'}")
        for t in fs.get("pros" if bull else "cons", [])[:2]:
            add(str(t))
    if nw.get("available") and nw.get("good" if bull else "bad", 0) > nw.get("bad" if bull else "good", 0):
        add(f"Wire: {nw['good']} good-impact and {nw['bad']} bad-impact headlines")
    return pts[:6]


def _bullets(pts: list[dict], key: str = "confidence") -> str:
    return "\n".join(f"- {p['text']} ({p[key]})" for p in pts) or "- Nothing in the data argues this side."


def bull(run: dict, data: dict, up: dict) -> dict:
    pts = _points(data, "bull")
    mk, ta, fs, nw = (data.get(k) or {} for k in ("get_market_data", "technical_indicators", "get_financial_statements", "get_stock_news"))
    score = sum(p["weight"] for p in pts)
    text = (f"**Bull thesis bullets**\n{_bullets(pts)}\n\n"
            f"**Technical detail**\n- Daily read {ta.get('overall', '—')}; MACD {ta.get('macd', '—')}; RSI {_n(ta.get('rsi'), 0)}; ADX {_n(ta.get('adx'), 0)}\n"  # noqa: E501
            f"- 50-day {_n(mk.get('sma50'), 2)} · 200-day {_n(mk.get('sma200'), 2)} · 52-week high {_n(mk.get('high_52w'), 2)}\n\n"
            "**Fundamental upside**\n" + (f"- P/E {_n(fs.get('pe'))}× · ROE {_n(fs.get('roe'), 1, ' %')} · EPS growth {_n(fs.get('eps_cagr_3y'), 1, ' %')} a year"  # noqa: E501
                                          if fs.get("available") else "- Filings unavailable from this data source") + "\n\n"
            f"**Sentiment & flow support**\n- {nw.get('preview', 'no headlines')}\n\n"
            "**Main risk to the bull case**\n- A close below the 200-day average or a cut to earnings growth breaks it")
    return {"points": pts, "score": score, "computed": {"bull_score": score, "points": len(pts)}, "text": text,
            "line": f"{len(pts)} bull points · score {score}"}


def bear(run: dict, data: dict, up: dict) -> dict:
    pts = _points(data, "bear")
    rk, mk, ta, fs = (data.get(k) or {} for k in ("risk_metrics", "get_market_data", "technical_indicators", "get_financial_statements"))
    if rk.get("available") and rk["max_drawdown_pct"] <= -25:
        pts.append({"text": f"Max drawdown {rk['max_drawdown_pct']} % inside the sample", "weight": 1, "confidence": "medium"})
    if rk.get("available") and rk["vol_annual_pct"] >= 40:
        pts.append({"text": f"Realised volatility {rk['vol_annual_pct']} % a year", "weight": 1, "confidence": "medium"})
    for p in pts:
        p["severity"] = p["confidence"]
    score = sum(p["weight"] for p in pts)
    risk = (f"- 1-day 95 % VaR {rk['var95_1d_pct']} % · CVaR {rk['cvar95_1d_pct']} % (historical, {rk['n']} daily returns)\n"
            f"- Max drawdown {rk['max_drawdown_pct']} % · worst day {rk['worst_day_pct']} % · volatility {rk['vol_annual_pct']} % a year"
            if rk.get("available") else "- Risk metrics unavailable: not enough bars")
    text = (f"**Bear risk bullets**\n{_bullets(pts, 'severity')}\n\n"
            f"**Technical breakdown risk**\n- Daily read {ta.get('overall', '—')}; {_n(rk.get('from_high_pct'), 1, ' %')} from the 52-week high of {_n(mk.get('high_52w'), 2)}\n\n"  # noqa: E501
            "**Valuation assessment**\n" + (f"- P/E {_n(fs.get('pe'))}× · P/B {_n(fs.get('pb'), 2)} · EV/EBITDA {_n(fs.get('ev_ebitda'))}; no DCF is run here"  # noqa: E501
                                            if fs.get("available") else "- Filings unavailable, so no valuation read") + "\n\n"
            f"**Risk metrics**\n{risk}\n\n"
            "**What would disprove the bear case**\n- Price holding above the 200-day average with earnings growth intact")
    return {"points": pts, "score": score, "computed": {"bear_score": score, "points": len(pts)}, "text": text,
            "line": f"{len(pts)} bear points · score {score}"}


def risk_officer(run: dict, data: dict, up: dict) -> dict:
    b, s = up["task-bull"], up["task-bear"]
    rk, pe = data.get("risk_metrics") or {}, data.get("peer_comparison") or {}
    net = b["score"] - s["score"]
    vol = rk.get("vol_annual_pct")
    stance = "oppose" if net <= -2 else "support" if net >= 2 and (vol or 0) < 40 else "conditional support"
    # stop distance: the larger of 5 % and a 10-session 95 % move; size so a stop-out costs 1 % of the portfolio, capped at 10 %
    dist = max(5.0, 1.65 * (rk.get("vol_daily_pct") or 1.5) * math.sqrt(10))
    cap = 0.0 if stance == "oppose" else round(min(10.0, 100.0 / dist), 1)
    blind = []
    if not (b.get("points") and s.get("points")):
        blind.append("One side found no evidence in the data; the debate is thin")
    if not rk.get("available"):
        blind.append("Risk metrics could not be computed; sizing uses a default 1.5 % daily move")
    if pe.get("median_pe") is None:
        blind.append("No peer valuation from this data source")
    blind.append("Earnings dates, pledged shares and block deals are not in the desk's data")
    score = lambda pts: "\n".join(f"- {p['text']}: reliability {3 + p['weight']}/5" for p in pts[:4]) or "- No points to score"  # noqa: E731
    cond = {"support": "- None beyond the stop", "oppose": "- Revisit only after the bear points clear",
            "conditional support": "- Enter only while price holds its 200-day average; cut on the stop without averaging down"}[stance]
    text = (f"**Risk review conclusion**\n- {stance.capitalize()}: bull score {b['score']} against bear score {s['score']}"
            + (f", volatility {vol} % a year" if vol else "") + "\n\n"
            f"**Risk scorecard on bull points**\n{score(b.get('points', []))}\n\n**Risk scorecard on bear points**\n{score(s.get('points', []))}\n\n"  # noqa: E501
            "**Blind-spot risks**\n" + "\n".join(f"- {x}" for x in blind[:3]) + "\n\n"
            f"**Position sizing**\n- Not more than {cap:.1f} % of the portfolio (a stop-out then costs at most about 1 %)\n\n"
            f"**Stop & hedge**\n- Stop {dist:.1f} % below entry; no hedge priced, options data is not wired to this desk\n\n"
            f"**Risk conditions**\n{cond}")
    return {"points": blind, "text": text, "line": f"{stance} · cap {cap:.1f} % · stop -{dist:.1f} %",
            "computed": {"stance": stance, "size_cap_pct": cap, "stop_distance_pct": round(dist, 1), "bull_score": b["score"], "bear_score": s["score"],  # noqa: E501
                         "net": net, "risk": {k: v for k, v in rk.items() if k != "preview"}}}


def portfolio_manager(run: dict, data: dict, up: dict) -> dict:
    r = up["task-risk"]["computed"]
    cn = data.get("council_vote") or {}
    net, stance = r["net"], r["stance"]
    action = "avoid" if stance == "oppose" or net <= -2 else "long" if net >= 2 else "wait"
    agree = cn.get("available") and {"long": "buy", "avoid": "sell", "wait": "hold"}[action] == cn.get("stance")
    conf = int(max(35, min(85, 50 + 6 * abs(net) + (8 if agree else -6 if cn.get("available") else 0))))
    entry = (r.get("risk") or {}).get("last")
    decision = {"action": action, "confidence": conf, "risk_stance": stance, "size_pct": r["size_cap_pct"] if action == "long" else 0.0,
                "stop_pct": -r["stop_distance_pct"], "target_pct": round(2 * r["stop_distance_pct"], 1), "horizon": "3 months",
                "bull_score": r["bull_score"], "bear_score": r["bear_score"], "council": cn.get("stance"), "entry": entry}
    first = decision["size_pct"] / 2
    plan = (f"- First tranche {first:.1f} %, add the second half after a close above entry +{r['stop_distance_pct'] / 2:.1f} %\n- Hard stop {decision['stop_pct']:.1f} %; "  # noqa: E501
            f"target +{decision['target_pct']:.1f} % (2 to 1)") if action == "long" else "- No position; re-run the committee when the scores change"  # noqa: E501
    text = (f"**PM decision statement**\n- {action.upper()} {run['name']}: bull {r['bull_score']} against bear {r['bear_score']}, risk office says {stance}\n\n"  # noqa: E501
            f"**Ruling on arguments**\n- Net score {net:+d}; a long needs +2 or better, an avoid −2 or worse\n"
            f"- Council at three months: {cn.get('stance', 'unavailable')}" + (" (agrees)" if agree else "") + "\n\n"
            f"**How risk input was used**\n- Size cap {r['size_cap_pct']:.1f} % and stop -{r['stop_distance_pct']:.1f} % accepted as given\n\n"  # noqa: E501
            f"**Execution plan**\n{plan}\n\n"
            f"**Targets & stops**\n- Stop {decision['stop_pct']:.1f} % · target +{decision['target_pct']:.1f} % · horizon {decision['horizon']}\n\n"  # noqa: E501
            f"**Confidence & review triggers**\n- Confidence {conf} %; review on a stop-out, a 200-day cross or new filings")
    return {"decision": decision, "computed": decision, "text": text, "line": f"{action} · confidence {conf} %"}


COMPOSE = {"bull_advocate": bull, "bear_advocate": bear, "risk_officer": risk_officer, "portfolio_manager": portfolio_manager}
