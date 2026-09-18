---
name: delta-desk-design
description: Delta Desk's design system. Use whenever you add or change a page, section, table, chart or header in this repo, so every page stays identical in look and a change lands everywhere at once.
---

# Delta Desk design system

One stylesheet owns the look: `static/design.css`. Every page loads it first, then `static/ai.css`
(AI components) or `static/watchlist.css` when it uses them, then a small page-specific `<style>`.
Never redefine tokens, the header, tables or section scaffolding inside a page. If a page needs a
new shared thing, add it to `design.css` and use it from every page.

## Pages and navigation

| route | file | nav label |
|---|---|---|
| `/` | `home.html` | Home (the AI radar and ranking; never call it "radar" in the nav) |
| `/markets` | `markets.html` | Markets |
| `/desk` | `agents.html` | Agents |
| `/prototype` | `prototype/index.html` | (legacy design prototype, not linked) |

Navigation is the segmented control in the header, same three items on every page, `aria-current="page"`
on the current one. Section anchors go in the page body (tabs, `.sec-head`), not in the nav.

## Tokens (from `design.css`)

* Ground `--bg`, ink `--ink` / `--ink-2` / `--ink-3`, hairlines `--line` / `--line-2`, fills `--fill` / `--fill-2`.
* Accent `--accent` (#F386A1) and `--accent-deep` (#D45BB6): highlights, current-tab underline, watchlist stars. Never for data.
* Status: `--good` (up, approved), `--bad` (down, veto), `--warn` (held, upcoming). Always paired with a label or sign, never colour alone.
* Two-series categorical: `--s1` blue, `--s2` orange (calls/puts, FII/DII). Fixed order, never cycled.
* Diverging heat-map ramp `--dn3..--up3` with `--flat` midpoint. Every tile carries a signed label. The colour-safe toggle (`data-safe="1"` on `<html>`) swaps the up pole to blue; keep it on every page.
* Type: JetBrains Mono 300 for data and body; Host Grotesk 500/600 for headlines and big numbers. Tabular numerals via `.num`.
* Dark mode follows `prefers-color-scheme` and `data-theme`; tokens already swap, so pages never hard-code colours.

## Header

`<header class="top"><div class="wrap">` with three zones in one 56px row:
1. `.brand` (✢ Delta Desk + a `.tag` naming the page),
2. `.nav` segmented control (Home · Markets · Agents),
3. `.status` pills of equal height: data source with a `.dot`, clock (`.clock`), colour-safe toggle, and on the Agents page the paper/live `.seg` switch and the `.kill` button.

The watchlist rail (`static/watchlist.*`) is not on any page for now; the watchlist lives as a view on Markets.

Below the header, `.ticker` is the index strip (NIFTY 50, BANK, FIN SERVICE, NEXT 50, SENSEX, VIX) with the data source at the right end.

## Layout rules

* `.wrap` centres content at 1360px with hairline borders on both sides. Sections are separated by hairlines, never shadows or cards with radius above 3px.
* Every section starts with `.sec-head`: `[nn]` index, lowercase label, and a `.meta` line on the right that says what the data is and when it is from.
* Grids use hairlines between cells (`border-right`), collapse to one column under 1000px.
* Tables: uppercase 11px headers, right-aligned `.num` columns, sortable headers are `<button data-k>` with `data-dir` arrows.
* Buttons are outlined, 2px radius; the only filled button is the current nav item and the kill switch.
* Text wears ink tokens. Colour lives in dots, rings, tiles and signed numbers.

## Charts and data marks

Follow the dataviz skill: one axis, thin marks, legend for two or more series, hover tooltip, dark-mode
validated. Shared marks live in `static/ai.css` / `static/ai.js`: score rings (`DDAI.ring`), sparklines
(`DDAI.spark`), the radar (`DDAI.radar`) and the ranking table (`DDAI.ranking`). Reuse them; do not fork.

## Copy

* Sentence case, short labels, no exclamation marks. Numbers are Indian-formatted (`en-IN`), rupees with ₹.
* Every page footer ends with "Nothing here is investment advice." Anything modelled or sampled is tagged
  `example data`, `computed`, `delayed` or `rules model v0` in the UI.

## Checklist before committing a page change

1. `node --check` every inline `<script>` and `static/*.js`.
2. Light and dark render, colour-safe toggle still works.
3. Width 400px: no horizontal scroll except inside `.tbl-wrap`.
4. `uv run pytest tests/test_server.py` passes (routes and assets).
