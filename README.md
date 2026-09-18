# Delta Desk

Sniper-style F&O (futures and options) trading desk run by a pipeline of agents. Retail-first, NSE
index options, paper mode by default. The desk prepares a plan from the previous session, arms
opportunity zones, and fires one typed, risk-checked decision when the market reaches them.

* `docs/STATUS.md` — **start here**: where we are, what is real, what is next. Updated at the end of every session.
* `docs/PLAN.md` — the build plan: principles, sniper workflow, agent topology, live-data API
  comparison, SEBI retail-algo constraints, enterprise checklist, phases.
* `home.html` — the landing page at `/`: AI radar and the top-10 ranking (NIFTY 50, BANK NIFTY, SENSEX, all).
* `news.html` — the News page at `/news`: a continuously updating wire from public RSS feeds, each story tagged with the
  stocks it mentions and an impact call (good / bad / no impact, lexicon rule v0 with the cues shown), filters by impact,
  watchlist or picked stocks, a story panel, and a desk assistant that answers from the desk's own data.
* `analysis.html` — the analysis page (overview, chart, agents, news, levels) at `/analysis#SYMBOL/3m`. The chart is a single line of closes with range buttons (was: TradingView,
  all its indicators and drawing tools); the Desk chart (our bars on Lightweight Charts, EMA/RSI/volume) is the offline
  fallback. Every stock name across the app links here.
* `sniper.html` — the F&O sniper desk at `/sniper`: scope tiles, today's range with plan levels and zones, chain around
  ATM, target board, the latest typed decision with approve/reject, agents strip, risk meters, positions, signals, log.
* `ipo.html` — the IPO page at `/ipo`: open, upcoming, closed and listed issues with dates, band, lot, minimum bid, size.
* `agents.html` — the agents page at `/desk`: the agent council. Ten narrow agents (trend, momentum, MACD, volume,
  volatility, levels, valuation, growth, quality, ownership) read one stock at one horizon (15 min to 10 years) and
  feed a verdict; short horizons weight the technical agents, long horizons the fundamentals.
* `sniper.html` — the F&O sniper desk at `/sniper`: pipeline strip, plan and chart, typed decisions, positions, log.
* `prototype/index.html` — the original single-file design prototype (demo data), served at `/prototype`.
  Published copy: https://claude.ai/artifact/8oJdEdBTDVCvc5bzfKNSQj
* `markets.html` — the markets page at `/markets`, laid out like a broker's market-analysis menu:
  real-time quotes (stocks with index tabs, options chain, index futures, ETFs, forex), technical tools
  (screener, heat map, earnings calendar, FII/DII institutional tracker, IPO tracker) and trading news
  (headlines from public RSS, financial calendar with computed expiries, trending topics), plus watchlists.
* `deltadesk/` — the Python package (phase 0 skeleton, runnable end to end on a synthetic market).
* Visual style follows typesafe.ai: ground `#FEFEFE`, ink `#1E1E1E`, hairlines `#DEDEDE` / `#C4C4C4`,
  accent `#F386A1` / `#D45BB6`, JetBrains Mono 300 for data, Host Grotesk for headlines.
* All figures in the prototype are illustrative examples, not advice.

## Run it

```
uv sync                                     # installs Python 3.12 and dependencies
uv run deltadesk run --fast --auto-approve  # one synthetic range day, paper fills, typed decisions
uv run deltadesk run --scenario trend_up --fast --auto-approve -v
uv run deltadesk serve --speed 120          # :8000 → / AI radar + ranking, /markets, /desk (agents), WS /stream
uv run pytest
```

Endpoints: `GET /state`, `GET /decisions`, `POST /decisions/{id}/approve|reject`, `POST /kill`,
`WS /stream` (every bus message as `{topic, data}`). Markets: `GET /markets/indices`, `GET /markets/index/{code}`,
`GET /markets/options|futures|etf|forex|screener|earnings|flows|ipo|calendar|news|trending`, `GET /markets/search?q=`,
`GET|POST|DELETE /markets/watchlist/{name}[/{symbol}]`, `POST /markets/refresh-constituents` (downloads NSE's
official constituent CSVs into `data/constituents/`). Hand-maintained inputs live in `data/*.json`
(`ipo`, `earnings`, `flows`, `calendar`); schemas are in the matching `deltadesk/markets/*.py` docstrings.

## Agents (matches the pipeline nodes on the page, plus planner and sniper)

| agent | job | typed output |
|---|---|---|
| feed | ticks, 1-min bars, option chain, OI, VIX; local IV and Greeks | `Snapshot` |
| planner | previous-session levels, CPR, bias, opportunity zones | `DayPlan` |
| regime | trend / range / event classification | `RegimeCall` |
| chain | ATM IV, IV rank, skew, PCR, max pain, walls, expected move | `ChainStats` |
| sniper | arms zones as price approaches, fires on confirmation | `Trigger` |
| strategy | structure, strikes, size, stop, target, confidence | `CandidateTrade` |
| risk | margin, max loss, Greek limits, drawdown, window; can veto | `RiskVerdict` |
| exec | paper or broker orders, exits, book | `OrderState` |

Execution stays in paper mode until backtest and calibration numbers justify live routing.

## Real prices without an account: Yahoo Finance (15 min delayed)

Set `DD_QUOTES=yahoo` in `.env` (or run `DD_QUOTES=yahoo uv run deltadesk serve`). The markets page,
heat map, screener and watchlists then show real NSE prices for stocks, ETFs, the main indices and
currency pairs, about 15 minutes late, with a "delayed" label in the header. Index futures and the
option chain are not on Yahoo, so the desk itself stays on the synthetic market until a broker feed is
configured. NIFTY Midcap Select has no Yahoo symbol and shows no quote.

## AI ranking and radar

Two views on the markets page rank the universe with a transparent rules model (v0) over three months
of daily closes: **AI picks** (rank, past win rate of the score over 10-day windows, score ring 1 to 10,
3-month forecast, 3-month sparkline, low-risk ring, add to watchlist) and **radar** (a bullseye with score
10 at the centre and 1 at the rim, sectors as spokes, dot size by index weight, and a play button that
replays the last five sessions). With `DD_QUOTES=yahoo` the history is real; otherwise synthetic. The
rules are in `deltadesk/markets/ai_rank.py` and are the placeholder that Sprint 3's calibration replaces.

## Live data with Upstox (free)

1. Open an Upstox account (free) and create an API app at https://account.upstox.com/developer/apps
   with redirect URL `http://127.0.0.1:8765/upstox/callback`. Put the key and secret in `.env`
   (see `.env.example`) and set `DD_FEED=upstox`.
2. `uv sync --extra upstox`, then every trading day: `uv run deltadesk login upstox` (browser login,
   token cached under `data/` until 03:30 IST next day).
3. `uv run deltadesk instruments` shows what the desk will subscribe to (index, VIX, near future,
   weekly chain around ATM: about 90 keys, inside the free limit). `uv run deltadesk serve` then runs
   the desk on the live chain and the markets page on live quotes.

The watchlist pane on the left of both pages (search with Ctrl+K, multiple named lists, live quotes)
is served from `static/` and stored in `data/watchlist.json`.

## Feeds

Quotes on the markets page come from `deltadesk/markets/quotes.py`. Synthetic by default; the module
docstring lists the exact quote endpoints for Upstox, Kite, Dhan and Angel One. IPO data has no broker API;
maintain `data/ipo.json` (schema in `deltadesk/markets/ipo.py`).


`DD_FEED=synthetic` (default) needs no credentials. `kite` is wired to Kite Connect's ticker (paid
Connect plan for data). `upstox` and `dhan` are phase-1 adapters; see `docs/PLAN.md` section 5 for
limits and pricing of each provider.
