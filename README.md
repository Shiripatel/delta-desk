# Delta Desk

Sniper-style F&O (futures and options) trading desk run by a pipeline of agents. Retail-first, NSE
index options, paper mode by default. The desk prepares a plan from the previous session, arms
opportunity zones, and fires one typed, risk-checked decision when the market reaches them.

* `docs/PLAN.md` — the build plan: principles, sniper workflow, agent topology, live-data API
  comparison, SEBI retail-algo constraints, enterprise checklist, phases.
* `index.html` — the desk page (single file, no build step). Opened as a file it shows demo data; served by
  `deltadesk serve` it streams live from the pipeline. Published copy: https://claude.ai/artifact/8oJdEdBTDVCvc5bzfKNSQj
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
uv run deltadesk serve --speed 120          # HTTP + WebSocket on :8000, index.html at /
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

## Feeds

Quotes on the markets page come from `deltadesk/markets/quotes.py`. Synthetic by default; the module
docstring lists the exact quote endpoints for Upstox, Kite, Dhan and Angel One. IPO data has no broker API;
maintain `data/ipo.json` (schema in `deltadesk/markets/ipo.py`).


`DD_FEED=synthetic` (default) needs no credentials. `kite` is wired to Kite Connect's ticker (paid
Connect plan for data). `upstox` and `dhan` are phase-1 adapters; see `docs/PLAN.md` section 5 for
limits and pricing of each provider.
