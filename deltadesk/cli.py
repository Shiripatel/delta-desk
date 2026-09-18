"""deltadesk run   -> drive the pipeline in the terminal (synthetic feed by default)
deltadesk serve  -> same, plus the HTTP / WebSocket server on :8000
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from deltadesk.config import Settings
from deltadesk.feeds import make_feed
from deltadesk.pipeline import Pipeline


def _printer(verbose: bool):
    def on_event(topic: str, msg) -> None:
        if topic == "log":
            print(f"  · {msg}")
        elif topic == "decision":
            t, r = msg.trade, msg.risk
            legs = " + ".join(f"{l.side.value} {l.lots}x {l.symbol} @ {l.limit}" for l in t.legs)
            print(f"\n{msg.id} [{msg.state}] {t.structure} conf {t.confidence:.2f} (thr {msg.threshold})")
            print(f"  {legs}")
            print(f"  stop {t.stop} target {t.target} · margin {r.margin_after:,.0f} max loss {r.max_loss:,.0f} "
                  f"Δ {r.net_delta:+.2f} vega {r.net_vega:+,.0f}")
            print(f"  why: {t.why}\n")
        elif topic == "cycle" and verbose:
            ok = sum(a.ok for a in msg.agents)
            summ = " | ".join(f"{a.name} {a.summary}" for a in msg.agents if a.ok)
            print(f"{msg.ts:%H:%M:%S} cycle {msg.seq:>5} {msg.ms:6.1f} ms {ok}/{len(msg.agents)} ok  {summ}")
        elif topic == "orders" and msg.positions and verbose:
            print("    book: " + ", ".join(f"{p.symbol} {p.qty:+d} @ {p.avg:.2f} ltp {p.ltp:.2f} P&L {p.pnl:+,.0f}"
                                          for p in msg.positions))
    return on_event


def _build(args) -> Pipeline:
    overrides = {}
    if args.auto_approve:
        overrides["auto_approve"] = True
    if args.cycle:
        overrides["cycle_seconds"] = args.cycle
    settings = Settings(**overrides)
    kw = {}
    if settings.feed == "synthetic":
        kw = {"scenario": args.scenario, "seed": args.seed, "speed": 0.0 if args.fast else args.speed}
    feed = make_feed(settings, **kw)
    return Pipeline(settings, feed, on_event=_printer(args.verbose))


def _instruments(args) -> None:
    settings = Settings(**({"underlying": args.underlying} if args.underlying else {}))
    feed = make_feed(settings)

    async def go():
        await feed.connect()
        rows = await feed.instruments(settings.underlying)
        for i in rows:
            print(f"{i.token:32s} {i.symbol:30s} {i.kind.value:4s} {i.strike or '':>8} {i.expiry or ''} lot {i.lot_size}")
        print(f"{len(rows)} instruments from feed {feed.name}")
        await feed.close()

    asyncio.run(go())


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="deltadesk")
    sub = p.add_subparsers(dest="cmd", required=True)
    lg = sub.add_parser("login", help="broker login; caches today's access token under data/")
    lg.add_argument("broker", choices=["upstox"])
    lg.add_argument("--no-browser", action="store_true")
    im = sub.add_parser("instruments", help="show what the feed would subscribe to today")
    im.add_argument("--underlying", default=None)
    for name in ("run", "serve"):
        q = sub.add_parser(name)
        q.add_argument("--scenario", default="range", choices=["range", "trend_up", "trend_down"])
        q.add_argument("--seed", type=int, default=7)
        q.add_argument("--speed", type=float, default=60.0, help="synthetic: market seconds per real second")
        q.add_argument("--fast", action="store_true", help="synthetic: no sleeping at all")
        q.add_argument("--cycle", type=float, default=None, help="market seconds per pipeline cycle")
        q.add_argument("--cycles", type=int, default=None, help="stop after N cycles")
        q.add_argument("--auto-approve", action="store_true")
        q.add_argument("-v", "--verbose", action="store_true")
        if name == "serve":
            q.add_argument("--port", type=int, default=8000)
            q.add_argument("--host", default="127.0.0.1")
    args = p.parse_args()
    if args.cmd == "login":
        from dotenv import load_dotenv
        load_dotenv()
        from deltadesk.auth.upstox_login import login
        login(open_browser=not args.no_browser)
        return
    if args.cmd == "instruments":
        _instruments(args)
        return
    pipe = _build(args)
    if args.cmd == "run":
        asyncio.run(pipe.run(args.cycles))
        if pipe.orders:
            o = pipe.orders
            print(f"\nend of run · realised {o.realised:+,.0f} · unrealised {o.unrealised:+,.0f} · "
                  f"{len(o.positions)} open · {len(pipe.decisions)} decisions")
    else:
        import uvicorn

        from deltadesk.markets.ai_rank import AiRanker, SyntheticHistory, YahooHistory
        from deltadesk.markets.council import Council, SyntheticBars, YahooBars
        from deltadesk.markets.quotes import make_quotes
        from deltadesk.markets.service import MarketsService
        from deltadesk.server.app import create_app
        quotes = make_quotes(pipe.s.quotes or pipe.s.feed)
        history = YahooHistory() if quotes.name == "yahoo" else SyntheticHistory()
        history_long = YahooHistory(range_="2y", interval="1wk") if quotes.name == "yahoo" else SyntheticHistory(days=104, weekly=True)
        council = Council(YahooBars() if quotes.name == "yahoo" else SyntheticBars())
        print(f"desk feed: {pipe.feed.name} · markets quotes: {quotes.name} · history: {history.name} · http://{args.host}:{args.port}/")
        uvicorn.run(create_app(pipe, args.cycles, MarketsService(quotes=quotes, ai=AiRanker(history, history_long=history_long), council=council)), host=args.host,  # noqa: E501
                    port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
