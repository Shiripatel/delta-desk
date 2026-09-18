"""FastAPI surface: desk state, decisions, approve / reject, kill switch, WebSocket stream, and the
markets read model (quotes across asset classes, screener, heat map, watchlists, calendars, flows, IPOs, news)."""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from deltadesk.markets import universe
from deltadesk.markets.service import MarketsService
from deltadesk.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[2]


class ChatIn(BaseModel):
    question: str = ""
    symbol: str | None = None
    news_id: str | None = None


def _dump(x):
    if hasattr(x, "model_dump"):
        return x.model_dump(mode="json")
    return x


def create_app(pipeline: Pipeline, cycles: int | None = None, markets: MarketsService | None = None) -> FastAPI:
    markets = markets or MarketsService()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(pipeline.run(cycles))
        yield
        task.cancel()

    app = FastAPI(title="Delta Desk", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

    # ---- pages ----------------------------------------------------------------------------
    @app.get("/")
    async def home():
        return FileResponse(ROOT / "home.html")

    @app.get("/desk")
    async def desk():
        return FileResponse(ROOT / "agents.html")

    @app.get("/news")
    async def news_page():
        return FileResponse(ROOT / "news.html")

    @app.get("/chart")
    async def chart_page():
        return FileResponse(ROOT / "chart.html")

    @app.get("/ipo")
    async def ipo_page():
        return FileResponse(ROOT / "ipo.html")

    @app.get("/sniper")
    async def sniper():
        return FileResponse(ROOT / "sniper.html")

    @app.get("/prototype")
    async def prototype():
        return FileResponse(ROOT / "prototype" / "index.html")

    @app.get("/markets")
    async def markets_page():
        return FileResponse(ROOT / "markets.html")

    # ---- desk -----------------------------------------------------------------------------
    @app.get("/state")
    async def state():
        return JSONResponse({k: _dump(v) for k, v in pipeline.bus.latest.items()})

    @app.get("/decisions")
    async def decisions():
        return JSONResponse([_dump(d) for d in pipeline.decisions.values()])

    @app.post("/decisions/{did}/approve")
    async def approve(did: str):
        if did not in pipeline.decisions:
            raise HTTPException(404)
        return JSONResponse(_dump(pipeline.approve(did)))

    @app.post("/decisions/{did}/reject")
    async def reject(did: str):
        if did not in pipeline.decisions:
            raise HTTPException(404)
        return JSONResponse(_dump(pipeline.reject(did)))

    @app.post("/kill")
    async def kill():
        return JSONResponse(_dump(pipeline.kill()))

    @app.websocket("/stream")
    async def stream(ws: WebSocket):
        await ws.accept()
        q = pipeline.bus.subscribe("*")
        try:
            for topic, msg in ((k, v) for k, v in pipeline.bus.latest.items()):
                await ws.send_text(json.dumps({"topic": topic, "data": _dump(msg)}, default=str))
            while True:
                topic, msg = await q.get()
                await ws.send_text(json.dumps({"topic": topic, "data": _dump(msg)}, default=str))
        except WebSocketDisconnect:
            pass
        finally:
            pipeline.bus.unsubscribe("*", q)

    # ---- markets: real-time quotes ----------------------------------------------------------
    @app.get("/markets/source")
    async def m_source():
        q = markets.quotes
        return JSONResponse({"name": q.name, "delay_min": getattr(q, "delay_min", 0), "note": getattr(q, "note", ""),
                             "errors": len(getattr(q, "errors", {}) or {}), "history": markets.ai.history.name})

    @app.get("/markets/indices")
    async def m_indices():
        return JSONResponse(await asyncio.to_thread(markets.indices))

    @app.get("/markets/index/{code}")
    async def m_index(code: str):
        out = await asyncio.to_thread(markets.index, code)
        if out is None:
            raise HTTPException(404, f"unknown index {code}")
        return JSONResponse(out)

    @app.get("/markets/options")
    async def m_options():
        """The desk's option chain: latest Snapshot and ChainStats from the pipeline (paper feed or broker)."""
        snap, stats = pipeline.bus.latest.get("snapshot"), pipeline.bus.latest.get("chain")
        if snap is None:
            return JSONResponse({"ready": False, "note": "pipeline warming up"})
        s = _dump(snap)
        return JSONResponse({"ready": True, "underlying": s["underlying"], "ts": s["ts"], "spot": s["spot"], "fut": s["fut"],
                            "vix": s["vix"], "expiry": s["expiry"], "atm": s["atm"], "chain": s["chain"],
                            "stats": _dump(stats) if stats else None, "feed": pipeline.feed.name})

    @app.get("/markets/indicators")
    async def m_indicators():
        return JSONResponse(await asyncio.to_thread(markets.indicators))

    @app.get("/markets/futures")
    async def m_futures():
        return JSONResponse(await asyncio.to_thread(markets.futures))

    @app.get("/markets/etf")
    async def m_etf():
        return JSONResponse(await asyncio.to_thread(markets.etfs))

    @app.get("/markets/forex")
    async def m_forex():
        return JSONResponse(await asyncio.to_thread(markets.forex))

    # ---- markets: tools --------------------------------------------------------------------
    @app.get("/markets/screener")
    async def m_screener(index: str | None = None, sector: str | None = None, chg_min: float | None = None,
                         chg_max: float | None = None, px_min: float | None = None, px_max: float | None = None,
                         sort: str = "change_pct", desc: bool = True, limit: int = 100):
        return JSONResponse(await asyncio.to_thread(markets.screener, index, sector, chg_min, chg_max, px_min, px_max, sort, desc, limit))

    @app.get("/markets/search")
    async def m_search(q: str = ""):
        return JSONResponse(markets.search(q))

    @app.get("/markets/watchlist")
    async def m_watchlist():
        return JSONResponse(await asyncio.to_thread(markets.watchlists))

    @app.get("/markets/ai")
    async def m_ai(index: str | None = None, limit: int = 50, mode: str = "short"):
        return JSONResponse(await asyncio.to_thread(markets.ai_rank, index, limit, mode))

    @app.get("/markets/bars")
    async def m_bars(symbol: str = "NIFTY50", range: str = "3m"):  # noqa: A002
        return JSONResponse(await asyncio.to_thread(markets.bars, symbol, range))

    @app.get("/news/feed")
    async def n_feed(symbols: str = "", impact: str = "", since: float = 0.0, limit: int = 80):
        syms = [x for x in symbols.split(",") if x]
        return JSONResponse(await asyncio.to_thread(markets.news.feed, syms or None, impact or None, since, limit))

    @app.get("/news/item")
    async def n_item(id: str):  # noqa: A002
        out = await asyncio.to_thread(markets.news.item, id)
        if out is None:
            raise HTTPException(404, "unknown story")
        return JSONResponse(out)

    @app.post("/chat")
    async def chat(body: ChatIn):
        return JSONResponse(await asyncio.to_thread(markets.assistant.answer, body.question, body.symbol, body.news_id))

    @app.get("/markets/council")
    async def m_council(symbol: str = "HDFCBANK", horizon: str = "1d"):
        return JSONResponse(await asyncio.to_thread(markets.council_run, symbol, horizon))

    @app.get("/markets/radar")
    async def m_radar(index: str | None = None, days: int = 5, mode: str = "short"):
        return JSONResponse(await asyncio.to_thread(markets.ai_radar, index, max(2, min(10, days)), mode))

    @app.post("/markets/watchlist/{name}")
    async def m_watchlist_create(name: str):
        markets.watchlist.create(name)
        return JSONResponse(markets.watchlists())

    @app.delete("/markets/watchlist/{name}")
    async def m_watchlist_delete(name: str):
        markets.watchlist.delete(name)
        return JSONResponse(markets.watchlists())

    @app.post("/markets/watchlist/{name}/{symbol}")
    async def m_watchlist_add(name: str, symbol: str):
        symbol = symbol.upper() if not symbol.startswith("FUT:") else symbol
        if not markets.known(symbol):
            raise HTTPException(404, f"unknown symbol {symbol}")
        markets.watchlist.add(name, symbol)
        return JSONResponse(markets.watchlists())

    @app.delete("/markets/watchlist/{name}/{symbol}")
    async def m_watchlist_remove(name: str, symbol: str):
        markets.watchlist.remove(name, symbol.upper() if not symbol.startswith("FUT:") else symbol)
        return JSONResponse(markets.watchlists())

    @app.get("/markets/earnings")
    async def m_earnings():
        return JSONResponse(markets.earnings())

    @app.get("/markets/flows")
    async def m_flows():
        return JSONResponse(markets.flows())

    @app.get("/markets/ipo")
    async def m_ipo():
        return JSONResponse(markets.ipos())

    @app.post("/markets/refresh-constituents")
    async def m_refresh():
        done = await asyncio.to_thread(universe.refresh_from_nse)
        return JSONResponse({"refreshed": done})

    # ---- markets: news ---------------------------------------------------------------------
    @app.get("/markets/news")
    async def m_news(force: bool = False):
        return JSONResponse(await asyncio.to_thread(markets.headlines, force))

    @app.get("/markets/trending")
    async def m_trending():
        return JSONResponse(await asyncio.to_thread(markets.trending))

    @app.get("/markets/calendar")
    async def m_calendar():
        return JSONResponse(markets.calendar())

    return app
