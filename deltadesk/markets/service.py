"""Read model for the markets page: quotes across asset classes, screener, heat-map stats, watchlists,
calendars, institutional flows and news."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import date

from deltadesk.markets import technicals as ta
from deltadesk.markets import universe
from deltadesk.markets.agent_chat import AgentChat
from deltadesk.markets.ai_rank import AiRanker, SyntheticHistory
from deltadesk.markets.council import Council, SyntheticBars, chart_bars
from deltadesk.markets.fundamentals import YahooFundamentals
from deltadesk.markets.news import NewsService
from deltadesk.markets.quotes import QuoteProvider, SyntheticQuotes
from deltadesk.markets.research import Research
from deltadesk.markets.track import TrackRecord
from deltadesk.markets.watchlist import Watchlist, presets


class MarketsService:
    def __init__(self, quotes: QuoteProvider | None = None, watchlist: Watchlist | None = None,
                 news: NewsService | None = None, ai: AiRanker | None = None, council: Council | None = None,
                 fundamentals: YahooFundamentals | None = None, track: TrackRecord | None = None) -> None:
        self.quotes = quotes or SyntheticQuotes()
        self.ai = ai or AiRanker(SyntheticHistory())
        self.track = track or TrackRecord(SyntheticHistory(days=260), SyntheticHistory(days=200, weekly=True))
        self.council = council or Council(SyntheticBars())
        self.funda = fundamentals
        if self.funda is not None and self.council.fundamentals is None:
            self.council.fundamentals = self.funda.council_summary
        self.agent = AgentChat(self)
        self.research = Research(self, self.agent.llm)
        self._wl_stats: dict[str, tuple[float, dict]] = {}
        self.watchlist = watchlist or Watchlist()
        self.news = news or NewsService()
        universe.load_cached()

    # ---- indices and constituents ---------------------------------------------------------
    def indices(self) -> list[dict]:
        q = self.quotes.quotes(list(universe.INDICES))
        return [{"code": ix.code, "name": ix.name, "exchange": ix.exchange, "fno": ix.fno, "lot_size": ix.lot_size,
                 "feed_key": ix.feed_key, "n": len(ix.constituents), "quote": q[ix.code].json() if ix.code in q else None}
                for ix in universe.INDICES.values()]

    def index(self, code: str) -> dict | None:
        ix = universe.INDICES.get(code.upper())
        if ix is None:
            return None
        syms = [c.symbol for c in ix.constituents]
        q = self.quotes.quotes(syms + [ix.code])
        rows = [{**asdict(c), "quote": q[c.symbol].json() if c.symbol in q else None} for c in ix.constituents]
        chg = [r["quote"]["change_pct"] for r in rows if r["quote"]]
        adv = sum(1 for x in chg if x > 0.05)
        dec = sum(1 for x in chg if x < -0.05)
        by_sector: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            by_sector[r["sector"]].append(r)
        sectors = []
        for s, rs in by_sector.items():
            w = sum(r["weight"] for r in rs) or 1.0
            wc = sum(r["weight"] * (r["quote"]["change_pct"] if r["quote"] else 0.0) for r in rs) / w
            sectors.append({"sector": s, "weight": round(w, 2), "change_pct": round(wc, 2), "n": len(rs)})
        sectors.sort(key=lambda x: -x["weight"])
        ranked = sorted([r for r in rows if r["quote"]], key=lambda r: -r["quote"]["change_pct"])
        return {"code": ix.code, "name": ix.name, "exchange": ix.exchange, "fno": ix.fno, "lot_size": ix.lot_size,
                "feed_key": ix.feed_key, "quote": q[ix.code].json() if ix.code in q else None,
                "constituents": rows, "sectors": sectors,
                "breadth": {"advances": adv, "declines": dec, "unchanged": len(chg) - adv - dec},
                "gainers": ranked[:5], "losers": ranked[-5:][::-1]}

    # ---- other asset classes --------------------------------------------------------------
    def indicators(self) -> list[dict]:
        """India indices plus the global indicators people watch: rupee, gold, silver, crude, crypto, US yields, world indices."""
        keys = ["NIFTY50", "BANKNIFTY", "SENSEX", "INDIAVIX"] + list(universe.INDICATORS)
        q = self.quotes.quotes(keys)
        out = []
        for k in keys[:4]:
            ix = universe.INDICES[k]
            out.append({"key": k, "name": ix.name, "group": "india", "unit": "index", "decimals": 2, "quote": q[k].json() if k in q else None})  # noqa: E501
        for g in (universe.GLOBAL_BY_KEY[k] for k in universe.INDICATORS):
            out.append({"key": g[0], "name": g[1], "group": g[5], "unit": g[4], "decimals": g[3], "quote": q[g[0]].json() if g[0] in q else None})  # noqa: E501
        return out

    # ---- search and watchlist ---------------------------------------------------------------
    def _name(self, k: str) -> tuple[str, str, str]:
        if k in universe.INDICES:
            return universe.INDICES[k].name, "index", ""
        c = universe.all_symbols().get(k)
        if c:
            return c.name, "stock", c.sector
        for s, n, t, _ in universe.ETFS:
            if s == k:
                return n, "etf", t
        for s, n, d, _ in universe.FX:
            if s == k:
                return n, "forex", d
        if k in universe.GLOBAL_BY_KEY:
            g = universe.GLOBAL_BY_KEY[k]
            return g[1], "global", g[4]
        if k in universe.FX_WORLD_BY_KEY:
            f = universe.FX_WORLD_BY_KEY[k]
            return f[1], "forex", f"{f[4]}/{f[5]}"
        if k.startswith("FUT:"):
            for f in universe.futures_contracts(date.today()):
                if f["key"] == k:
                    return f["symbol"], "future", f["expiry"]
        return k, "unknown", ""

    def known(self, k: str) -> bool:
        return self._name(k)[1] != "unknown"

    def search(self, q: str, limit: int = 12) -> list[dict]:
        q = q.strip().upper()
        if not q:
            return []
        out = []
        for ix in universe.INDICES.values():
            if q in ix.code or q in ix.name.upper():
                out.append({"key": ix.code, "name": ix.name, "kind": "index"})
        for s, c in universe.all_symbols().items():
            if q in s or q in c.name.upper():
                out.append({"key": s, "name": c.name, "kind": "stock", "sector": c.sector})
        for s, n, t, _ in universe.ETFS:
            if q in s or q in n.upper():
                out.append({"key": s, "name": n, "kind": "etf", "sector": t})
        for s, n, d, _ in universe.FX:
            if q in s or q in n.upper():
                out.append({"key": s, "name": n, "kind": "forex", "sector": d})
        for g in universe.GLOBAL:
            if q in g[0] or q in g[1].upper():
                out.append({"key": g[0], "name": g[1], "kind": "global", "sector": g[4]})
        for f in universe.FX_WORLD:
            if q in f[0] or q in f[1].upper():
                out.append({"key": f[0], "name": f[1], "kind": "forex", "sector": f"{f[4]}/{f[5]}"})
        out.sort(key=lambda r: (not r["key"].startswith(q), r["key"]))
        return out[:limit]

    def watchlists(self) -> dict:
        keys = sorted({k for v in self.watchlist.lists.values() for k in v})
        q = self.quotes.quotes(keys)

        def row(k: str) -> dict:
            name, kind, sector = self._name(k)
            return {"key": k, "name": name, "kind": kind, "sector": sector, "quote": q[k].json() if k in q else None}
        return {"lists": {name: [row(k) for k in keys_] for name, keys_ in self.watchlist.lists.items()}, "max_symbols": 50, "max_lists": 12}  # noqa: E501

    def wl_stats(self, symbols: list[str]) -> dict:
        """Week and month change plus the 52-week range from daily bars; cached half an hour per symbol."""
        import time as _t
        from concurrent.futures import ThreadPoolExecutor
        now = _t.time()
        want = [k for k in symbols if k not in self._wl_stats or now - self._wl_stats[k][0] > 1800][:60]

        def one(k: str) -> tuple[str, dict]:
            try:
                bars = self.council.bars.bars_for(k, "1y", "1d")
            except Exception:  # noqa: BLE001
                bars = []
            c = [b.close for b in bars]
            if len(c) < 6:
                return k, {}
            hi = max(b.high for b in bars[-250:])
            lo = min(b.low for b in bars[-250:])
            out = {"ret_1w": round((c[-1] / c[-6] - 1) * 100, 2), "ret_1m": round((c[-1] / c[-22] - 1) * 100, 2) if len(c) >= 22 else None,
                   "hi_52w": round(hi, 2), "lo_52w": round(lo, 2)}
            return k, out
        if want:
            with ThreadPoolExecutor(max_workers=8) as ex:
                for k, v in ex.map(one, want):
                    self._wl_stats[k] = (now, v)
        return {k: self._wl_stats[k][1] for k in symbols if k in self._wl_stats}

    @staticmethod
    def watchlist_presets() -> list[dict]:
        return presets()

    def fundamentals(self, symbol: str, refresh: bool = False) -> dict | None:
        """Koyfin-style statements, ratios and snapshot; None for instruments without statements."""
        if self.funda is None:
            return {"symbol": symbol.upper(), "error": "fundamentals provider not configured (run with DD_QUOTES=yahoo)", "source": "none"}
        return self.funda.analysis(symbol, refresh)

    def technicals(self, symbol: str, timeframe: str = "daily") -> dict:
        """Indicators, moving averages and pivots on one timeframe, plus the summary verdict for every timeframe."""
        symbol = symbol.upper()
        if timeframe not in ta.TIMEFRAMES:
            timeframe = "daily"
        out = ta.analyse(self.bars(symbol, ta.TIMEFRAMES[timeframe][0])["bars"], timeframe)
        strip = []
        for tf, (rng, label) in ta.TIMEFRAMES.items():
            try:
                r = out if tf == timeframe else ta.analyse(self.bars(symbol, rng)["bars"], tf)
                strip.append({"timeframe": tf, "label": label, "verdict": r.get("summary", {}).get("overall", "—"),
                              "ma": r.get("summary", {}).get("moving_averages", {}).get("verdict", "—"),
                              "ind": r.get("summary", {}).get("indicators", {}).get("verdict", "—")})
            except Exception:  # noqa: BLE001 - one timeframe failing must not sink the page
                strip.append({"timeframe": tf, "label": label, "verdict": "—", "ma": "—", "ind": "—"})
        out["strip"] = strip
        out["symbol"] = symbol
        out["source"] = self.council.bars.name
        return out

    def peers(self, symbol: str, limit: int = 8) -> dict:
        """Same-sector companies from the index universe with quote and, when the provider is configured, valuation."""
        symbol = symbol.upper()
        me = universe.all_symbols().get(symbol)
        if me is None:
            return {"symbol": symbol, "sector": "", "rows": []}
        cands = sorted([c for c in universe.all_symbols().values() if c.sector == me.sector and c.symbol != symbol], key=lambda c: -c.weight)[:limit]  # noqa: E501
        rows = [me] + cands
        q = self.quotes.quotes([c.symbol for c in rows])
        snaps: dict[str, dict] = {}
        if self.funda is not None:
            from concurrent.futures import ThreadPoolExecutor

            def one(sym: str) -> tuple[str, dict]:
                a = self.funda.analysis(sym)
                return sym, (a.get("snapshot") or {}) if a and not a.get("error") else {}
            with ThreadPoolExecutor(max_workers=6) as ex:
                snaps = dict(ex.map(one, [c.symbol for c in rows]))
        out = []
        for c in rows:
            qq = q.get(c.symbol)
            sn = snaps.get(c.symbol, {})
            out.append({"symbol": c.symbol, "name": c.name, "self": c.symbol == symbol, "cmp": qq.ltp if qq else None, "change_pct": qq.change_pct if qq else None,  # noqa: E501
                        "pe": sn.get("pe"), "market_cap_cr": sn.get("market_cap_cr"), "roe": sn.get("roe"), "roce": sn.get("roce"), "net_margin": sn.get("net_margin"),  # noqa: E501
                        "revenue_cagr_3y": sn.get("revenue_cagr_3y"), "eps_cagr_3y": sn.get("eps_cagr_3y"), "debt_equity": sn.get("debt_equity")})  # noqa: E501
        return {"symbol": symbol, "sector": me.sector, "rows": out, "valuation": self.funda is not None}

    # ---- calendars, flows, news ---------------------------------------------------------
    def ai_rank(self, index: str | None = None, limit: int = 50, mode: str = "short") -> dict:
        return self.ai.rank(index, limit, mode)

    def ai_radar(self, index: str | None = None, days: int = 5, mode: str = "short") -> dict:
        return self.ai.radar(index, days, mode)

    def ai_track(self, index: str | None = None, mode: str = "short") -> dict:
        return self.track.report(index, mode)

    def bars(self, symbol: str, range_key: str = "3m") -> dict:
        return chart_bars(self.council.bars, symbol.upper(), range_key)

    def council_run(self, symbol: str, horizon: str = "1d") -> dict:
        return self.council.run(symbol, horizon)
