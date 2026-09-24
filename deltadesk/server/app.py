"""FastAPI surface: desk state, decisions, approve / reject, kill switch, WebSocket stream, and the
markets read model (quotes across asset classes, screener, heat map, watchlists, calendars, flows, IPOs, news)."""
from __future__ import annotations

import asyncio
import json
import os
import secrets
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
from deltadesk.markets.watchlist import WatchlistError
from deltadesk.pipeline import Pipeline
from deltadesk.server.traffic import Traffic

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
PAGES = WEB / "pages"
PAGE_ROUTES = {"/": "home.html", "/watchlist": "watchlist.html", "/heatmap": "heatmap.html", "/news": "news.html", "/ipo": "ipo.html",
               "/ipo/{slug}": "ipo_detail.html", "/forex": "forex.html", "/global": "global.html", "/investors": "investors.html", "/desk": "agents.html", "/sniper": "sniper.html",  # noqa: E501
               "/analysis": "analysis.html", "/beta": "beta.html", "/legal": "legal.html"}


class AgentChatIn(BaseModel):
    symbol: str
    mode: str = "fundamental"
    messages: list[dict] = []


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


def _safe_send(notifier, to: str, text: str) -> None:
    try:
        notifier.send(to, text)
    except Exception:  # noqa: BLE001 - a failed owner ping must never fail the sign-up
        pass


def create_app(pipeline: Pipeline, cycles: int | None = None, markets: MarketsService | None = None,
               waitlist: Waitlist | None = None, alerts: Alerts | None = None, alert_interval: float = 60.0,
               traffic_log_store: Traffic | None = None) -> FastAPI:
    markets = markets or MarketsService()
    waitlist = waitlist or Waitlist()
    traffic = traffic_log_store or Traffic()
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
    app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")

    @app.middleware("http")
    async def traffic_log(request, call_next):
        resp = await call_next(request)
        if request.method == "GET" and resp.status_code == 200 and traffic.is_page(request.url.path):
            ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "").split(",")[0].strip()
            await asyncio.to_thread(traffic.record, request.url.path, ip, request.headers.get("user-agent", ""), request.headers.get("referer", ""))  # noqa: E501
        return resp

    @app.get("/admin/traffic")
    async def admin_traffic(token: str = "", days: int = 30):
        expected = os.environ.get("DD_ADMIN_TOKEN", "")
        if not expected or not secrets.compare_digest(token, expected):
            raise HTTPException(401, "set DD_ADMIN_TOKEN in .env and pass ?token=")
        return JSONResponse(await asyncio.to_thread(traffic.summary, days))

    @app.middleware("http")
    async def cache_policy(request, call_next):
        """Pages always revalidate (a stale cached page shows an old nav); static assets may be cached for a minute."""
        resp = await call_next(request)
        path = request.url.path
        if path.startswith("/static/"):
            resp.headers["Cache-Control"] = "public, max-age=60"
        elif resp.headers.get("content-type", "").startswith("text/html"):
            resp.headers["Cache-Control"] = "no-cache"
        return resp

    # ---- pages ----------------------------------------------------------------------------
    def _page(name: str):
        async def handler(slug: str = "") -> FileResponse:   # slug only matters for /ipo/{slug}; the page reads it from the URL
            return FileResponse(PAGES / name)
        return handler

    for _path, _file in PAGE_ROUTES.items():
        app.add_api_route(_path, _page(_file), methods=["GET"], name=_file[:-5])

    @app.get("/healthz")
    async def healthz():
        return JSONResponse({"ok": True, "quotes": markets.quotes.name, "mode": pipeline.s.mode})

    @app.get("/chart")
    async def chart_page():
        return RedirectResponse("/analysis", status_code=307)

    @app.get("/markets/forex-market")
    async def m_forex_market():
        return JSONResponse(await asyncio.to_thread(markets.forex_market))

    @app.post("/waitlist")
    async def waitlist_join(body: WaitlistIn):
        out = waitlist.join(body.name, body.email, body.phone, body.interests, body.experience, body.whatsapp_ok)
        owner = os.environ.get("DD_OWNER_CHAT", "")
        if out.get("ok") and not out.get("duplicate") and owner:
            parts = [f"New Delta Desk waitlist sign-up #{out.get('position')}: {body.name} · {body.email}", body.phone or "",
                     ", ".join(body.interests) if body.interests else "", body.experience or ""]
            text = " · ".join(x for x in parts if x)
            asyncio.get_running_loop().run_in_executor(None, lambda: _safe_send(alerts.notifier, owner, text))
        return JSONResponse(out)

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

    @app.get("/markets/fundamentals/{symbol}")
    async def m_fundamentals(symbol: str, refresh: bool = False):
        out = await asyncio.to_thread(markets.fundamentals, symbol, refresh)
        if out is None:
            raise HTTPException(404, f"no financial statements for {symbol}")
        return JSONResponse(out)

    @app.get("/markets/technicals/{symbol}")
    async def m_technicals(symbol: str, tf: str = "daily"):
        return JSONResponse(await asyncio.to_thread(markets.technicals, symbol, tf))

    @app.get("/markets/peers/{symbol}")
    async def m_peers(symbol: str):
        return JSONResponse(await asyncio.to_thread(markets.peers, symbol))

    @app.get("/markets/global")
    async def m_global():
        return JSONResponse(await asyncio.to_thread(markets.global_market))

    @app.get("/markets/investors")
    async def m_investors():
        return JSONResponse(await asyncio.to_thread(markets.investors))

    @app.get("/markets/watchlist/stats")
    async def m_watchlist_stats(symbols: str = ""):
        keys = [k.strip().upper() for k in symbols.split(",") if k.strip()]
        return JSONResponse(await asyncio.to_thread(markets.wl_stats, keys))

    @app.get("/agent/model")
    async def agent_model():
        return JSONResponse({"provider": markets.agent.llm.provider, "model": markets.agent.llm.model, "label": markets.agent.llm.label(), "available": markets.agent.llm.available})  # noqa: E501

    @app.post("/agent/chat")
    async def agent_chat(body: AgentChatIn):
        return JSONResponse(await asyncio.to_thread(markets.agent.reply, body.symbol, body.mode, body.messages))

    @app.get("/markets/watchlist/presets")
    async def m_watchlist_presets():
        return JSONResponse(markets.watchlist_presets())

    @app.post("/markets/watchlist/preset/{code}")
    async def m_watchlist_preset(code: str):
        try:
            loaded = markets.watchlist.load_preset(code)
        except WatchlistError as exc:
            raise HTTPException(409, str(exc)) from exc
        out = await asyncio.to_thread(markets.watchlists)
        out["loaded"] = loaded
        return JSONResponse(out)

    @app.post("/markets/watchlist/{name}/rename/{new}")
    async def m_watchlist_rename(name: str, new: str):
        try:
            markets.watchlist.rename(name, new)
        except WatchlistError as exc:
            raise HTTPException(409, str(exc)) from exc
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
        try:
            markets.watchlist.create(name)
        except WatchlistError as exc:
            raise HTTPException(409, str(exc)) from exc
        return JSONResponse(await asyncio.to_thread(markets.watchlists))

    @app.delete("/markets/watchlist/{name}")
    async def m_watchlist_delete(name: str):
        markets.watchlist.delete(name)
        return JSONResponse(markets.watchlists())

    @app.post("/markets/watchlist/{name}/{symbol}")
    async def m_watchlist_add(name: str, symbol: str):
        symbol = symbol.upper() if not symbol.startswith("FUT:") else symbol
        if not markets.known(symbol):
            raise HTTPException(404, f"unknown symbol {symbol}")
        try:
            markets.watchlist.add(name, symbol)
        except WatchlistError as exc:
            raise HTTPException(409, str(exc)) from exc
        return JSONResponse(await asyncio.to_thread(markets.watchlists))

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
