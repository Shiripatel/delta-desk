# Delta Desk — build plan

Sniper-style, agent-run F&O desk for Indian retail traders. Inspired by the polish of moomoo and
Robinhood, but the product is different: the user does not scroll charts and tap buy. A team of narrow
agents prepares a plan from previous sessions, sits on armed levels during the day, and fires one typed,
risk-checked order when the market hands over the opportunity. The human sets limits and approves.

This document is the working plan. `README.md` stays the short overview.

## 1. Product principles

1. **Decisions, not chatter.** Every agent output is a typed schema (pydantic model). The UI renders
   schemas; nothing is free text except the `why` field.
2. **Sniper, not machine gun.** The desk is idle by default. It only acts when an armed opportunity zone
   is hit and the regime, chain and risk agents agree. Target: a handful of trades a week, not a day.
3. **Previous session feeds today.** Pre-market, a planner agent reads yesterday's bars, option chain,
   OI build-up and IV to produce a `DayPlan`: levels, expected move, bias, and the structures that are
   allowed today. Intraday agents cannot invent a setup that is not in the plan.
4. **Risk can veto, always.** Margin, max loss, Greek limits and daily drawdown are enforced by a
   separate agent and by a kill switch that flattens everything.
5. **Paper first, live later.** Live routing turns on only when paper results and calibration numbers
   justify it, and only through a SEBI-compliant broker API path (section 6).
6. **Broker-agnostic.** A `Feed` and a `Broker` interface sit between the agents and any vendor SDK.
   Swapping Zerodha for Upstox or Dhan is a config change.

## 2. The sniper workflow (one trading day)

| phase | when (IST) | agent(s) | output |
|---|---|---|---|
| Post-market review | 15:45 to 18:00 previous day | journal, planner | trade journal entries, calibration stats |
| Pre-market plan | 08:00 to 09:10 | planner | `DayPlan`: PDH/PDL/PDC, CPR, yesterday's call/put walls, max pain, IV rank, expected move, event calendar, allowed structures, bias |
| Open | 09:15 to 09:30 | feed, regime | opening range, gap classification, no trades |
| Hunt | 09:30 to 14:45 | feed, regime, chain, sniper, strategy, risk | zones arm as price approaches; a `Trigger` fires on touch and rejection or on a confirmed break; strategy converts a trigger to a `CandidateTrade`; risk returns a verdict; the desk emits one `Decision` |
| Manage | after fill | exec, risk | stop, target, time stop, Greek drift, re-hedge suggestion |
| Wind down | 14:45 to 15:20 | exec | no new entries, close or roll per plan |
| Kill switch | any time | risk, exec | flatten all, disarm all zones |

The "wait like a sniper" behaviour lives in the sniper agent: it holds the `DayPlan`'s opportunity zones,
tracks distance to each in sigma units, arms a zone when price is within reach, and fires only when the
zone's condition is met and the regime agent's current call is compatible with that zone.

## 3. Agent topology

The six nodes in the prototype stay. Three are added for the sniper model.

| agent | input | job | typed output |
|---|---|---|---|
| feed | broker WebSocket | ticks, 1-min bars, option chain, OI, VIX; local IV and Greeks | `Snapshot` |
| planner (new) | previous-day bars, chain, journal | levels, zones, allowed structures, bias | `DayPlan` |
| regime | `Snapshot` | trend, range, event classification with probability | `RegimeCall` |
| chain | `Snapshot` | IV rank, skew, PCR, max pain, walls, expected move | `ChainStats` |
| sniper (new) | `Snapshot`, `DayPlan`, `RegimeCall` | arm and fire opportunity zones | `Trigger` |
| strategy | `Trigger`, `RegimeCall`, `ChainStats`, `DayPlan` | pick structure, strikes, size, thesis, confidence | `CandidateTrade` |
| risk | `CandidateTrade`, positions, limits | margin, max loss, Greek limits, drawdown; can veto | `RiskVerdict` |
| exec | approved `Decision` | paper or broker orders, fills, monitoring, exits | `OrderState` |
| journal (new) | fills, decisions | post-trade record, calibration of confidence vs outcome | journal rows |

Most agents are deterministic quant code. An LLM is used only where language is the input or the
output: classifying scheduled events and news for the regime agent, writing the `why` field, and drafting
the post-market journal. LLM output never bypasses the schemas or the risk agent.

## 4. Architecture

```
broker WS ──► Feed adapter ──► feed agent ──► Snapshot ─┬─► regime ─┐
                                                        ├─► chain  ─┼─► strategy ─► risk ─► Decision ─► exec ─► Broker adapter
DayPlan (planner, pre-market) ──► sniper ─► Trigger ────┘           │
                                                    event bus (asyncio topics, later Redis Streams)
                                                    ▼
                                    FastAPI: /state, /stream (WS), approve, reject, kill
                                                    ▼
                                    index.html desk (existing prototype, wired to /stream)
```

* **Runtime:** Python 3.12, asyncio. Chosen because every Indian broker ships a Python SDK first
  (kiteconnect, upstox-python-sdk, dhanhq, smartapi-python, fyers-apiv3).
* **Schemas:** pydantic v2. One module, `deltadesk/schemas.py`, is the contract for every agent.
* **Event bus:** in-process asyncio topics now. Redis Streams when the desk runs as more than one process
  or needs replay across restarts.
* **Storage:** Parquet files per day for ticks and bars (DuckDB for queries), SQLite for decisions,
  orders and journal. Postgres when multi-user.
* **Pipeline cycle:** the feed agent publishes a `Snapshot` every N seconds (2 s default). Regime and
  chain run in parallel on it, sniper checks zones, strategy runs only when a trigger exists, risk runs
  only on a candidate. Every cycle logs duration and per-agent status, which is what the prototype's
  "last full cycle 1.84 s · 6/6 agents ok" line shows.
* **UI:** the existing `index.html` becomes a thin client on `/stream`. Later a React or Svelte app if
  the surface grows; the current single file is fine for one desk.
* **Auth and multi-tenant:** out of scope until paper trading works for one account.

## 5. Live data: which APIs

The desk needs four streams for NIFTY and BANKNIFTY: index spot, near futures, the option chain for the
current and next weekly expiry (LTP, bid/ask, OI, volume), and India VIX. Nobody sells "an option chain
feed": you download the broker's daily instrument master, pick the strikes around ATM, and subscribe to
each token. Greeks and IV are computed locally with Black-76 on the futures price, unless the broker
pushes them (Upstox does).

| provider | cost | WebSocket limits | depth | historical | notes |
|---|---|---|---|---|---|
| Zerodha Kite Connect | Personal plan free, but **no market data**. Connect plan ₹500/month per API key includes live and historical | 3,000 instruments per connection | 5 levels in full mode | included in paid plan | Most mature SDK and docs. Login needs a daily request-token exchange (TOTP automatable). |
| Upstox | free | 2 connections per user; per connection ltpc 5,000, option_greeks 3,000, full 2,000 keys; combined caps lower (full 1,500). Plus plan: 5 connections, D30 depth for 50 keys | 5 levels; 30 on Plus | free | Protobuf feed. Pushes option Greeks, which saves local computation for the chain. Best free choice for the chain. |
| Dhan | Data APIs ₹499 + GST per month (waiver tied to monthly trade count, verify) | 5 connections × 5,000 instruments | 20-depth available | included | Binary feed, second-by-second snapshots rather than tick-by-tick. |
| Angel One SmartAPI | free | 3 connections, 1,000 tokens each | 20-depth on WS 2.0 | free | Adequate for one underlying's chain. |
| Fyers API v3 | free | small per-connection symbol cap in older docs (50); verify current | yes | free; partners with TrueData | |
| TrueData, Global Datafeeds | paid vendor, roughly ₹1.5k to 2.5k per month retail (verify) | full-market, tick-by-tick | yes | yes, deep history | Exchange-authorised vendors, independent of your broker. Use for research history and as a second feed for redundancy. |
| nseindia.com scraping | free | none | none | none | Against NSE terms, rate-limited, breaks often. Not for production. |

Recommendation:

1. **Now (paper):** synthetic and replay feeds in the repo, so the pipeline runs with no credentials.
2. **First live feed:** Upstox (free, Greeks pushed, enough keys for two underlyings' chains).
   Execution on the Zerodha Personal plan (free) or Upstox itself.
3. **Redundancy:** add Kite Connect paid (₹500) or TrueData as a second feed. The feed agent compares
   both and flags divergence, which is what an enterprise desk needs before live routing.
4. **Historical:** TrueData or Kite Connect historical for backtests and IV-rank history. Store locally
   as Parquet the first time; never re-download.

Sizing check: one underlying, two expiries, 25 strikes each side, CE and PE = about 200 tokens, plus
spot, futures and VIX. Two underlyings fit comfortably inside every provider's free limit above.

### 5a. Data for the markets page (indices, constituents, watchlist, IPO)

The desk page needs the F&O chain. The markets page needs plain equity and index quotes, which every
broker data API also provides over the same connection:

| need | source | notes |
|---|---|---|
| Index levels (NIFTY 50, Bank, Fin, Midcap Select, Next 50, Sensex, VIX) | broker WebSocket, index keys (`NSE_INDEX|Nifty 50`, `BSE_INDEX|SENSEX` on Upstox; `NSE:NIFTY 50` on Kite) | free on Upstox and Angel; ₹500/month on Kite; Dhan Data API plan |
| Constituent lists | niftyindices.com constituent CSVs (official, free, daily) | `POST /markets/refresh-constituents` fetches them; weights need the monthly factsheet |
| Constituent quotes for heat map, movers, watchlist | REST quote endpoint (500 keys per call on Upstox and Kite; 1,000 on Dhan) polled every few seconds, or WebSocket in `ltpc` mode (5,000 keys free on Upstox) | one Upstox connection covers all indices' members |
| End-of-day fallback | NSE bhavcopy (free daily CSV) | enough for after-hours heat maps and screens |
| IPO calendar | `data/ipo.json` maintained by hand or a job; NSE's public IPO pages are unofficial and change; no retail broker API exposes IPOs | bidding stays in the broker app (UPI) |

So: yes, live quotes need a broker data API, and the recommendation is unchanged: Upstox first (free,
index keys and equity quotes on one token), Kite Connect or TrueData as a second source. Everything on
the markets page runs on synthetic quotes until `DD_FEED` points at a real adapter.

## 6. Regulation (SEBI retail algo framework)

SEBI's framework for retail participation in algo trading applies to all brokers from 1 April 2026. It
shapes the execution path, not the analysis path:

* Every automated order carries an exchange-issued **Algo ID / strategy ID**; strategies must be
  registered through the broker, who is the principal. Open, unregistered APIs are not allowed.
* Orders must originate from a **static IP** whitelisted with the broker, and a **kill switch** must
  exist. Exchanges monitor order-to-trade ratios and a per-second order threshold above which the
  activity is treated as algo.
* Practical consequence for Delta Desk: paper mode needs nothing. Live mode requires registering the
  strategy with the broker, tagging orders with the ID, running from a fixed IP (a small VPS in Mumbai
  is the usual answer), and keeping order rates far below thresholds, which a sniper desk does by design.

## 7. Enterprise-readiness checklist

* Typed contracts and versioned agents (`name`, `version` on every output).
* Every cycle, decision, veto, order and fill persisted with timestamps and inputs, so any trade can be
  replayed from stored snapshots.
* Feed health: heartbeat, latency, gap detection, dual-feed divergence alarm, automatic reconnect with
  resubscription.
* Hard limits in config, not code: margin cap, max loss per trade, daily drawdown, net vega and delta,
  max lots, allowed underlyings and structures, trading window.
* Kill switch reachable from the UI, the CLI and a phone.
* Secrets in environment variables or a vault, never in the repo. Daily broker tokens refreshed by a job.
* Backtest harness that runs the same agent code over replayed snapshots, plus calibration report:
  confidence bucket versus hit rate, which is what "0.81 means 81 of 100 such calls worked" requires.
* Tests: Greeks against known values, agent unit tests on fixed snapshots, end-to-end paper run in CI.
* Observability: structured logs, per-agent latency, Prometheus metrics later.
* Deployment: Docker, one process now; Mumbai VPS with static IP for live.

## 8. Phases

| phase | goal | deliverable |
|---|---|---|
| 0 (done) | runnable skeleton | schemas, bus, Black-76 Greeks, synthetic feed, all agents wired, paper broker, CLI, FastAPI + WebSocket, `index.html` on `/stream` (signals, decision, book, log), markets page (index tabs, heat map, breadth, movers, watchlists, IPO calendar) on synthetic quotes, tests |
| 1 | real data, still paper | Upstox feed adapter (chain + equity quotes), instrument master, Parquet recording, replay feed, live charts (spot, OI) on the desk page, index factsheet weights |
| 2 | planner and journal | previous-day analysis, DayPlan editor in UI, journal and calibration report |
| 3 | backtest and calibration | replay harness over recorded days, confidence calibration, strategy library (strangle, iron condor, debit spreads, directional) |
| 4 | second feed and hardening | Kite or TrueData redundancy, gap and divergence alarms, SQLite persistence, Docker |
| 5 | live routing | broker order adapter, SEBI registration, static IP deployment, staged size limits |

## 9. Decisions taken and open questions

Taken: Python and asyncio; pydantic schemas; NIFTY and BANKNIFTY weekly options first; paper mode
default; Upstox as first live feed; in-process bus until a second process is needed.

Open: whether the planner's levels are rule-based only or also learned from the journal; whether to
support equity F&O beyond the two indices; whether the UI stays a single HTML file past phase 2.
