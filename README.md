# Delta Desk

An agentic desk for Indian markets, built for retail: an AI radar and ranking over NSE indices, a
watchlist, a sector heatmap, a news wire with impact calls, IPO tracking with an IPO agent, a global
market map, a stock analysis page (fundamental and technical), an agent council, and a sniper-style
F&O desk that runs a typed, risk-checked pipeline in paper mode. Nothing here is investment advice.

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

## Agent chat

The Watchlist page hosts a Fundamental agent and a Technical agent. Set one free key in `.env` (`GROQ_API_KEY`, `GEMINI_API_KEY` or `OPENROUTER_API_KEY`, or run Ollama locally with `DD_LLM=ollama`) and answers come from that model, grounded in the desk's data for the stock. With no key the agents answer by rules from the same data.

## Traffic

Page views are logged locally to `data/traffic.jsonl` (salted daily hash of IP and user agent, no
cookies). With `DD_ADMIN_TOKEN` set, `/admin/traffic?token=…&days=30` returns views and visitors per day,
top pages, referrers and device mix.

## Deploy

`Dockerfile` builds one container that runs the pipeline and the HTTP / WebSocket server on port 8000.
Set `DD_QUOTES=yahoo` and the secrets from `.env.example` in the host's environment; mount or persist
`data/` if you want watchlists, the waitlist and the traffic log to survive redeploys.
