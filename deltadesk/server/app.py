"""FastAPI surface: desk state, decisions, approve / reject, kill switch, WebSocket stream, and the
markets read model (quotes across asset classes, screener, heat map, watchlists, calendars, flows, IPOs, news)."""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

from deltadesk.markets import universe
from deltadesk.markets.service import MarketsService
from deltadesk.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[2]


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

    # ---- pages ----------------------------------------------------------------------------
    @app.get("/")
    async def index():
        return FileResponse(ROOT / "index.html")

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
    @app.get("/markets/indices")
    async def m_indices():
        return JSONResponse(markets.indices())

    @app.get("/markets/index/{code}")
    async def m_index(code: str):
        out = markets.index(code)
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

    @app.get("/markets/futures")
    async def m_futures():
        return JSONResponse(markets.futures())

    @app.get("/markets/etf")
    async def m_etf():
        return JSONResponse(markets.etfs())

    @app.get("/markets/forex")
    async def m_forex():
        return JSONResponse(markets.forex())

    # ---- markets: tools --------------------------------------------------------------------
    @app.get("/markets/screener")
    async def m_screener(index: str | None = None, sector: str | None = None, chg_min: float | None = None,
                         chg_max: float | None = None, px_min: float | None = None, px_max: float | None = None,
                         sort: str = "change_pct", desc: bool = True, limit: int = 100):
        return JSONResponse(markets.screener(index, sector, chg_min, chg_max, px_min, px_max, sort, desc, limit))

    @app.get("/markets/search")
    async def m_search(q: str = ""):
        return JSONResponse(markets.search(q))

    @app.get("/markets/watchlist")
    async def m_watchlist():
        return JSONResponse(markets.watchlists())

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
