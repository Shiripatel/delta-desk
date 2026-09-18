# Delta Desk — daily roadmap

Working agreement: one focused deliverable per working day, merged to `main` behind green CI, demoable
on the synthetic market unless the day is explicitly about a live integration. Each day below is a GitHub
issue; close it with the PR that ships it. Days are numbered, not dated, so a missed day just shifts.

Definition of done for every day: tests added or updated, `uv run pytest` and `uv run ruff check .`
green, README or `docs/` touched if behaviour changed, no secrets in the diff.

## Sprint 1 · Days 1–5 · repo hygiene and the first real feed

| day | deliverable | done when |
|---|---|---|
| 1 ✅ | Repo on GitHub, CI (lint, tests, page scripts), Dockerfile, branch protection on `main` | first green run on GitHub Actions |
| 2 ✅ code | Upstox login job: OAuth code exchange, token cached under `data/`, `deltadesk login upstox` | token obtained on a real account, expiry handled |
| 3 ✅ | Upstox instrument master loader (`NSE.json.gz`, validated against the live file), chain, index and futures keys | `deltadesk instruments` prints today's chain tokens |
| 4 ✅ code | Upstox WebSocket V3 adapter via the SDK streamer: `Tick` mapping, auto-reconnect | ticks flow into `FeedAgent` during market hours; `/markets/options` shows the real chain (verify on a live session) |
| 5 ✅ code | Upstox REST quote provider for the markets page and watchlists (500 keys per call, 2 s cache); Kite-style watchlist pane on both pages | heat map and watchlist move with the real market (verify on a live session) |

## Sprint 2 · Days 6–10 · persistence and replay

| day | deliverable | done when |
|---|---|---|
| 6 | Tick and bar recorder to Parquet per day (`data/ticks/YYYY-MM-DD.parquet`), DuckDB query helper | a full session recorded without gaps |
| 7 | Replay feed: replays a recorded day into the pipeline at any speed | `deltadesk run --feed replay --day 2026-09-22` reproduces the same decisions |
| 8 | SQLite store for decisions, fills, cycle reports, agent errors; `/history` endpoint | restart keeps yesterday's journal |
| 9 | Feed health: heartbeat, latency, gap detection, stale-data guard that blocks the sniper | injected gap disarms all zones and logs an alarm |
| 10 | Daily jobs: pre-market instrument refresh, NSE constituent CSV refresh, post-market recorder flush | cron or Task Scheduler entries documented |

## Sprint 3 · Days 11–15 · planner, journal, calibration

| day | deliverable | done when |
|---|---|---|
| 11 | Planner v2: previous-day chain (walls, max pain), IV rank from recorded history, event calendar as an input | `DayPlan` shows why each zone exists |
| 12 | Journal agent: every decision joined to its outcome (P&L, MAE/MFE, time in trade) | `/journal` table on the desk page |
| 13 | Calibration report: confidence bucket versus hit rate over recorded days | report renders; threshold recommendation printed |
| 14 | Strategy library v2: iron condor, calendar spread guardrails, size by risk budget instead of fixed lots | each structure has a unit test on a fixed snapshot |
| 15 | Broker margin API in the risk agent (Upstox `/charges/margin`) with the local estimate as fallback | live margin shown in `RiskVerdict` |

## Sprint 4 · Days 16–20 · product surface

| day | deliverable | done when |
|---|---|---|
| 16 | Desk page charts on live bars: spot with levels and zones, OI by strike | charts follow `/stream` |
| 17 | DayPlan editor: adjust or disable zones from the page before the open | edits persist and reach the sniper |
| 18 | Markets page: index factsheet weights, 52-week data, sector indices | heat map tiles use published weights |
| 19 | Data jobs for IPO, earnings, FII/DII, holidays from official pages into `data/*.json` | tables show real rows, no "example data" tags |
| 20 | Auth: single-user login, session cookie, HTTPS behind Caddy on the VPS | desk reachable from phone with a password |

## Sprint 5 · Days 21–25 · hardening

| day | deliverable | done when |
|---|---|---|
| 21 | Second feed (Kite Connect or TrueData) and divergence alarm | mismatch above threshold pauses the sniper |
| 22 | Structured logging, Prometheus metrics, Grafana dashboard for cycle latency and agent errors | dashboard screenshot in docs |
| 23 | Alerting: Telegram or WhatsApp on decisions, vetoes, kill switch, feed loss; kill switch by reply | phone alert round-trip under 10 s |
| 24 | Backtest harness over all recorded days with the calibration report as output | one command, one report |
| 25 | Chaos day: kill the feed, corrupt a tick, restart mid-trade; fix what breaks | runbook in `docs/RUNBOOK.md` |

## Sprint 6 · Days 26–30 · towards live

| day | deliverable | done when |
|---|---|---|
| 26 | Broker order adapter (Upstox orders, modify, cancel, positions) behind the `Broker` interface, paper by default | round-trip on a 1-lot far OTM option after hours in sandbox |
| 27 | SEBI algo registration pack: strategy description, algo ID tagging in every order, static IP, order-rate guard | checklist signed off with the broker |
| 28 | Staged go-live limits: 1 lot, one structure, tight drawdown, auto-flatten at 15:15 | config reviewed and locked |
| 29 | Mumbai VPS deployment with Docker, systemd, static IP, backups of `data/` | desk survives a reboot |
| 30 | Review: paper versus expectations, calibration, decide on first live week | written decision in `docs/` |

## Standing backlog (pull in when a day frees up)

* Bank Nifty and Sensex chains alongside NIFTY (multi-underlying pipeline).
* Multi-user accounts and per-user watchlists, limits, journals.
* LLM-written `why` fields and post-market narrative, behind the schema.
* Mobile layout pass for both pages.
* GitHub Pages deployment of the desk page in demo mode.
