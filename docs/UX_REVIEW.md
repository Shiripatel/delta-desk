# UX review: what the popular platforms do well, and what Delta Desk takes from each

Principles only; colours, type, icons and layout stay our own (see the design skill).

| Platform | What people love about it | What we take |
|---|---|---|
| Groww | One search box at the top of every screen; a stock page that answers "what is this, is it doing well, what do others hold" in one scroll; clean tables with company logos; a bottom tab bar on mobile with five things | Global search on every page (Ctrl K, `/`), bottom tab bar on phones, logos everywhere, calm tables |
| Zerodha Kite | Watchlist as the home of the workflow; one keystroke to add a symbol; index strip always visible; no clutter, nothing decorative | Sticky index ticker, add-to-watchlist from search and from the stock page, keyboard shortcuts |
| moomoo | A dense dashboard that still breathes: card grid, one readable sans, consistent up / down colour, filled dark header with plain text nav | Filled header, single UI sans, card rhythm, heatmap and global map |
| Robinhood | Very few words on screen; one number and one colour per card; the whole app readable with a thumb | Two-line hero, three sentiment boxes, big price + change on the stock page, mobile spacing |
| Screener.in | Every fundamental on one page, years as columns, pros / cons in plain language, peers table | The Fundamental tab, section nav, pros / cons rules |
| Investing.com | Technicals as a verdict per timeframe, then the indicator and moving-average tables that explain it | The Technical tab: summary strip, indicators, moving averages, pivots |
| TradingView | Symbol search that understands partial names; chart first | Search suggestions with kind pills; chart at the top of Technical |
| Yahoo Finance | Sticky quote header on the stock page; statements in crore with a period toggle | Symbol head that stays put; annual / quarterly toggle |

## What "easy to use" means here

1. **Find any symbol from anywhere.** Search lives in the header of every page and opens with Ctrl K or `/`. Enter opens the analysis, the `+ watch` chip adds to the active watchlist. A toast confirms.
2. **The next action is one click away.** Every stock row opens the analysis; the analysis head has `+ Watchlist`; the watchlist row opens the analysis; the heatmap tile opens the analysis.
3. **Nothing important scrolls away.** The header and the index ticker stay pinned.
4. **Phones get their own nav.** Under 760 px the text nav hides and a five-item bottom bar appears: Home, Watchlist, Search, News, More.
5. **No decorative text.** Section numbers such as `[01]` are gone; headings say what the section is.
6. **One vocabulary.** Buy zone / hold / sell zone, AI score, council, technicals verdict: the same words on Home, Watchlist, Heatmap and Analysis.

## Rounds

* **Round 1 (done):** global search palette, add-to-watchlist from search and analysis, sticky ticker, mobile bottom bar and More sheet, toasts, section numbers removed, three themes.
* **Round 2:** skeleton loading states instead of "loading…" text; empty states with a next step; Home "today at a glance" row (top gainers, losers, most active, most searched); watchlist quick-add star on every ranking row; keyboard navigation in tables.
* **Round 3:** accounts, so watchlists and alerts follow the user; onboarding (pick an index, pick three stocks); saved views; a compact mode toggle for dense tables.

## Agentic trading repos: what the most-starred ones do, and what Delta Desk takes (19 Nov 2026)

Star counts move daily and differ by source; the order is stable. Sources: the GitHub repositories themselves, a March 2026
ranking on dev.to, and the TradingAgents paper (arXiv 2412.20138).

| Repo | Stars (approx.) | What it is | How the user reads it |
|---|---|---|---|
| TauricResearch/TradingAgents | 93k–120k | An LLM "trading firm": an analyst team (fundamentals, sentiment, news, technical) runs in parallel, a bull and a bear researcher debate, a trader proposes, a risk team debates it across risk appetites, a portfolio manager approves or rejects, then a simulated exchange executes | A terminal that shows each agent's stage and status as it runs, then one decision object and a single-page report |
| virattt/ai-hedge-fund | 45k–64k | Agents modelled on named investors plus valuation, sentiment, fundamentals and technicals; a risk manager and a portfolio manager turn their signals into one action per ticker; paper only, explicitly educational | One row per agent: signal, confidence, reasoning; the final decision as action, quantity, confidence, reasoning |
| HKUDS/Vibe-Trading | 24k–34k | A local CLI copilot for a retail trader: natural-language questions, paper trading, chart analysis | A designed terminal, one question and one answer at a time |
| HKUDS/AI-Trader | 21k | Many agents trading in parallel on a platform with a leaderboard | Leaderboard and per-agent pages |
| AI4Finance FinRL / FinGPT | 15k / 21k | Reinforcement learning and financial LLM toolkits | Notebooks and training pipelines |
| NautilusTrader | 30k | A production execution engine | Code, not a screen |
| NoFxAiOS/nofx | 12k | Automated trading with a hard-coded kill switch the model cannot override | Backend runtime |

What they have in common, and what we already had: narrow agents with one job each; every agent output in the same shape
(signal, confidence, a short reason); a separate risk gate that can veto; one typed final decision; paper first and a plain
disclaimer. What they do better on screen, and what the 19 Nov Sniper rebuild took:

1. **One line per agent.** Role, signal and the number that produced it; the sentence of reasoning lives in a tooltip or a report, not
   on the board. The Sniper's agent cards went from four lines to one, the shelf lost its paragraph, the title bars lost their slogans.
2. **Stages with a status, not prose.** TradingAgents shows "analyst team → research → trader → risk → manager" as stages that light
   up. The Sniper's gate shows `1 / 4`, a direction, and one word (`watching`, `ready`, `blocked`, `fired`); the window and cooldown
   moved into the rule's tooltip.
3. **The decision is a card, not a paragraph.** Direction, structure, confidence, entry, stop, target, legs, max loss, margin, and the
   two buttons. The explanation of spreads and exits is a tooltip.
4. **The log is a report you open, not a wall you read.** One line shows the latest event; click to open the stream.

What they have that we do not, in the order we would add it: a bull-versus-bear debate step before the trader (TradingAgents),
which needs a language model behind the same `Analyzer` interface; per-agent accuracy from past calls (the track record built on
18 Nov does this for the AI score and is the pattern for the council); a report per decision (one page: every agent's line, the gate,
the order, the outcome) which the journal in the next-up list will produce.
