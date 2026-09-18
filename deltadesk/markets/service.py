"""Read model for the markets page: quotes across asset classes, screener, heat-map stats, watchlists,
calendars, institutional flows, IPOs and news."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import date

from deltadesk.markets import calendar as cal
from deltadesk.markets import ipo, universe
from deltadesk.markets.news import NewsService
from deltadesk.markets.quotes import QuoteProvider, SyntheticQuotes
from deltadesk.markets.watchlist import Watchlist


class MarketsService:
    def __init__(self, quotes: QuoteProvider | None = None, watchlist: Watchlist | None = None,
                 news: NewsService | None = None) -> None:
        self.quotes = quotes or SyntheticQuotes()
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

    def etfs(self) -> list[dict]:
        q = self.quotes.quotes([e[0] for e in universe.ETFS])
        return [{"symbol": s, "name": n, "tracks": t, "quote": q[s].json() if s in q else None} for s, n, t, _ in universe.ETFS]

    def forex(self) -> list[dict]:
        q = self.quotes.quotes([f[0] for f in universe.FX])
        return [{"symbol": s, "name": n, "detail": d, "quote": q[s].json() if s in q else None} for s, n, d, _ in universe.FX]

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
        out.sort(key=lambda r: (not r["key"].startswith(q), r["key"]))
        return out[:limit]

    def watchlists(self) -> dict:
        keys = sorted({k for v in self.watchlist.lists.values() for k in v})
        q = self.quotes.quotes(keys)

        def row(k: str) -> dict:
            name, kind, sector = self._name(k)
            return {"key": k, "name": name, "kind": kind, "sector": sector, "quote": q[k].json() if k in q else None}
        return {"lists": {name: [row(k) for k in keys_] for name, keys_ in self.watchlist.lists.items()}}

    # ---- calendars, flows, ipo, news ---------------------------------------------------------
    @staticmethod
    def ipos() -> dict:
        return ipo.load()

    @staticmethod
    def calendar() -> dict:
        return cal.financial_calendar()

    @staticmethod
    def earnings() -> dict:
        return cal.earnings()

    @staticmethod
    def flows() -> dict:
        return cal.flows()

    def headlines(self, force: bool = False) -> dict:
        return self.news.headlines(force=force)

    def trending(self) -> dict:
        return self.news.trending()
