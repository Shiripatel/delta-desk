"""FastAPI surface: desk state, decisions, approve / reject, kill switch, WebSocket stream, and the
markets read model (quotes across asset classes, screener, heat map, watchlists, calendars, flows, IPOs, news)."""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from deltadesk.beta import Alerts, Waitlist
from deltadesk.markets import universe
from deltadesk.markets.logos import DOMAINS
from deltadesk.markets.service import MarketsService
from deltadesk.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[2]


class ChatIn(BaseModel):
    question: str = ""
    symbol: str | None = None
    news_id: str | None = None


class WaitlistIn(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    interests: list[str] = []
    experience: str = ""
    whatsapp_ok: bool = False


class AlertIn(BaseModel):
    contact: str = ""
    symbol: str = ""
    kind: str = "price_move"
    value: float | None = None
    horizon: str = "1d"


class ContactIn(BaseModel):
    contact: str = ""


def _dump(x):
    if hasattr(x, "model_dump"):
        return x.model_dump(mode="json")
    return x


def create_app(pipeline: Pipeline, cycles: int | None = None, markets: MarketsService | None = None,
               waitlist: Waitlist | None = None, alerts: Alerts | None = None, alert_interval: float = 60.0) -> FastAPI:
    markets = markets or MarketsService()
    waitlist = waitlist or Waitlist()
    alerts = alerts or Alerts(markets)

    async def alert_loop():
        while True:
            await asyncio.sleep(alert_interval)
            try:
                await asyncio.to_thread(alerts.evaluate)
            except Exception:  # noqa: BLE001 - never let the loop die
                pass

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(pipeline.run(cycles))
        loop = asyncio.create_task(alert_loop())
        yield
        task.cancel()
        loop.cancel()

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

    @app.get("/analysis")
    async def analysis_page():
        return FileResponse(ROOT / "analysis.html")

    @app.get("/chart")
    async def chart_page():
        return RedirectResponse("/analysis", status_code=307)

    @app.get("/forex")
    async def forex_page():
        return FileResponse(ROOT / "forex.html")

    @app.get("/markets/forex-market")
    async def m_forex_market():
        return JSONResponse(await asyncio.to_thread(markets.forex_market))

    @app.get("/beta")
    async def beta_page():
        return FileResponse(ROOT / "beta.html")

    @app.get("/legal")
    async def legal_page():
        return FileResponse(ROOT / "legal.html")

    @app.post("/waitlist")
    async def waitlist_join(body: WaitlistIn):
        return JSONResponse(waitlist.join(body.name, body.email, body.phone, body.interests, body.experience, body.whatsapp_ok))

    @app.get("/waitlist/stats")
    async def waitlist_stats():
        return JSONResponse(waitlist.stats())

    @app.get("/alerts")
    async def alerts_list(contact: str = ""):
        return JSONResponse(alerts.for_contact(contact) if contact else [])

    @app.post("/alerts")
    async def alerts_add(body: AlertIn):
        return JSONResponse(alerts.add(body.contact, body.kind, body.symbol, body.value, body.horizon))

    @app.delete("/alerts/{rule_id}")
    async def alerts_remove(rule_id: str):
        return JSONResponse({"ok": alerts.remove(rule_id)})

    @app.get("/alerts/log")
    async def alerts_log():
        return JSONResponse(alerts.log())

    @app.get("/alerts/channel")
    async def alerts_channel():
        n = alerts.notifier.name
        note = {"whatsapp": "WhatsApp Cloud API configured. Business-initiated messages need an approved template outside the 24-hour window.",  # noqa: E501
                "telegram": "Telegram bot configured. Message the bot once, then use your chat id as the contact.",
                "dry-run": "No WhatsApp or Telegram credentials yet: alerts are evaluated and logged here, not delivered. Set WHATSAPP_TOKEN + WHATSAPP_PHONE_ID or TELEGRAM_BOT_TOKEN in .env."}[n]  # noqa: E501
        return JSONResponse({"channel": n, "note": note, "kinds": list(__import__("deltadesk.beta", fromlist=["KINDS"]).KINDS)})

    @app.post("/alerts/test")
    async def alerts_test(body: ContactIn):
        return JSONResponse(await asyncio.to_thread(alerts.test, body.contact))

    @app.post("/alerts/run")
    async def alerts_run():
        return JSONResponse(await asyncio.to_thread(alerts.evaluate))

    @app.get("/ipo")
    async def ipo_page():
        return FileResponse(ROOT / "ipo.html")

    @app.get("/ipo/{slug}")
    async def ipo_detail_page(slug: str):
        return FileResponse(ROOT / "ipo_detail.html")

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

    @app.get("/limits")
    async def limits():
        return JSONResponse(pipeline.s.limits.model_dump())

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

    @app.get("/markets/domains")
    async def m_domains():
        return JSONResponse(DOMAINS)

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
        return JSONResponse(await asyncio.to_thread(markets.ipos))

    @app.get("/markets/ipo-performance")
    async def m_ipo_perf(year: int | None = None, segment: str = ""):
        return JSONResponse(await asyncio.to_thread(markets.ipo_performance, year, segment))

    @app.get("/markets/ipo/{slug}")
    async def m_ipo_detail(slug: str):
        out = await asyncio.to_thread(markets.ipo_detail, slug)
        if out is None:
            raise HTTPException(404, f"unknown ipo {slug}")
        return JSONResponse(out)

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
