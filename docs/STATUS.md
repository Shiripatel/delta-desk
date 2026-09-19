# Delta Desk — where we are (start here tomorrow)

Updated: 2026-09-18 (end of day 1). Repo: https://github.com/Shiripatel/delta-desk · branch `main` · CI green.

## Resume in three commands

```
cd C:\Users\shiri\Downloads\delta-desk
uv run pytest -q                                   # 35 tests
set DD_QUOTES=yahoo && uv run deltadesk serve --speed 120     # then open http://127.0.0.1:8000/
```

Tell Claude: "read docs/STATUS.md and continue with the next item" — this file is the memory.

## What exists (all on the shared design system, five themes, Home · News · IPO · Agents · Sniper)

| page | route | what it does | data today |
|---|---|---|---|
| Home | `/` | AI radar (buy / hold-no-trade / sell bands, short-term vs long-term mode, replay 5 sessions, trails), top-10 ranking, NIFTY 50 / BANK NIFTY / SENSEX selector, zone counts, index ticker | Yahoo, 15 min delayed; rules model v0 |
| Watchlist | `/watchlist` | user lists (up to 12, 50 symbols each) with live quotes, change, day range, open, previous close, volume and AI score; presets NIFTY 50 / BANK NIFTY / FIN NIFTY / NEXT 50 / MIDCAP SELECT / SENSEX / Indian indices / commodities-FX-world; search to add, rename, delete, sortable columns, row → analysis | stored server-side in `data/watchlist.json` (single-user until accounts) |
| News | `/news` | Bloomberg-style wire from 6 RSS feeds: time, source, headline, stock tags, impact call (good / bad / no impact, lexicon v0, cues shown), filters (impact, watchlist, picked stocks), AI generated summary panel, desk assistant chat (`POST /chat`) | live RSS; assistant answers from quote + council + headlines |
| IPO | `/ipo`, `/ipo/<slug>` | list with summary chips (open, upcoming, closed, listed in gain / loss, avg listing gain), board filter, tabs Open / Upcoming / Closed / Listed / Performance / Tracked with Groww-style columns; performance tracker per year and board (issue price, listing day close, listing gain, current price, profit / loss, CSV export); detail page per issue: facts, six-step timeline, IPO agent (rules v0: demand, growth, valuation, issue structure, news), about, financials table + bars, strengths / risks, objectives, subscription by category, issue details, key ratios, people, wire mentions | fictional example issues flagged `example`; `data/ipo.json` in the documented schema replaces them; current price for real listings via quotes |
| Agents | `/desk` | agent council: 10 agents (6 technical, 4 fundamental) vote on one stock at one horizon (15m → 10y); weights shift with horizon; flow picture + every vote in a table | Yahoo bars per horizon; fundamentals only for 3 example files |
| Sniper | `/sniper` | five-step flow with a live stepper (Plan → Watch → Arm → Shoot → Manage): levels and zones, scope tiles, range chart with zones, chain around ATM, target board (pts and σ), the shot with approve / reject, risk meters, positions, agents, log | synthetic market (paper); Upstox adapter written, not yet run live |
| Global | `/global` | dotted world map with the key indices placed by city, region tabs (World, United States, Europe, China & Hong Kong, Japan & Asia, India), index cards for the region, then index futures, commodities, forex, bonds and crypto cards; every card opens the analysis page | Yahoo quotes for all world keys |
| Forex | `/forex` | INR crosses, world majors, a colour map of pairs, currency-strength meter, all pairs table; every pair links to its chart | Yahoo, delayed |
| Beta | `/beta` | waitlist sign-up (name, email, phone, interests, experience, WhatsApp consent) into `data/waitlist.jsonl`; free alerts: price move, price above/below, council verdict flip, bad news; WhatsApp Cloud API or Telegram when configured, dry-run log otherwise; evaluated every 60 s | files under `data/` |
| Legal | `/legal` | disclaimer, risk disclosure, terms, privacy, data sources, contact; the same footer is injected on every page | static |
| Analysis | `/analysis#SYMBOL/3m/overview` | every stock, index, FX or commodity click lands here: symbol head with day and 52-week range; tabs Overview (AI score, council stance, win rate, forecast, risk, returns, strongest agent readings, six-month line, latest news), Chart (one line of closes with range buttons; no TradingView), Agents (council per horizon), News (tagged headlines), Levels (pivots, 52w, SMAs, RSI, ATR). `/chart` redirects here. Was: TradingView widget by default (real-time NSE, all indicators, drawing tools); Desk chart fallback (our bars, EMA/RSI/volume) | TradingView / Yahoo |
| Markets | `/markets` | the full market-analysis surface (overview, stocks, options, futures, ETF, forex, screener, heat map, earnings, flows, calendar, trending, watchlist). Not in the nav for now | Yahoo / files |

Backend: FastAPI in `deltadesk/server/app.py`; markets read model in `deltadesk/markets/`; the F&O pipeline in `deltadesk/agents/` + `pipeline.py`; feeds in `deltadesk/feeds/` (synthetic, kite, upstox); tests in `tests/`.

## What is real and what is placeholder

* Real: Yahoo quotes and bars (delayed), RSS headlines, NSE constituent CSVs, Upstox instrument master, TradingView chart, all maths (Greeks, indicators, scoring rules).
* Placeholder, clearly tagged in the UI: IPO rows, earnings dates, FII/DII flows, holidays, fundamentals (3 example files). Each reads a `data/*.json` file the moment one exists; schemas are in the module docstrings.
* Rules v0 everywhere an "AI" label appears (radar score, council votes, news impact, assistant). Designed so a trained model or an LLM slots in behind the same endpoints.

## Decisions taken with the user

* Product focus: Home (radar + table), News, IPO, Agents, Sniper. Markets stays alive but unlinked.
* Free data first: Yahoo (no account) now; Upstox (free account) when the user creates the app; Kite Connect (₹500/month) or Angel One as alternatives. No nseindia.com scraping.
* Look: light grey Mist theme default, filled dark header band with "Join beta" as the only call to action (no beta strip on pages), compact hero written in LLM / AI-agent terms, text nav, no watchlist rail on pages, "Nothing here is investment advice" everywhere. Groww lessons adopted as principles (cards, pill tabs, calm tables, monograms, own icons); see the design skill.
* Sniper page is a five-step flow (Plan → Watch → Arm → Shoot → Manage) with a live stepper; keep any new agent output inside one of those steps.
* Radar: three bands; short term = daily momentum, long term = weekly momentum + fundamentals.
* Work rhythm: one deliverable per day, tests + ruff green, commit and push each day, update this file at the end of each session.

## Next up, in order (pick from the top)

1. **IPO data feed:** the tracker, detail page and IPO agent are built and run on fictional example issues. License a calendar (Trendlyne / Tickertape / TrueData) or write the SEBI + BSE fetcher that fills `data/ipo.json` in the schema in `deltadesk/markets/ipo.py`; subscription by category during bidding; listing prices on listing day. GMP is deliberately left out (no primary source; user decision).
2. **Fundamentals source** so the council's right half lights up for every stock (NSE annual results or a licensed API into `data/fundamentals/<SYMBOL>.json`).
3. **Options agents + per-agent accuracy badges** on the council (IV rank, OI walls, max pain, expected move; track each agent's past calls and let weights learn).
4. **LLM behind the same endpoints:** news impact analyser, "why" text, assistant. Needs an API key; interface already isolated (`Analyzer`, `DeskAssistant`).
5. **Alerts:** Telegram on verdict flips, new bad-impact story on a watchlist stock, sniper decisions, kill switch.
6. **Upstox live session:** create the Upstox app, `deltadesk login upstox`, run the sniper on the real chain during market hours; then the recorder and replay (roadmap days 6–7).
7. Radar trails toggle, compare two stocks on the council, mobile pass, GitHub Pages demo.

## Known rough edges

* NIFTY Midcap Select has no Yahoo symbol (no quote). India 10-year G-sec yield has no free source.
* News tagging is alias-based; obscure company names may go untagged. Impact lexicon is deliberately simple.
* TradingView widget needs internet; its NSE data is real-time but layouts are per TradingView login.
* Branch protection on `main` is unavailable on GitHub Free for private repos.
