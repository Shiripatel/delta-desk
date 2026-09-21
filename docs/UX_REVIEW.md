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
