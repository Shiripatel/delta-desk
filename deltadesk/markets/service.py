"""Read model for the markets page: quotes across asset classes, screener, heat-map stats, watchlists,
calendars, institutional flows, IPOs and news."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import date

from deltadesk.markets import calendar as cal
from deltadesk.markets import ipo, universe
from deltadesk.markets.ai_rank import AiRanker, SyntheticHistory
from deltadesk.markets.chat import DeskAssistant
from deltadesk.markets.council import Council, SyntheticBars, chart_bars
from deltadesk.markets.news import NewsService
from deltadesk.markets.quotes import QuoteProvider, SyntheticQuotes
from deltadesk.markets.watchlist import Watchlist, presets


class MarketsService:
    def __init__(self, quotes: QuoteProvider | None = None, watchlist: Watchlist | None = None,
                 news: NewsService | None = None, ai: AiRanker | None = None, council: Council | None = None) -> None:
        self.quotes = quotes or SyntheticQuotes()
        self.ai = ai or AiRanker(SyntheticHistory())
        self.council = council or Council(SyntheticBars())
        self.assistant = DeskAssistant(self)
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
    def futures(self, today: date | None = None) -> list[dict]:
        cons = universe.futures_contracts(today or date.today())
        q = self.quotes.quotes([c["key"] for c in cons] + [c["underlying"] for c in cons])
        out = []
        for c in cons:
            fq, sq = q.get(c["key"]), q.get(c["underlying"])
            basis = round(fq.ltp - sq.ltp, 2) if fq and sq else None
            out.append({**c, "quote": fq.json() if fq else None, "spot": sq.ltp if sq else None, "basis": basis,
                        "underlying_name": universe.INDICES[c["underlying"]].name})
        return out

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

    def etfs(self) -> list[dict]:
        q = self.quotes.quotes([e[0] for e in universe.ETFS])
        return [{"symbol": s, "name": n, "tracks": t, "quote": q[s].json() if s in q else None} for s, n, t, _ in universe.ETFS]

    def forex(self) -> list[dict]:
        q = self.quotes.quotes([f[0] for f in universe.FX])
        return [{"symbol": s, "name": n, "detail": d, "quote": q[s].json() if s in q else None} for s, n, d, _ in universe.FX]

    def forex_market(self) -> dict:
        """INR crosses, world majors, and a currency-strength meter (average day change of each currency vs the others)."""
        inr_keys = [f[0] for f in universe.FX]
        world_keys = [f[0] for f in universe.FX_WORLD]
        q = self.quotes.quotes(inr_keys + world_keys + ["DXY"])
        inr = [{"key": s, "name": n, "detail": d, "base": universe.FX_INR[s][0], "quote_ccy": "INR", "decimals": 4, "group": "inr",
                "quote": q[s].json() if s in q else None} for s, n, d, _ in universe.FX]
        world = [{"key": k, "name": n, "detail": f"{b}/{c}", "base": b, "quote_ccy": c, "decimals": d, "group": "world",
                  "quote": q[k].json() if k in q else None} for k, n, _, d, b, c, _ in universe.FX_WORLD]
        strength: dict[str, list[float]] = {}
        for p in inr + world:
            qq = p["quote"]
            if not qq:
                continue
            strength.setdefault(p["base"], []).append(qq["change_pct"])
            strength.setdefault(p["quote_ccy"], []).append(-qq["change_pct"])
        meter = sorted(({"ccy": c, "score": round(sum(v) / len(v), 3), "pairs": len(v)} for c, v in strength.items()), key=lambda x: -x["score"])  # noqa: E501
        dxy = q.get("DXY")
        return {"inr": inr, "world": world, "strength": meter, "dxy": dxy.json() if dxy else None,
                "note": "Strength is the average day change of a currency across the pairs shown, positive means it strengthened. Not advice."}  # noqa: E501

    def screener(self, index: str | None = None, sector: str | None = None, chg_min: float | None = None,
                 chg_max: float | None = None, px_min: float | None = None, px_max: float | None = None,
                 sort: str = "change_pct", desc: bool = True, limit: int = 100) -> dict:
        if index and index.upper() in universe.INDICES:
            cons = {c.symbol: c for c in universe.INDICES[index.upper()].constituents}
        else:
            cons = universe.all_symbols()
        q = self.quotes.quotes(list(cons))
        rows = []
        for s, c in cons.items():
            qq = q.get(s)
            if qq is None:
                continue
            if sector and c.sector.lower() != sector.lower():
                continue
            if chg_min is not None and qq.change_pct < chg_min:
                continue
            if chg_max is not None and qq.change_pct > chg_max:
                continue
            if px_min is not None and qq.ltp < px_min:
                continue
            if px_max is not None and qq.ltp > px_max:
                continue
            pos = round((qq.ltp - qq.low) / (qq.high - qq.low), 2) if qq.high > qq.low else 0.5
            rows.append({**asdict(c), "quote": qq.json(), "range_pos": pos})
        key = (lambda r: r["quote"].get(sort, 0)) if sort in ("change_pct", "ltp", "volume", "change") else (lambda r: r.get(sort, 0))
        rows.sort(key=key, reverse=desc)
        sectors = sorted({c.sector for c in universe.all_symbols().values()})
        return {"count": len(rows), "entries": rows[:limit], "sectors": sectors, "indices": list(universe.INDICES)}

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

    @staticmethod
    def watchlist_presets() -> list[dict]:
        return presets()

    def global_market(self) -> dict:
        """World map read model: key indices placed by city, grouped by region, plus futures, commodities, FX, bonds, crypto."""
        keys = [m[0] for m in universe.WORLD_MAP] + [k for _, ks in universe.GLOBAL_SECTIONS for k in ks]
        q = self.quotes.quotes(sorted(set(keys)))

        def item(k: str) -> dict:
            if k in universe.INDICES:
                name, dec, unit = universe.INDICES[k].name, 2, "index"
            elif k in universe.GLOBAL_BY_KEY:
                g = universe.GLOBAL_BY_KEY[k]
                name, dec, unit = g[1], g[3], g[4]
            elif k in universe.FX_WORLD_BY_KEY:
                f = universe.FX_WORLD_BY_KEY[k]
                name, dec, unit = f[1], f[3], f"{f[4]}/{f[5]}"
            else:
                name, dec, unit = k, 2, ""
            return {"key": k, "name": name, "decimals": dec, "unit": unit, "quote": q[k].json() if k in q else None}
        markers = [{**item(m[0]), "city": m[1], "lat": m[2], "lon": m[3], "region": m[4]} for m in universe.WORLD_MAP]
        return {"regions": [{"code": c, "name": n} for c, n in universe.REGIONS], "markers": markers,
                "sections": [{"name": n, "items": [item(k) for k in ks]} for n, ks in universe.GLOBAL_SECTIONS],
                "source": self.quotes.name, "delay_min": getattr(self.quotes, "delay_min", 0)}

    # ---- calendars, flows, ipo, news ---------------------------------------------------------
    def ipos(self) -> dict:
        return ipo.load(quotes=self.quotes.quotes)

    def ipo_detail(self, slug: str) -> dict | None:
        try:
            heads = [{"title": h.get("title", ""), "description": h.get("description", ""), "impact": h.get("impact")} for h in self.news.feed(limit=400)["entries"]]  # noqa: E501
        except Exception:  # noqa: BLE001 - news is optional for the agent
            heads = []
        return ipo.detail(slug, quotes=self.quotes.quotes, headlines=heads)

    def ipo_performance(self, year: int | None = None, segment: str | None = None) -> dict:
        return ipo.performance(year, segment or None, quotes=self.quotes.quotes)

    @staticmethod
    def calendar() -> dict:
        return cal.financial_calendar()

    @staticmethod
    def earnings() -> dict:
        return cal.earnings()

    @staticmethod
    def flows() -> dict:
        return cal.flows()

    def ai_rank(self, index: str | None = None, limit: int = 50, mode: str = "short") -> dict:
        return self.ai.rank(index, limit, mode)

    def ai_radar(self, index: str | None = None, days: int = 5, mode: str = "short") -> dict:
        return self.ai.radar(index, days, mode)

    def bars(self, symbol: str, range_key: str = "3m") -> dict:
        return chart_bars(self.council.bars, symbol.upper(), range_key)

    def council_run(self, symbol: str, horizon: str = "1d") -> dict:
        return self.council.run(symbol, horizon)

    def headlines(self, force: bool = False) -> dict:
        return self.news.headlines(force=force)

    def trending(self) -> dict:
        return self.news.trending()
