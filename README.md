# Delta Desk

An agentic desk for Indian markets, built for retail: an AI radar and ranking over NSE indices, a
watchlist, a sector heatmap, a news wire with impact calls, IPO tracking with an IPO agent, a global
market map, a stock analysis page (fundamental and technical), an agent council, and a sniper-style
F&O desk that runs a typed, risk-checked pipeline in paper mode. Nothing here is investment advice.

Status: private beta, paper trading only. Source is published to read and follow, all rights reserved (see LICENSE).

`docs/STATUS.md` is the hand-off: what exists, what is real, what is next. Read it first.

## Layout

```
deltadesk/            Python package
  agents/             the sniper pipeline: feed → planner → regime → chain → sniper → strategy → risk → exec
  analytics/          options maths: Black-76 Greeks and implied vol, chain stats, indicators
  broker/             broker interface and the paper broker
  feeds/              synthetic market, Kite and Upstox adapters
  auth/               Upstox login and token cache
  markets/            read model behind the pages: universe, quotes and bars, AI ranking and radar, council,
                      news wire and desk assistant, IPO, fundamentals, technicals, investors, watchlist,
                      agent chat and language-model providers, logos
  server/             FastAPI app (page table, JSON API, WebSocket stream), traffic log (traffic.py)
  beta.py             waitlist, alert rules, WhatsApp / Telegram notifiers
  cli.py              `deltadesk run` (one synthetic day) and `deltadesk serve`
web/
  pages/              one self-contained HTML file per page
  static/css/         design.css (tokens, three themes, header, tables, cards), ai.css
  static/js/          common.js (shared helpers), nav.js (theme, beta pill, legal footer), ui.js (logos), ai.js (radar, ranking)
  static/vendor/      Lightweight Charts
data/                 runtime state, gitignored: watchlists, waitlist, alerts, caches, traffic log
docs/                 STATUS (hand-off), ROADMAP, PLAN
tests/                pytest suite, mirrors the package
tools/                page_harness.js: runtime smoke test for page scripts against a running server
.claude/skills/       the design system skill every page follows
```

Pages and routes: `/` home (radar + ranking), `/watchlist`, `/heatmap`, `/news`, `/ipo` and `/ipo/<slug>`,
`/forex`, `/global`, `/desk` (agent council), `/sniper`, `/analysis#SYMBOL/3m/<tab>`, `/beta`, `/legal`.
Every page shares the same header, nav, ticker, footer and design tokens; the page table lives in
`deltadesk/server/app.py` (`PAGE_ROUTES`).

## Run it

```
uv sync                                          # Python 3.12 and dependencies
cp .env.example .env                             # optional keys: Upstox, WhatsApp, Telegram, admin token
DD_QUOTES=yahoo uv run deltadesk serve --port 8000   # real delayed quotes, filings and news; http://127.0.0.1:8000
uv run deltadesk serve                           # fully synthetic market, works offline
uv run deltadesk run --fast --auto-approve       # one synthetic range day in the terminal
```

Checks: `uv run ruff check .` and `uv run pytest -q`; CI also parse-checks every page script with node.

## Data

* Quotes, bars, history: Yahoo Finance public endpoints (about 15 minutes delayed, no account). Upstox
  adapter is written for real-time once an app key exists (`uv run deltadesk login upstox`).
* Fundamentals: Yahoo fundamentals time series (annual and quarterly statements, trailing valuation),
  cached twelve hours under `data/fundamentals/cache`.
* News: public RSS feeds of Economic Times, Moneycontrol, Mint and Business Standard; impact calls are a
  lexicon rule (v0) with cues shown.
* IPOs: `data/ipo.json` in the schema documented in `deltadesk/markets/ipo.py`; fictional example issues
  until a feed is wired. Grey market premium is deliberately not modelled.
* Everything labelled "AI" is a transparent rules model (v0) until it is calibrated.

## Sniper (signal confluence)

Monitor agents each watch one thing on the 3-minute tape and vote long, short or neutral: relative volume,
EMA 9/21 with VWAP, RSI, the regime call, put-call ratio, yesterday's levels. Drag agents onto the desk on
`/sniper`; when every agent on the desk agrees (or `k` of `n`, with none against) inside the trading window the
gate fires one paper order with a stop (1.5 ATR) and a target (2x) on the index, drawn on the live candle chart.
Set the desk from the page or with `DD_SNIPER_MONITORS` / `DD_SNIPER_REQUIRED`. Paper only; not investment advice.

## Agent chat

The Watchlist page hosts a Fundamental agent and a Technical agent. Set one key in `.env` (free: `GROQ_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`; paid: `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`; or Ollama locally with `DD_LLM=ollama`) and answers come from that model, grounded in the desk's data for the stock and shaped as one summary line, a table of the numbers that matter and a few short bullets. With no key the agents compose the same shape by rules.

## Traffic

Page views are logged locally to `data/traffic.jsonl` (salted daily hash of IP and user agent, no
cookies). With `DD_ADMIN_TOKEN` set, `/admin/traffic?token=…&days=30` returns views and visitors per day,
top pages, referrers and device mix.

## Deploy

`Dockerfile` builds one container that runs the pipeline and the HTTP / WebSocket server; it listens on
`$PORT` when the host sets one, else 8000, so any container host works. GitHub Pages cannot host it (it is
a live server, not static files).

* **Oracle Cloud always-free VM (the launch target):** on a fresh Ubuntu ARM instance run
  `curl -fsSL https://raw.githubusercontent.com/Shiripatel/delta-desk/main/deploy/oracle/setup.sh | bash`.
  It installs Docker, opens ports 80 / 443, clones the repository to `/opt/delta-desk`, writes a starter `.env`,
  starts the app behind Caddy (automatic HTTPS once `SITE_ADDRESS` is a domain) and installs a five-minute
  pull-based auto-deploy. `data/` lives on the VM disk. See `deploy/oracle/`.
* **Any other host:** run the image with the `.env` values as environment variables. `/healthz` is the
  health check (it also reports the cache warmer's progress). Set `DATABASE_URL` to a Postgres (Neon,
  Supabase, or the host's own) and the waitlist is stored there instead of `data/`; every sign-up is also
  sent to the owner's Telegram (`DD_OWNER_CHAT`). The server warms its own caches at start and on a timer.

## Licence

Copyright (c) 2026 Shirish Patel. All rights reserved. The code is published for reading and personal,
non-commercial use; copying it into another product or service needs written permission. See `LICENSE`.
Lightweight Charts is Apache 2.0 (TradingView). Nothing here is investment advice.
