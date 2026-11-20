# Delta Desk — where we are (start here tomorrow)

Updated: 2026-11-19 (Sniper rebuilt with one line per agent after a check of every page found no runtime breakage; agentic-repo review in docs/UX_REVIEW.md; favicon). 18 Nov: local launch with a six-page nav, IPO / Forex / Global / Investors parked, Home trimmed, phone layout fixed, one-click `tools/serve.cmd`. Earlier the same day: reevaluation, owner lock, calendar samples relative to today, the AI score's measured track record (which says the rule has no edge). Repo: https://github.com/Shiripatel/delta-desk · branch `main` · CI green.

## Resume in three commands

```
cd C:\Users\shiri\Downloads\delta-desk
uv run pytest -q                                   # 63 tests
tools\serve.cmd                                    # or: set DD_QUOTES=yahoo && uv run deltadesk serve --speed 120 ; then http://127.0.0.1:8000/
```

Local hosting (18 Nov 2026): the site runs on this machine at http://127.0.0.1:8000/ from `tools/serve.cmd` (double-click; it writes a
`.env` with `DD_QUOTES=yahoo` if none exists). The user's plan: check it locally first, then launch the integrated site; the Oracle kit
is ready for that step.

Tell Claude: "read docs/STATUS.md and continue with the next item" — this file is the memory.

## Reevaluation, 18 Nov 2026

The verdict after six weeks away: the code still runs (lint clean, Yahoo quotes, RSS and fundamentals all answering), but the
project is wide and shallow. Thirteen pages and about sixty endpoints sit on Sprint 1 of the roadmap; Sprints 2 to 6 (recorder,
replay, journal, calibration, auth, broker adapter) are untouched. The sniper has never seen a real tick (no Upstox app yet). Every
"AI" label is rules v0 with no record of past calls, so nothing can be called calibrated. There is no verifiable live URL (the Render
beta was taken down on 27 Sep, the Oracle kit was never recorded as deployed), no waitlist file and no stars.

Decisions taken from it:

* **Freeze on new pages and endpoints** until the measurement chain exists. The product surface is enough to launch with.
* **Depth before breadth:** the next sessions go to the chain that gives the desk a track record (recorder → replay → journal →
  calibration), because that is the only thing no competitor offers and the only thing that makes "AI" honest.
* **Owner lock before any public URL** (shipped today, see below). Accounts remain the real fix for the shared watchlist.
* Data purchases (shareholding, IPO calendar) move down the list: they are licensing decisions, not code, and they blocked the top of
  the list for six weeks.
* Open question for the user, not yet answered: information site (compete with Groww / Screener on licensed data) or decision engine
  with a track record (needs the Upstox app and the journal). The recommendation is the decision engine; the free pages stay as the
  landing surface either way.

Two things only the user can do, both unblockers:

1. Create the Upstox developer app (free, 15 minutes: https://account.upstox.com/developer/apps, redirect
   `http://127.0.0.1:8765/upstox/callback`), put the key and secret in `.env`, run `uv run deltadesk login upstox`. Every
   "verify on a live session" item since September waits on this.
2. Provision the Oracle VM and run `deploy/oracle/setup.sh` (it now generates `DD_OWNER_TOKEN` and prints the unlock link).

## Layout

`deltadesk/` is the Python package (agents, feeds, markets read model, server, beta, cli). `web/pages/` holds one HTML file per page, `web/static/css|js|vendor` the shared design system and scripts. `data/` is runtime state (gitignored). `tests/` mirrors the package. `docs/` is this file, the roadmap, the plan and the UX review.

## Less content, clean design (18 Nov 2026)

The user asked for less content and a very clean design before launch. Decisions:

* **Nav is six links:** Home · Watchlist · Heatmap · News · Agents · Sniper. The same on every page and in the phone More sheet.
* **Parked, not deleted:** IPO (fictional issues), Forex, Global and Investors (seed stakes). Their routes and APIs still work and carry
  the six-link nav, but nothing links to them. Each comes back with one nav line the day a real feed fills its data file.
* **Home is five things:** one hero line with the three sentiment boxes, the radar with its picks and breadth, the top 10, the track
  record, and one explanatory note. Gone: the eyebrow and paragraph, "biggest moves over the replay", the four-cell explainer.
* **Phone layout fixed on every kept page** (checked with Chrome device emulation at 400 px, not plain headless screenshots, which
  Chrome crops at its minimum window width): the ticker sticks under the header's real height (`--sticky-top` set by `nav.js`, with
  `--header-h` left constant so the measurement cannot feed back), the tablet header keeps brand and status on row one and the nav on
  row two, the theme select hides on phones, News items go to two rows (time · source · impact, then the headline), Home's sentiment
  boxes and radar controls wrap. The design skill records the "less is the rule" principle.

## Sniper rebuilt on the shape of the top agentic repos (19 Nov 2026)

The user reported pages "broken" and the Sniper "too much text, complex". A render of every page through Chrome's DevTools
protocol (console errors, uncaught exceptions, failed requests, sideways overflow, light and dark themes) found nothing broken at
runtime except a missing favicon, now served as `/static/favicon.svg` and at `/favicon.ico`. The complaint was the prose. The
`docs/UX_REVIEW.md` section "Agentic trading repos" compares TradingAgents, ai-hedge-fund, Vibe-Trading and the rest; the Sniper page
now follows their screen shape: one line per agent (name · vote · reading, the sentence in a tooltip), a gate that shows `agree / n`
and one word of status, an order card with numbers and two buttons, the chart, risk and positions, and a one-line log that opens on
click. The status bar lost its slogan, the title bars their explanations, the shelf its paragraph, the theme select is hidden on the
always-dark terminal. Mechanics unchanged: drag or + to add agents, the `needs k of n` rule, approvals, kill switch, stream. The
harness replays a recorded stream (`WS_REPLAY`) through every handler with zero errors.

## What exists (all on the shared design system, three themes, Home · Watchlist · Heatmap · News · Agents · Sniper; four pages parked)

| page | route | what it does | data today |
|---|---|---|---|
| Home | `/` | AI radar (buy / hold-no-trade / sell bands, short-term vs long-term mode, replay 5 sessions, trails), top-10 ranking, NIFTY 50 / BANK NIFTY / SENSEX selector, zone counts, index ticker | Yahoo, 15 min delayed; rules model v0 |
| Watchlist | `/watchlist` | Kite-style: narrow list on the left (symbol, LTP, day / week / month change, 52-week range bar, numbered list pager, search-to-add, presets, rename, delete) and the agent chat in the centre: pick a stock, choose Fundamental agent or Technical agent, ask; answers are grounded in the desk's own data for that stock, generated by a free language model when a key is set (Groq, Gemini, OpenRouter, Ollama) or composed by rules otherwise | stored server-side in `data/watchlist.json` (one list set for the whole site; edits are owner-only when `DD_OWNER_TOKEN` is set, until accounts) |
| Heatmap | `/heatmap` | Finviz-style treemap: tiles sized by index weight, grouped by sector, coloured by day %, 1 month, 3 months or AI score; NIFTY 50 / 100 / NEXT 50 / BANK / FIN / MIDCAP SELECT / SENSEX; hover card, click → analysis; refreshes every 10 s | live quotes + ranking |
| News | `/news` | Bloomberg-style wire from 6 RSS feeds: time, source, headline, stock tags, impact call (good / bad / no impact, lexicon v0, cues shown), filters (impact, watchlist, picked stocks), AI generated summary panel, desk assistant chat (`POST /chat`) | live RSS; assistant answers from quote + council + headlines |
| IPO | `/ipo`, `/ipo/<slug>` | list with summary chips (open, upcoming, closed, listed in gain / loss, avg listing gain), board filter, tabs Open / Upcoming / Closed / Listed / Performance / Tracked with Groww-style columns; performance tracker per year and board (issue price, listing day close, listing gain, current price, profit / loss, CSV export); detail page per issue: facts, six-step timeline, IPO agent (rules v0: demand, growth, valuation, issue structure, news), about, financials table + bars, strengths / risks, objectives, subscription by category, issue details, key ratios, people, wire mentions | fictional example issues flagged `example`; `data/ipo.json` in the documented schema replaces them; current price for real listings via quotes |
| Agents | `/desk` | agent council: 10 agents (6 technical, 4 fundamental) vote on one stock at one horizon (15m → 10y); weights shift with horizon; flow picture + every vote in a table | Yahoo bars per horizon; fundamentals via Yahoo when `DD_QUOTES=yahoo` |
| Sniper | `/sniper` | dark trading terminal built as a **pipeline canvas** (left to right): a shelf of monitor agents (Volume RVOL, MA/VWAP, RSI, Trend, Options PCR, Levels) the user drags onto the desk or adds with +; each node is one line (name · ▲ long / ▼ short / · neutral · reading; the reason is the tooltip); curved edges coloured by vote flow into the **confluence gate** (`agree / n`, direction, vote bar, `needs k of n`, one word of status) and on to the **order card** (direction, structure, confidence, entry / stop / target on the index, legs, max loss, margin, Approve / Reject). Below: a lightweight-charts candle chart (1/3/5-min, VWAP, EMA 9/21, volume, PDH/PDL, the live order's lines and fill arrows), risk, positions, orders today, and a one-line log that opens on click. Config is `GET/POST /sniper/config` (persisted to `data/sniper.json`). `tools/page_harness.js` replays a recorded stream (`WS_REPLAY`). | synthetic feed only so far; the Upstox feed is written but has never run on a real session |
| Global | `/global` | dotted world map with the key indices placed by city, region tabs (World, United States, Europe, China & Hong Kong, Japan & Asia, India), index cards for the region, then index futures, commodities, forex, bonds and crypto cards; every card opens the analysis page | Yahoo quotes for all world keys |
| Investors | `/investors` | cards for well-known investors (style, vehicle, since, holdings count, valued total, today's average move, top holdings with logos); open a card for the full holdings table (stake, market cap, value, LTP, today), row → analysis; sort by value, move or count | seed list with approximate stakes until a shareholding feed fills `data/investors.json` |
| Forex | `/forex` | INR crosses, world majors, a colour map of pairs, currency-strength meter, all pairs table; every pair links to its chart | Yahoo, delayed |
| Beta | `/beta` | one centred card: name, email, phone (optional, for WhatsApp); position on the list; live count; the alert-rules UI is off the page (API stays for the premium tier) | waitlist in Postgres when `DATABASE_URL` is set (Neon / Supabase free), else `data/waitlist.jsonl`; every sign-up also pinged to the owner's Telegram |
| Legal | `/legal` | disclaimer, risk disclosure, terms, privacy, data sources, contact; the same footer is injected on every page | static |
| Analysis | `/analysis#SYMBOL/3m/fundamental` | every stock, index, FX or commodity click lands here. Two tabs. **Fundamental**, laid out like a stock-analysis site: Overview (key stats, financial performance with chart, about, Delta Desk read, peers), Financials (income statement, balance sheet, cash flow, ratios; Annual / Quarterly / TTM; growth rows; per-row chart; CSV download), Statistics (18 groups incl. Altman Z and Piotroski F), Dividends (per FY, history, splits), History (price table), Profile. **Technical**, investing-style: chart, summary per timeframe, indicators, moving averages, pivots, AI score and council, headlines. Real filings via Yahoo fundamentals plus its dividend / split / monthly price events; cached 12 h. | four fiscal years and ~8 quarters from Yahoo; quarterly cash flows not published for India; no analyst estimates or business description (licensed data) |

Backend: FastAPI in `deltadesk/server/app.py`; markets read model in `deltadesk/markets/`; the F&O pipeline in `deltadesk/agents/` + `pipeline.py`; feeds in `deltadesk/feeds/` (synthetic, kite, upstox, dhan); tests in `tests/`.

## Owner lock (18 Nov 2026)

`DD_OWNER_TOKEN` empty (laptop): every route open, as before. Set (any public host): the fifteen routes that change desk state
answer 401 unless the request carries the token: kill switch, approve / reject, `POST /sniper/config`, every watchlist write (create,
delete, rename, preset, add, remove), `POST /markets/refresh-constituents`, and the alert rules (`POST/DELETE /alerts`, `/alerts/test`,
`/alerts/run`). The token travels as the `X-Owner-Token` header, `?token=`, or the `dd_owner` cookie that `GET /owner?token=…` sets
for 30 days (HttpOnly, SameSite Lax, Secure behind HTTPS); `GET /owner` reports `{locked, owner}`, `GET /owner/logout` clears it,
`/healthz` reports `locked`. Reads, the stream, the waitlist and both chats stay public. Pages already show a failed write as a toast
with the server's reason, so no page changed. `deploy/oracle/setup.sh` generates the token with the other secrets and prints the
unlock link. Test: `tests/test_server.py::test_owner_lock`.

## Track record of the AI score (18 Nov 2026)

`deltadesk/markets/track.py`: every past bar of every stock in the universe is scored exactly as the live ranking scores it (`features`
and `score` on the last 63 daily closes, or 104 weekly closes in long-term mode, price only), the zone is noted (buy 7–10, hold 4–6,
sell 1–3) and the forward return over 5 and 20 sessions (4 and 13 weeks) is recorded. Per zone: windows, share that closed higher,
mean and median move, against the base rate of every window. Walk-forward, no look-ahead, overlapping windows, no costs. `GET
/markets/track?index=&mode=`; cached six hours; warmed for NIFTY 50 with the rankings and for BANK NIFTY and SENSEX in the slow pass.
On Yahoo the serve command feeds it a year of daily closes and five years of weekly closes. Home shows it as the "track record" section
under the top-10 table (`DDAI.track` in `ai.js`, zone dot, delta to the base rate, base-rate row, one-line headline), following the
index tabs and the short / long switch. Tests: `tests/test_track.py`, `test_server.py::test_track_record_endpoint_and_home_section`.

**First real numbers, NIFTY 50, scored windows 16 Feb to 16 Oct 2026 (8,085 windows, 49 stocks):** the buy zone was higher 20
sessions later 38 % of the time against a base rate of 46 %; the sell zone 58 %; the hold zone 41 %. Directional hit rate 41 % at 20
sessions, 49 % at 5. Long-term mode (weekly, since Nov 2023): buy zone 54 % against a base of 55 %, so no edge there either. In plain
words: on the past year the momentum rule v0 was anti-predictive on NIFTY 50 (a choppy, mean-reverting period), and the "AI score"
must not be sold as predictive until it beats its own table. That table is now the acceptance test for every change to the rule.

## What is real and what is placeholder

* Real: Yahoo quotes and bars (delayed), RSS headlines, NSE constituent CSVs, Upstox instrument master, Yahoo fundamentals, all maths (Greeks, indicators, scoring rules).
* Placeholder, clearly tagged in the UI or the JSON: IPO rows, earnings dates, FII/DII flows, financial calendar events, investor stakes. Each reads a `data/*.json` file the moment one exists; schemas are in the module docstrings. Calendar, earnings and flows samples are now dated relative to today (`deltadesk/markets/calendar.py`: `sample_calendar`, `sample_earnings`, `sample_flows`, `quarter_label`), so they never expire; no sample holiday, because a holiday moves computed expiries. Those three endpoints have no page consumer any more (they served the deleted Markets page) and stay API-only.
* Rules v0 everywhere an "AI" label appears (radar score, council votes, news impact, assistant, IPO agent). Designed so a trained model or an LLM slots in behind the same endpoints. The AI score now has a measured, walk-forward track record (above) and it is negative on the past year; the council, news impact and IPO agent still have none.

## UX

`docs/UX_REVIEW.md` lists what Groww, Kite, moomoo, Robinhood, Screener, Investing, TradingView and Yahoo do well and which of it we adopt. Round 1 is in: global search palette (Ctrl K, `/`) with add-to-watchlist, sticky ticker, mobile bottom bar, toasts, no section numbers. Rounds 2 and 3 are listed there and are frozen until the measurement chain exists.

## Agent chat

`deltadesk/markets/llm.py` picks a provider from `.env` (DD_LLM; free: GROQ_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY; paid: DEEPSEEK_API_KEY, OPENAI_API_KEY; Ollama locally). Requests send a browser-style User-Agent because Cloudflare in front of Groq rejects Python's default one (403 / 1010). Answers are shaped: one summary line, a Metric / Value / Read table, two to four bullets; the watchlist chat renders that markdown. `agent_chat.py` builds a DATA block (quote, filings, ratios, pros / cons, peers, technicals, council votes, headlines) and asks the model to answer only from it; without a key the same block is composed by rules. The reply always ends with the disclaimer. Both chat endpoints are public: with a paid key set on a public host they cost money per visitor question, so start with a free-tier key and add a rate limit before a paid one.

## Decisions taken with the user

* Repository is public on GitHub (24 Sep 2026) under an all-rights-reserved, source-available licence (LICENSE): read and run privately, no reuse in other products. Secrets stay in `.env`, runtime data in `data/`, both ignored.
* Product shape: a small free tier that lands customers with unique data (radar and AI score, heatmap, watchlist, news wire with impact calls, IPO tracker with the IPO agent, fundamental and technical analysis, Telegram alerts), and a premium tier for the agentic side (council at every horizon with explanations, sniper desk, real-time WhatsApp alerts, desk assistant on an LLM, custom rules, real-time data). Do not add features beyond that basic set until launch (reaffirmed 18 Nov 2026 as a freeze on new pages and endpoints).
* WhatsApp: Meta Cloud API is wired (`WhatsAppNotifier`); replies inside a 24-hour window are free, business-initiated alerts are paid utility templates (about ₹0.12 each in India), so free-tier alerts go over Telegram and WhatsApp is a premium or daily-digest channel.
* Product focus: Home (radar + table), News, IPO, Agents, Sniper. The old Markets page and the prototype were deleted in the restructure.
* Free data first: Yahoo (no account) now; Upstox (free account) when the user creates the app; Kite Connect (₹500/month) or Angel One as alternatives. No nseindia.com scraping.
* Look: light grey Mist theme default, filled dark header band with "Join beta" as the only call to action (no beta strip on pages), compact hero written in LLM / AI-agent terms, text nav, no watchlist rail on pages, "Nothing here is investment advice" everywhere. Groww lessons adopted as principles (cards, pill tabs, calm tables, monograms, own icons); see the design skill.
* Sniper page is the pipeline canvas (palette → monitor nodes → gate → order → chart); a new signal is a new `_Monitor` subclass in `deltadesk/agents/monitors.py` (name, label, desc, icon, `step` → `Signal`) plus an icon in the page's `ICON` map, nothing else. Keep the page always dark whatever the site theme.
* Radar: three bands; short term = daily momentum, long term = weekly momentum + fundamentals.
* Public hosting needs `DD_OWNER_TOKEN` set (18 Nov 2026); accounts replace the lock on the watchlist later.
* Work rhythm: one deliverable per day, tests + ruff green, commit and push each day, update this file at the end of each session.

## Next up, in order (pick from the top)

0. **User-only unblockers:** create the Upstox app and log in once; provision the Oracle VM and run `setup.sh`; answer the direction question above. None of the items below needs them to start, but 1 and 2 only become real with the Upstox feed.
1. **Make the score beat its own table (roadmap day 13, calibration):** the track record says momentum v0 lost to the base rate over the past year. Candidates, each judged only by the walk-forward table with the last quarter held out: a regime gate (momentum only while the index sits above its own 200-day average, otherwise neutral), a mean-reversion term for the 2-week leg, a longer look-back, and a per-stock choice between the two by past hit rate. Also show the track record where the score appears elsewhere (analysis head, watchlist column) and the per-agent version on the Agents page (council agents scored the same way, which gives the accuracy badges).
2. **Recorder and replay (roadmap days 6–7):** record every tick, bar and chain snapshot per session to Parquet under `data/ticks/`, with a `replay` feed that replays a recorded day into the pipeline at any speed (`DD_FEED=replay`, `--day`). Runs on the synthetic feed today, on Upstox the day the app exists. The page harness already replays a stream; this is the feed-level version.
3. **Journal (roadmap days 8 and 12):** SQLite store of decisions, fills, cycle reports and agent errors; each decision joined to its outcome (P&L, MAE / MFE, time in trade); `/journal` endpoint and a table on the sniper page. Restart keeps yesterday's journal.
4. **Calibration of the sniper (roadmap day 13):** confidence bucket versus hit rate over recorded and back-filled days; threshold recommendation; the confluence gate's `required` learns from it.
5. **Options agents on the council:** IV rank, OI walls, max pain, expected move; per-agent accuracy badges from item 1.
6. **LLM behind the same endpoints:** news impact analyser, "why" text, assistant. Needs a key; interfaces are isolated (`Analyzer`, `DeskAssistant`). Add a per-IP rate limit on `/chat` and `/agent/chat` first.
7. **Alerts:** Telegram on verdict flips, new bad-impact story on a watchlist stock, sniper decisions, kill switch.
8. **Accounts (UX round 3):** single-user login first (roadmap day 20), then per-user watchlists; retire the owner lock on watchlist writes.
9. **Sniper follow-ups, in the order the top repos suggest:** a bull-versus-bear debate step before the order (needs a language model behind `Analyzer`), per-agent accuracy badges from past votes (the AI-score track record is the pattern), a one-page report per decision from the journal; then more monitor agents (OI change, order-flow imbalance, news impact), several desks per user, backtest a desk over recorded days.
10. **Data feeds that need a licence or a scraper:** BSE quarterly shareholding (fills `data/investors.json` and the ownership agent), IPO calendar (Trendlyne / Tickertape / TrueData, or SEBI + BSE fetcher into `data/ipo.json`; GMP stays out, user decision), earnings dates and FII/DII flows into the `data/*.json` schemas.
11. Radar trails toggle, compare two stocks on the council; phone pass for the parked pages and the Sniper terminal (the kept pages are done).

## Signal confluence engine (sniper v2, 5 Oct 2026)

`deltadesk/agents/monitors.py`: six monitor agents each vote +1 / 0 / −1 from plain rules on 3-min bars (relative volume over the last three bars vs twenty, EMA 9/21 + session VWAP, RSI(14) bands 55–70 / 30–45, regime call, PCR on OI, spot vs PDH/PDL). `ConfluenceAgent` is the AND gate over the monitors on the desk (`DD_SNIPER_MONITORS`, default volume + ma_vwap + rsi + trend; `required` None = all, or k of n with no dissent). When ready inside the trading window, not in cooldown (20 min) and with no open trade in that direction, it writes a Trigger with entry, stop (1.5 ATR, min 0.1 %) and target (2× risk) on the index; strategy builds a bull call / bear put spread, risk rules, exec exits on the spot levels (`spot_stop` / `spot_target`) as well as premium stop / target. Topic `signals` carries every cycle's `Confluence` (all six signals, active flags, why, blocked reason). The zone sniper still runs when the gate is quiet. Index bars now carry the near future's volume (cumulative broker volume → per-minute increments in `FeedAgent`); the synthetic feed clusters volume in bursts so the demo day fires. Tests: `tests/test_monitors.py` (rules, gate, blocks, trend-day fire).

## Hosting

Decision (25 Sep 2026): launch on an Oracle Cloud always-free Ampere VM in Mumbai (4 OCPU, 24 GB). `deploy/oracle/` holds the compose file (app + Caddy), `setup.sh` (one command on a fresh Ubuntu VM; writes `.env` with generated `DD_ADMIN_TOKEN`, `DD_TRAFFIC_SALT` and `DD_OWNER_TOKEN`, prints the owner unlock link) and `deploy.sh` (five-minute pull-based auto-deploy from `main`). Not yet provisioned as of 18 Nov 2026. The Render blueprint and its keep-alive workflow were removed on 27 Sep 2026; everything built for that hosting stays: `/healthz`, the cache warmer, gzip, the placeholder-key guards, the owner Telegram ping on sign-up, and the Postgres waitlist (`DATABASE_URL` → Neon, Supabase or any Postgres).

Hosting checks done while the beta ran on a free container host (24 Sep 2026): all pages 200 from a foreign network, Yahoo quotes, ranking, filings and news reachable, admin endpoint locked, page harness clean against a remote URL (`BASE=https://<host> node tools/page_harness.js ...`), heavy endpoints 0.3–0.6 s once warm. `Dockerfile` honours `$PORT` so any container host works (Docker Desktop was not running on 18 Nov, so the image was not rebuilt locally; CI does not build it either). Hugging Face Docker Spaces became paid; GitHub Pages cannot run the server.

## Speed

`deltadesk/server/warm.py` fills the caches at start (indices, rankings, news, global map, watchlist stats, investors, a few fundamentals) and refreshes the quote-driven ones every few minutes and rankings every ten, so a visitor never triggers the first Yahoo fetches. Responses over 1 KB are gzipped; the quote cache TTL is 180 s. `/healthz` reports the warmer's runs and steps.

## Checks

`uv run ruff check .`, `uv run pytest -q`, and for the pages `node tools/page_harness.js web/pages/<page>.html "#SYMBOL/3m/fundamental"` with the server running (`BASE=http://127.0.0.1:<port>` for another port): it executes the page script against a stub DOM with live data and reports runtime errors (this is what caught the blank Fundamental tab). Since 18 Nov it also loads the shared scripts a page references under `/static/js` (so Home, which needs `ai.js`, runs). CI parse-checks every page with node. For layout, do not trust plain headless `--screenshot` below about 500 px wide: Chrome clamps the window and crops the image; use the DevTools protocol with `Emulation.setDeviceMetricsOverride` (a 40-line node script did it on 18 Nov) and check that `document.documentElement.scrollWidth` equals the viewport.

## Known rough edges

* NIFTY Midcap Select has no Yahoo symbol (no quote). India 10-year G-sec yield has no free source.
* Yahoo's unofficial chart and fundamentals endpoints are the only quote source until Upstox runs; if they change, every page goes blank at once. The Upstox REST quotes provider is the fallback once the app exists.
* News tagging is alias-based; obscure company names may go untagged. Impact lexicon is deliberately simple.
* One shared watchlist for the whole site until accounts; locked to the owner on a public host.
* `SyntheticHistory(weekly=True)` used to loop until the calendar overflowed when its start date fell on a weekend (fixed 18 Nov); the synthetic serve command's long-term mode depended on the day of the week.
* Branch protection on `main` is unavailable on GitHub Free for private repos.
