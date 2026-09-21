---
name: delta-desk-design
description: Delta Desk's design system. Use whenever you add or change a page, section, table, chart or header in this repo, so every page stays identical in look and a change lands everywhere at once.
---

# Delta Desk design system

One stylesheet owns the look: `web/static/css/design.css`. Every page loads it first, then `web/static/css/ai.css`
(AI components) or `static/watchlist.css` when it uses them, then a small page-specific `<style>`.
Never redefine tokens, the header, tables or section scaffolding inside a page. If a page needs a
new shared thing, add it to `design.css` and use it from every page.

## Pages and navigation

| route | file | nav label |
|---|---|---|
| `/` | `web/pages/home.html` | Home (the AI radar and ranking; never call it "radar" in the nav) |
| `/watchlist` | `web/pages/watchlist.html` | Watchlist |
| `/global` | `web/pages/global.html` | Global |
| `/heatmap` | `web/pages/heatmap.html` | Heatmap |
| `/investors` | `web/pages/investors.html` | Investors |
| `/news` | `web/pages/news.html` | News (live wire, impact calls, assistant) |
| `/ipo`, `/ipo/<slug>` | `web/pages/ipo.html` | IPO |
| `/analysis` | `web/pages/analysis.html` | (analysis for any symbol: `/analysis#SYMBOL/3m/<tab>`; every stock, index, FX and commodity click lands here; two tabs, Fundamental (screener-style tables: years as columns, ratios box, pros / cons, peers) and Technical (investing-style: chart, summary per timeframe, indicators, moving averages, pivots); no third-party widget; `/chart` redirects) |
| `/desk` | `web/pages/agents.html` | Agents (the agent council: stock + horizon → verdict) |
| `/sniper` | `web/pages/sniper.html` | Sniper (F&O desk: scope, range with zones, chain, targets, the shot, risk) |
| `/prototype` | `prototype/index.html` | (legacy design prototype, not linked) |

Navigation is five text links in the header (Home · News · IPO · Agents · Sniper), the current one underlined in accent.
The header is a filled band (`--head`, dark ink on the light themes, near-black on the dark ones) with its own text tokens (`--head-ink`, `--head-ink-2`, `--head-line`); the accent pink marks the current page and the single call to action, the "Join beta" pill. Nothing else in the header is filled. The nav is the same ten links on every page, in this order: Home, Watchlist, Heatmap, News, IPO, Forex, Global, Investors, Agents, Sniper; a test checks every page carries all of them. Keep the right side to the minimum: the search button (opens the palette, Ctrl K or `/`), clock, theme, and on the Sniper page the kill switch. Under 760 px the text nav hides and nav.js injects a five-item bottom bar (Home, Watchlist, Search, News, More). The index ticker is sticky under the header. Section headings carry no numbers. No page tag beside the brand (the nav shows where you are), no mode toggles. Section anchors go in the page body (tabs, `.sec-head`), not in the nav.

## Tokens (from `design.css`)

* Ground `--bg`, ink `--ink` / `--ink-2` / `--ink-3`, hairlines `--line` / `--line-2`, fills `--fill` / `--fill-2`.
* Accent `--accent` (#F386A1) and `--accent-deep` (#D45BB6): highlights, current-tab underline, watchlist stars. Never for data.
* Status: `--good` (up, approved), `--bad` (down, veto), `--warn` (held, upcoming). Always paired with a label or sign, never colour alone.
* Two-series categorical: `--s1` blue, `--s2` orange (calls/puts, FII/DII). Fixed order, never cycled.
* Diverging heat-map ramp `--dn3..--up3` with `--flat` midpoint. Every tile carries a signed label. The colour-safe toggle (`data-safe="1"` on `<html>`) swaps the up pole to blue; keep it on every page.
* Type: JetBrains Mono 300 for data and body; Host Grotesk 500/600 for headlines and big numbers. Tabular numerals via `.num`.
* Four themes, all in `design.css`: Mist (light grey, default), White, Paper (warm), Ink (dark), Midnight (blue-black). `web/static/js/nav.js` stamps `data-theme` from the user's choice and adds the switch to the header; pages never hard-code colours. A new colour must be defined for every theme.

## Header

`<header class="top"><div class="wrap">` with three zones in one 56px row:
1. `.brand` (✢ Delta Desk + a `.tag` naming the page),
2. `.nav` text links (Home · News · IPO · Agents · Sniper),
3. `.status` borderless items: theme select (injected by nav.js), clock; the Sniper page adds the paper/live `.seg` switch and the `.kill` button. The data source is shown in the ticker strip, not the header.

The watchlist rail (`static/watchlist.*`) is not on any page for now; the watchlist lives as a view on Markets.

Below the header, `.ticker` is the index strip (NIFTY 50, BANK, FIN SERVICE, NEXT 50, SENSEX, VIX) with the data source at the right end.

## Layout rules

* `.wrap` centres content at 1360px with hairline borders on both sides. Sections are separated by hairlines, never shadows or cards with radius above 3px.
* Every section starts with `.sec-head`: `[nn]` index, lowercase label, and a `.meta` line on the right that says what the data is and when it is from.
* Grids use hairlines between cells (`border-right`), collapse to one column under 1000px.
* Tables: uppercase 11px headers, right-aligned `.num` columns, sortable headers are `<button data-k>` with `data-dir` arrows.
* Buttons are outlined, 2px radius; the only filled button is the current nav item and the kill switch.
* Text wears ink tokens. Colour lives in dots, rings, tiles and signed numbers.

## Page skeleton

Every page is a standalone file in `web/pages/` that links `/static/css/design.css`, then loads `/static/js/common.js` (the `DD` helpers: formatting, fetch, clock, colour-safe toggle, ticker), `/static/js/ui.js` (logos) and `/static/js/nav.js` (theme, beta pill, legal footer). Page scripts start with `DD.boot()` and `DD.ticker({...})`, then their own code. No page re-implements these.

## Actions and feedback

Every symbol leads to its analysis page; the analysis head and the search palette add to the active watchlist; `DD.toast()` confirms any write. See `docs/UX_REVIEW.md` for the platform takeaways behind these rules.

## Tables

Table headers sit on `--thead`, a tone one step darker than the card and far lighter than the header band, in 600 weight ink, with a `--line-2` rule under them; the table card has a `--line-2` outer border so the frame is visible against the ground. Do not restyle headers per page.

## Lessons taken from moomoo (principles, not the look)

* **One readable UI sans for all text** (`--sans`, Inter with Host Grotesk as the display face for the brand and big numbers). Body 13.5px/1.55 at weight 400, headings 600, never light weights for running text. Monospace is for code and logs only; numbers use tabular figures in the sans (`.num`).
* **Hierarchy you can scan:** page title 22px/600, section title 14px/600 in sentence case with the small mono index, meta line 11.5px muted. Secondary inks are dark enough to read (`--ink-2` ≈ 4.5:1 on the ground).
* **Dashboards are card grids:** a row of stat cards, then a map or chart card beside a ranking card, then a full-width table card. Each card has a header row with title left and meta or legend right.
* **Consistent up / down colour** on every number that moves, a range bar for the day's low–high, and a colour map (equal tiles) for a market at a glance.
* **Tab strips** for views inside a page, pills for states, one primary action.
* Dense but airy: 40–48px table rows, 12px card gaps, no decorative borders.

## Lessons taken from Groww (principles, not the look)

* Content sits in **cards** (`.card`: white-ish `--card` surface, 10px radius, hairline) on the grey ground, one card per table.
* **Pill tabs** (`.pills`) for states such as Open / Upcoming / Closed, with a count badge; a small select for a secondary filter.
* **Calm tables everywhere**: `.tbl-wrap` is a card (rounded, hairline, `--card` surface, 20px side margin) and every `table` has a light header band, sentence-case headers, 11px 14px cells, horizontal dividers only, hover highlight. Inside a `.card` use `.tbl-wrap` as is; use `.tbl-wrap.flush` when the table should sit edge to edge.
* **Company logos** via `DDUI.logo(symbol, name)` from `web/static/js/ui.js`: a favicon fetched by the company's domain (`deltadesk/markets/logos.py`, served at `/markets/domains`), with a **monogram** (`.mono`, two initials on a hue from the symbol) underneath as the fallback when no domain is known or the image fails.
* Status as soft **pills** (`.pill.open|upcoming|closed|listed|info|warn`); one action per row as a quiet `.btn` (filled `.btn.primary` only for the main action on a page).
* Generous whitespace beats more content: fewer columns, short dates ("16 Sep 2026"), rupee formatting, no jargon in headers.
* Our own icons only: small stroke SVGs in `currentColor` (`.ico`), never stock icon packs or screenshots of other apps.

## Charts and data marks

Follow the dataviz skill: one axis, thin marks, legend for two or more series, hover tooltip, dark-mode
validated. Shared marks live in `web/static/css/ai.css` / `web/static/js/ai.js`: score rings (`DDAI.ring`), sparklines
(`DDAI.spark`), the radar (`DDAI.radar`) and the ranking table (`DDAI.ranking`). Reuse them; do not fork.

## Copy

* Copy speaks in the product's terms: "LLM agents", "AI agent", "council", "radar", "sniper"; heroes are two lines at most. Sentence case, short labels, no exclamation marks. Numbers are Indian-formatted (`en-IN`), rupees with ₹.
* Every page's `<footer>` is replaced by `web/static/js/nav.js` with the standard legal footer (disclaimer line, SEBI note, copyright, links to `/legal`). Leave an empty `<footer><div class="wrap"></div></footer>` in new pages. The header gets a "Join beta" pill the same way. Every page still ends with "Nothing here is investment advice." Anything modelled or sampled is tagged
  `example data`, `computed`, `delayed` or `rules model v0` in the UI.

## Checklist before committing a page change

1. `node --check` every inline `<script>` and `static/*.js`.
2. Mist, White and Ink all render.
3. Width 400px: no horizontal scroll except inside `.tbl-wrap`.
4. `uv run pytest tests/test_server.py` passes (routes and assets).
