"""Company fundamentals for NSE-listed companies: statements, ratios, statistics, dividends, in the shape a
stock-analysis site presents them (fiscal years as columns, annual / quarterly / TTM, growth rows, per-row charts).

Source: Yahoo Finance's public fundamentals time series (annual and quarterly statement lines as filed, in
rupees) plus its chart endpoint for dividends, splits and period-end prices. No key, no crumb; cached on disk
under data/fundamentals/cache for twelve hours. Yahoo serves the last four fiscal years and about eight
quarters; quarterly cash-flow lines are not published for Indian companies, so the quarterly cash-flow table
is thin. Indices, FX and commodities have no statements and return None.

Read model (see compose()):
  periods: annual / quarterly / ttm date lists (oldest first; the page shows newest first)
  tables:  income / balance / cash / ratios, each with rows per period type: {key, label, kind, bold, values}
  statements, ratios, ttm: flat line dictionaries kept for the council, the agent chat and the tests
  snapshot: trailing valuation and the headline ratios; statistics: grouped tables; dividends: history, per FY, splits
"""
from __future__ import annotations

import json
import math
import threading
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

CACHE_DIR = Path("data") / "fundamentals" / "cache"
CRORE = 1e7
BASE = "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{sym}?type={types}&period1={p1}&period2={p2}"
EVENTS = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=15y&interval=1mo&events=div%2Csplits"

# every yahoo line we read: (label, statement, kind)  kind: money (₹ crore) | pershare (₹) | shares (crore)
LINES: dict[str, tuple[str, str, str]] = {
    "TotalRevenue": ("Revenue", "income", "money"), "CostOfRevenue": ("Cost of revenue", "income", "money"),
    "GrossProfit": ("Gross profit", "income", "money"), "SellingGeneralAndAdministration": ("Selling, general & admin", "income", "money"),
    "OperatingExpense": ("Operating expenses", "income", "money"), "OperatingIncome": ("Operating income", "income", "money"),
    "InterestExpense": ("Interest expense", "income", "money"), "InterestIncome": ("Interest income", "income", "money"),
    "PretaxIncome": ("Pre-tax income", "income", "money"), "TaxProvision": ("Income tax", "income", "money"),
    "NetIncome": ("Net income", "income", "money"), "NetIncomeCommonStockholders": ("Net income to common", "income", "money"),
    "BasicEPS": ("EPS (basic)", "income", "pershare"), "DilutedEPS": ("EPS (diluted)", "income", "pershare"),
    "DilutedAverageShares": ("Shares outstanding (diluted)", "income", "shares"), "EBITDA": ("EBITDA", "income", "money"), "EBIT": ("EBIT", "income", "money"),  # noqa: E501
    "ReconciledDepreciation": ("Depreciation & amortisation", "income", "money"),
    "CashAndCashEquivalents": ("Cash & equivalents", "balance", "money"), "OtherShortTermInvestments": ("Short-term investments", "balance", "money"),  # noqa: E501
    "CashCashEquivalentsAndShortTermInvestments": ("Cash & short-term investments", "balance", "money"), "AccountsReceivable": ("Receivables", "balance", "money"),  # noqa: E501
    "Inventory": ("Inventory", "balance", "money"), "OtherCurrentAssets": ("Other current assets", "balance", "money"), "CurrentAssets": ("Total current assets", "balance", "money"),  # noqa: E501
    "NetPPE": ("Property, plant & equipment", "balance", "money"), "Goodwill": ("Goodwill", "balance", "money"), "OtherIntangibleAssets": ("Other intangible assets", "balance", "money"),  # noqa: E501
    "TotalNonCurrentAssets": ("Total non-current assets", "balance", "money"), "TotalAssets": ("Total assets", "balance", "money"),
    "AccountsPayable": ("Accounts payable", "balance", "money"), "CurrentDebt": ("Short-term debt", "balance", "money"), "OtherCurrentLiabilities": ("Other current liabilities", "balance", "money"),  # noqa: E501
    "CurrentLiabilities": ("Total current liabilities", "balance", "money"), "LongTermDebt": ("Long-term debt", "balance", "money"),
    "TotalNonCurrentLiabilitiesNetMinorityInterest": ("Total non-current liabilities", "balance", "money"), "TotalLiabilitiesNetMinorityInterest": ("Total liabilities", "balance", "money"),  # noqa: E501
    "CommonStock": ("Common stock", "balance", "money"), "RetainedEarnings": ("Retained earnings", "balance", "money"), "StockholdersEquity": ("Shareholders' equity", "balance", "money"),  # noqa: E501
    "TotalEquityGrossMinorityInterest": ("Total equity incl. minority", "balance", "money"), "TotalDebt": ("Total debt", "balance", "money"), "NetDebt": ("Net debt", "balance", "money"),  # noqa: E501
    "WorkingCapital": ("Working capital", "balance", "money"), "TangibleBookValue": ("Tangible book value", "balance", "money"), "OrdinarySharesNumber": ("Shares outstanding", "balance", "shares"),  # noqa: E501
    "InvestedCapital": ("Invested capital", "balance", "money"),
    "NetIncomeFromContinuingOperations": ("Net income", "cash", "money"), "DepreciationAndAmortization": ("Depreciation & amortisation", "cash", "money"),  # noqa: E501
    "ChangeInWorkingCapital": ("Change in working capital", "cash", "money"), "ChangeInReceivables": ("Change in receivables", "cash", "money"),  # noqa: E501
    "ChangeInInventory": ("Change in inventory", "cash", "money"), "ChangeInPayable": ("Change in payables", "cash", "money"),
    "OperatingCashFlow": ("Operating cash flow", "cash", "money"), "CapitalExpenditure": ("Capital expenditure", "cash", "money"),
    "NetInvestmentPurchaseAndSale": ("Investment in securities", "cash", "money"), "InvestingCashFlow": ("Investing cash flow", "cash", "money"),  # noqa: E501
    "IssuanceOfDebt": ("Debt issued", "cash", "money"), "RepaymentOfDebt": ("Debt repaid", "cash", "money"), "NetIssuancePaymentsOfDebt": ("Net debt issued (repaid)", "cash", "money"),  # noqa: E501
    "CashDividendsPaid": ("Dividends paid", "cash", "money"), "FinancingCashFlow": ("Financing cash flow", "cash", "money"),
    "ChangesInCash": ("Net cash flow", "cash", "money"), "FreeCashFlow": ("Free cash flow", "cash", "money"), "EndCashPosition": ("Ending cash", "cash", "money"),  # noqa: E501
}
FLOW = {k for k, v in LINES.items() if v[1] in ("income", "cash") and v[2] != "shares"}
TRAILING = ["PeRatio", "ForwardPeRatio", "PbRatio", "PsRatio", "PegRatio", "MarketCap", "EnterpriseValue", "EnterprisesValueEBITDARatio", "EnterprisesValueRevenueRatio"]  # noqa: E501

# tables as shown: (key, label, kind, bold). kind: money | pershare | shares | pct | ratio | growth | price
INCOME_ROWS = [("TotalRevenue", "Revenue", "money", 1), ("g:TotalRevenue", "Revenue growth", "growth", 0), ("CostOfRevenue", "Cost of revenue", "money", 0),  # noqa: E501
               ("GrossProfit", "Gross profit", "money", 1), ("m:gross_margin", "Gross margin", "pct", 0), ("SellingGeneralAndAdministration", "Selling, general & admin", "money", 0),  # noqa: E501
               ("OperatingExpense", "Operating expenses", "money", 0), ("OperatingIncome", "Operating income", "money", 1), ("m:operating_margin", "Operating margin", "pct", 0),  # noqa: E501
               ("InterestExpense", "Interest expense", "money", 0), ("InterestIncome", "Interest income", "money", 0), ("PretaxIncome", "Pre-tax income", "money", 1),  # noqa: E501
               ("TaxProvision", "Income tax", "money", 0), ("m:tax_rate", "Effective tax rate", "pct", 0), ("NetIncome", "Net income", "money", 1), ("g:NetIncome", "Net income growth", "growth", 0),  # noqa: E501
               ("m:net_margin", "Net margin", "pct", 0), ("DilutedEPS", "EPS (diluted)", "pershare", 1), ("g:DilutedEPS", "EPS growth", "growth", 0), ("BasicEPS", "EPS (basic)", "pershare", 0),  # noqa: E501
               ("DilutedAverageShares", "Shares outstanding (diluted)", "shares", 0), ("g:DilutedAverageShares", "Shares change", "growth", 0), ("EBITDA", "EBITDA", "money", 1),  # noqa: E501
               ("m:ebitda_margin", "EBITDA margin", "pct", 0), ("EBIT", "EBIT", "money", 0), ("ReconciledDepreciation", "Depreciation & amortisation", "money", 0)]  # noqa: E501
BALANCE_ROWS = [("CashAndCashEquivalents", "Cash & equivalents", "money", 0), ("OtherShortTermInvestments", "Short-term investments", "money", 0),  # noqa: E501
                ("CashCashEquivalentsAndShortTermInvestments", "Cash & short-term investments", "money", 1), ("g:CashCashEquivalentsAndShortTermInvestments", "Cash growth", "growth", 0),  # noqa: E501
                ("AccountsReceivable", "Receivables", "money", 0), ("Inventory", "Inventory", "money", 0), ("OtherCurrentAssets", "Other current assets", "money", 0),  # noqa: E501
                ("CurrentAssets", "Total current assets", "money", 1), ("NetPPE", "Property, plant & equipment", "money", 0), ("Goodwill", "Goodwill", "money", 0),  # noqa: E501
                ("OtherIntangibleAssets", "Other intangible assets", "money", 0), ("TotalNonCurrentAssets", "Total non-current assets", "money", 0), ("TotalAssets", "Total assets", "money", 1),  # noqa: E501
                ("AccountsPayable", "Accounts payable", "money", 0), ("CurrentDebt", "Short-term debt", "money", 0), ("OtherCurrentLiabilities", "Other current liabilities", "money", 0),  # noqa: E501
                ("CurrentLiabilities", "Total current liabilities", "money", 1), ("LongTermDebt", "Long-term debt", "money", 0), ("TotalNonCurrentLiabilitiesNetMinorityInterest", "Total non-current liabilities", "money", 0),  # noqa: E501
                ("TotalLiabilitiesNetMinorityInterest", "Total liabilities", "money", 1), ("CommonStock", "Common stock", "money", 0), ("RetainedEarnings", "Retained earnings", "money", 0),  # noqa: E501
                ("StockholdersEquity", "Shareholders' equity", "money", 1), ("d:liab_equity", "Total liabilities & equity", "money", 0), ("TotalDebt", "Total debt", "money", 1),  # noqa: E501
                ("d:net_cash", "Net cash (debt)", "money", 0), ("g:d:net_cash", "Net cash growth", "growth", 0), ("d:net_cash_ps", "Net cash per share", "pershare", 0),  # noqa: E501
                ("WorkingCapital", "Working capital", "money", 0), ("d:bvps", "Book value per share", "pershare", 0), ("TangibleBookValue", "Tangible book value", "money", 0),  # noqa: E501
                ("d:tbvps", "Tangible book value per share", "pershare", 0), ("OrdinarySharesNumber", "Shares outstanding", "shares", 0)]
CASH_ROWS = [("NetIncomeFromContinuingOperations", "Net income", "money", 0), ("DepreciationAndAmortization", "Depreciation & amortisation", "money", 0),  # noqa: E501
             ("ChangeInWorkingCapital", "Change in working capital", "money", 0), ("ChangeInReceivables", "Change in receivables", "money", 0), ("ChangeInInventory", "Change in inventory", "money", 0),  # noqa: E501
             ("ChangeInPayable", "Change in payables", "money", 0), ("OperatingCashFlow", "Operating cash flow", "money", 1), ("g:OperatingCashFlow", "Operating cash flow growth", "growth", 0),  # noqa: E501
             ("CapitalExpenditure", "Capital expenditure", "money", 0), ("NetInvestmentPurchaseAndSale", "Investment in securities", "money", 0), ("InvestingCashFlow", "Investing cash flow", "money", 1),  # noqa: E501
             ("IssuanceOfDebt", "Debt issued", "money", 0), ("RepaymentOfDebt", "Debt repaid", "money", 0), ("NetIssuancePaymentsOfDebt", "Net debt issued (repaid)", "money", 0),  # noqa: E501
             ("CashDividendsPaid", "Dividends paid", "money", 0), ("FinancingCashFlow", "Financing cash flow", "money", 1), ("ChangesInCash", "Net cash flow", "money", 1),  # noqa: E501
             ("FreeCashFlow", "Free cash flow", "money", 1), ("g:FreeCashFlow", "Free cash flow growth", "growth", 0), ("m:fcf_margin", "Free cash flow margin", "pct", 0),  # noqa: E501
             ("d:fcf_ps", "Free cash flow per share", "pershare", 0), ("EndCashPosition", "Ending cash", "money", 0)]
RATIO_ROWS = [("r:market_cap", "Market capitalisation", "money", 1), ("g:r:market_cap", "Market cap growth", "growth", 0), ("r:ev", "Enterprise value", "money", 0), ("r:price", "Period-end price", "price", 0),  # noqa: E501
              ("r:pe", "PE ratio", "ratio", 1), ("r:ps", "PS ratio", "ratio", 0), ("r:pb", "PB ratio", "ratio", 0), ("r:ptbv", "P/TBV ratio", "ratio", 0), ("r:pfcf", "P/FCF ratio", "ratio", 0), ("r:pocf", "P/OCF ratio", "ratio", 0),  # noqa: E501
              ("r:ev_sales", "EV/Sales ratio", "ratio", 0), ("r:ev_ebitda", "EV/EBITDA ratio", "ratio", 1), ("r:ev_ebit", "EV/EBIT ratio", "ratio", 0), ("r:ev_fcf", "EV/FCF ratio", "ratio", 0),  # noqa: E501
              ("debt_equity", "Debt / equity ratio", "ratio", 1), ("r:debt_ebitda", "Debt / EBITDA ratio", "ratio", 0), ("r:debt_fcf", "Debt / FCF ratio", "ratio", 0),  # noqa: E501
              ("r:netdebt_equity", "Net debt / equity ratio", "ratio", 0), ("r:netdebt_ebitda", "Net debt / EBITDA ratio", "ratio", 0), ("r:asset_turnover", "Asset turnover", "ratio", 0),  # noqa: E501
              ("r:inventory_turnover", "Inventory turnover", "ratio", 0), ("r:quick", "Quick ratio", "ratio", 0), ("current_ratio", "Current ratio", "ratio", 0), ("interest_coverage", "Interest coverage", "ratio", 0),  # noqa: E501
              ("roe", "Return on equity (ROE)", "pct", 1), ("roa", "Return on assets (ROA)", "pct", 0), ("r:roic", "Return on invested capital (ROIC)", "pct", 0), ("roce", "Return on capital employed (ROCE)", "pct", 0),  # noqa: E501
              ("r:earnings_yield", "Earnings yield", "pct", 0), ("r:fcf_yield", "FCF yield", "pct", 0), ("r:div_yield", "Dividend yield", "pct", 0), ("r:payout", "Payout ratio", "pct", 0),  # noqa: E501
              ("r:buyback_yield", "Buyback yield / dilution", "pct", 0)]
COMPAT_RATIOS = [("gross_margin", "Gross margin %"), ("operating_margin", "Operating margin %"), ("ebitda_margin", "EBITDA margin %"), ("net_margin", "Net margin %"),  # noqa: E501
                 ("roe", "Return on equity %"), ("roa", "Return on assets %"), ("roce", "ROCE %"), ("interest_coverage", "Interest coverage"), ("debt_equity", "Debt to equity"),  # noqa: E501
                 ("current_ratio", "Current ratio"), ("fcf_margin", "FCF margin %"), ("revenue_growth", "Revenue growth %"), ("net_income_growth", "Net income growth %"), ("eps_growth", "EPS growth %")]  # noqa: E501


def _div(a, b, d=4):
    return round(a / b, d) if a is not None and b not in (None, 0) else None


def _pct(a, b):
    v = _div(a, b)
    return round(v * 100, 1) if v is not None else None


def _growth(cur, prev):
    if cur is None or prev is None or prev == 0:
        return None
    return round((cur - prev) / abs(prev) * 100, 1)


def _cagr(a, b, years):
    if not a or not b or a <= 0 or b <= 0 or years <= 0:
        return None
    return round(((b / a) ** (1 / years) - 1) * 100, 1)


def _r(v, d=2):
    return round(v, d) if v is not None and math.isfinite(v) else None


def _avg(vals):
    xs = [v for v in vals if v is not None]
    return round(sum(xs) / len(xs), 1) if xs else None


class YahooFundamentals:
    name = "yahoo fundamentals"

    def __init__(self, ttl: float = 12 * 3600, timeout: float = 15.0, cache_dir: Path = CACHE_DIR, bars=None) -> None:
        self.ttl, self.timeout, self.cache_dir, self.bars = ttl, timeout, cache_dir, bars
        self._mem: dict[str, tuple[float, dict | None]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def yahoo_symbol(symbol: str) -> str | None:
        from deltadesk.markets import universe
        s = symbol.upper()
        if s in universe.INDICES or s in universe.GLOBAL_BY_KEY or s in universe.FX_WORLD_BY_KEY or s.startswith("FUT:") or s in {f[0] for f in universe.FX}:  # noqa: E501
            return None
        return f"{s}.NS"

    def _get(self, url: str) -> dict:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (DeltaDesk)"})
        with urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _fetch(self, ysym: str) -> dict:
        now = int(time.time())
        out: dict = {"annual": {}, "quarterly": {}, "trailing": {}}
        keys = list(LINES)
        for n, chunk in enumerate((keys[:40], keys[40:])):
            types = ",".join([f"annual{k}" for k in chunk] + [f"quarterly{k}" for k in chunk] + ([f"trailing{k}" for k in TRAILING] if n == 0 else []))  # noqa: E501
            raw = self._get(BASE.format(sym=quote(ysym), types=types, p1=now - 12 * 365 * 86400, p2=now))
            for res in raw.get("timeseries", {}).get("result", []):
                t = res["meta"]["type"][0]
                for freq in ("annual", "quarterly", "trailing"):
                    if t.startswith(freq):
                        line = t[len(freq):]
                        for row in res.get(t) or []:
                            if row and row.get("reportedValue", {}).get("raw") is not None:
                                out[freq].setdefault(line, {})[row["asOfDate"]] = float(row["reportedValue"]["raw"])
                        break
        try:
            ev = self._get(EVENTS.format(sym=quote(ysym)))["chart"]["result"][0]
            evs = ev.get("events", {})
            out["dividends"] = sorted([{"date": date.fromtimestamp(v["date"]).isoformat(), "amount": v["amount"]} for v in evs.get("dividends", {}).values()], key=lambda x: x["date"])  # noqa: E501
            out["splits"] = sorted([{"date": date.fromtimestamp(v["date"]).isoformat(), "ratio": v.get("splitRatio")} for v in evs.get("splits", {}).values()], key=lambda x: x["date"])  # noqa: E501
            ts, cl = ev.get("timestamp", []), (ev.get("indicators", {}).get("quote", [{}])[0].get("close") or [])
            out["monthly"] = [{"date": date.fromtimestamp(t).isoformat(), "close": c} for t, c in zip(ts, cl, strict=False) if c is not None]  # noqa: E501
            out["meta"] = {k: ev["meta"].get(k) for k in ("currency", "fullExchangeName", "firstTradeDate", "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "regularMarketPrice")}  # noqa: E501
        except Exception:  # noqa: BLE001 - events are optional
            out["dividends"], out["splits"], out["monthly"], out["meta"] = [], [], [], {}
        return out

    def raw(self, symbol: str, refresh: bool = False) -> dict | None:
        ysym = self.yahoo_symbol(symbol)
        if ysym is None:
            return None
        key = symbol.upper()
        now = time.time()
        with self._lock:
            hit = self._mem.get(key)
            if hit and not refresh and now - hit[0] < self.ttl:
                return hit[1]
        f = self.cache_dir / f"{key}.json"
        if f.exists() and not refresh:
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                if now - d.get("fetched_at", 0) < self.ttl and "monthly" in (d.get("series") or {}):
                    with self._lock:
                        self._mem[key] = (d["fetched_at"], d)
                    return d
            except (json.JSONDecodeError, KeyError, AttributeError):
                pass
        try:
            data = self._fetch(ysym)
        except Exception as exc:  # noqa: BLE001 - network failure is reported, not raised
            with self._lock:
                self._mem[key] = (now, None)
            return {"error": str(exc), "fetched_at": now, "series": None}
        d = {"symbol": key, "yahoo": ysym, "fetched_at": now, "series": data}
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(d), encoding="utf-8")
        with self._lock:
            self._mem[key] = (now, d)
        return d

    def analysis(self, symbol: str, refresh: bool = False) -> dict | None:
        d = self.raw(symbol, refresh)
        if d is None:
            return None
        if not d.get("series"):
            return {"symbol": symbol.upper(), "error": d.get("error", "no data"), "source": self.name}
        daily = None
        if self.bars is not None:
            try:
                daily = [{"date": date.fromtimestamp(b.ts).isoformat(), "close": b.close, "volume": b.volume} for b in self.bars.bars_for(symbol.upper(), "1y", "1d")]  # noqa: E501
            except Exception:  # noqa: BLE001
                daily = None
        return compose(d, daily=daily)

    def council_summary(self, symbol: str) -> tuple[dict | None, str]:
        a = self.analysis(symbol)
        if not a or a.get("error"):
            return None, "no data (" + (a.get("error", "not a listed company") if a else "not a listed company") + ")"
        return a["council"], f"{self.name} · FY{a['periods']['annual'][-1][:4]}" if a["periods"]["annual"] else self.name


# ---- composition ---------------------------------------------------------------------------------------
def compose(d: dict, daily: list[dict] | None = None) -> dict:
    series = d["series"]
    out: dict = {"symbol": d["symbol"], "yahoo": d["yahoo"], "source": "yahoo fundamentals", "fetched_at": d["fetched_at"], "currency": "INR", "unit": "₹ crore",  # noqa: E501
                 "lines": {k: {"label": v[0], "statement": v[1], "kind": v[2]} for k, v in LINES.items()}, "ratio_labels": dict(COMPAT_RATIOS),  # noqa: E501
                 "periods": {}, "statements": {}, "ratios": {}, "ttm": {}, "ttm_prev": {}, "tables": {"income": {}, "balance": {}, "cash": {}, "ratios": {}}}  # noqa: E501
    base: dict[str, dict[str, dict[str, float | None]]] = {}
    for freq in ("annual", "quarterly"):
        s = series.get(freq, {})
        dates = sorted({dt for line in s.values() for dt in line})
        dates = dates[-6:] if freq == "annual" else dates[-8:]
        out["periods"][freq] = dates
        st: dict[str, dict[str, float | None]] = {}
        for line, (_, _, kind) in LINES.items():
            vals = s.get(line, {})
            st[line] = {dt: (round(vals[dt] / CRORE, 1) if kind in ("money", "shares") else round(vals[dt], 2)) if dt in vals else None for dt in dates}  # noqa: E501
        base[freq] = st
        out["statements"][freq] = st
    # TTM per quarter end: rolling four quarters for flows, latest quarter for stocks
    qd, q, ad = out["periods"]["quarterly"], base["quarterly"], out["periods"]["annual"]
    ttm_dates = [dt for i, dt in enumerate(qd) if i >= 3]
    ttm: dict[str, dict[str, float | None]] = {}
    for line in LINES:
        ttm[line] = {}
        for i, dt in enumerate(qd):
            if i < 3:
                continue
            if line in FLOW:
                window = qd[i - 3:i + 1]
                consecutive = all(_months_apart(window[j], window[j + 1]) <= 4 for j in range(3))
                vals = [q[line].get(x) for x in window]
                ttm[line][dt] = round(sum(vals), 2) if consecutive and all(v is not None for v in vals) else None
            else:
                ttm[line][dt] = q[line].get(dt)
    for line in LINES:   # a skipped quarter or no quarterly cash flows (India): the latest TTM falls back to the last annual figure
        if ttm_dates and ttm[line].get(ttm_dates[-1]) is None and ad and line in FLOW:
            ttm[line][ttm_dates[-1]] = base["annual"][line].get(ad[-1])
    base["ttm"] = ttm
    out["periods"]["ttm"] = ttm_dates
    out["ttm"] = {line: ttm[line].get(ttm_dates[-1]) for line in LINES} if ttm_dates else {}
    out["ttm_prev"] = {line: ttm[line].get(ttm_dates[-5]) for line in ("TotalRevenue", "NetIncome", "DilutedEPS")} if len(ttm_dates) >= 5 else {}  # noqa: E501
    # prices at period ends, dividends per period
    mclose = [(m["date"], m["close"]) for m in (series.get("monthly") or [])]
    last_px = (series.get("meta") or {}).get("regularMarketPrice") or (daily[-1]["close"] if daily else (mclose[-1][1] if mclose else None))

    def px_at(dt: str) -> float | None:
        best = None
        for mdt, c in mclose:
            if mdt[:7] <= dt[:7]:
                best = c
        return best
    divs = series.get("dividends") or []

    def dps_between(a: str | None, b: str) -> float:
        return round(sum(x["amount"] for x in divs if (a is None or x["date"] > a) and x["date"] <= b), 2)

    def build(freq: str) -> dict:
        st, dates = base[freq], out["periods"][freq]
        back = 1 if freq == "annual" else 4
        prev_of = {dt: (dates[i - back] if i >= back else None) for i, dt in enumerate(dates)}
        k = 1 if freq != "quarterly" else 4     # annualise flows for quarterly ratios
        dv: dict[str, dict[str, float | None]] = {}

        def g(line, dt):
            return st.get(line, {}).get(dt)
        for idx, dt in enumerate(dates):
            rev, ni, eq, ta, cl, ca = g("TotalRevenue", dt), g("NetIncome", dt), g("StockholdersEquity", dt), g("TotalAssets", dt), g("CurrentLiabilities", dt), g("CurrentAssets", dt)  # noqa: E501
            debt, ebitda, fcf, ocf = g("TotalDebt", dt), g("EBITDA", dt), g("FreeCashFlow", dt), g("OperatingCashFlow", dt)
            ebit = g("EBIT", dt) if g("EBIT", dt) is not None else g("OperatingIncome", dt)
            shares = g("OrdinarySharesNumber", dt) or g("DilutedAverageShares", dt)
            cash = g("CashCashEquivalentsAndShortTermInvestments", dt) if g("CashCashEquivalentsAndShortTermInvestments", dt) is not None else g("CashAndCashEquivalents", dt)  # noqa: E501
            net_cash = (cash - debt) if cash is not None and debt is not None else (-g("NetDebt", dt) if g("NetDebt", dt) is not None else None)  # noqa: E501
            px = last_px if (freq == "ttm" and dt == dates[-1]) else px_at(dt)
            mcap = round(px * shares, 1) if px and shares else None
            ev = round(mcap - net_cash, 1) if mcap is not None and net_cash is not None else None
            eps = g("DilutedEPS", dt)
            tax = _pct(g("TaxProvision", dt), g("PretaxIncome", dt))
            prev = prev_of.get(dt)
            dps = dps_between(prev, dt) if prev else (dps_between(None, dt) if idx == 0 and freq == "annual" else None)
            div_paid = g("CashDividendsPaid", dt)
            an = lambda v: v * k if v is not None else None  # noqa: E731
            vals = {
                "gross_margin": _pct(g("GrossProfit", dt), rev), "operating_margin": _pct(g("OperatingIncome", dt), rev), "ebitda_margin": _pct(ebitda, rev), "net_margin": _pct(ni, rev),  # noqa: E501
                "tax_rate": tax, "fcf_margin": _pct(fcf, rev), "roe": _pct(an(ni), eq), "roa": _pct(an(ni), ta),
                "roce": _pct(an(ebit), (ta - cl) if ta is not None and cl is not None else None),
                "roic": _pct(an(ebit) * (1 - (tax if tax is not None else 25) / 100) if ebit is not None else None, g("InvestedCapital", dt) or (((eq or 0) + (debt or 0)) or None)),  # noqa: E501
                "interest_coverage": _div(ebit, g("InterestExpense", dt), 2), "debt_equity": _div(debt, eq, 2), "current_ratio": _div(ca, cl, 2),  # noqa: E501
                "quick": _div((ca - (g("Inventory", dt) or 0)) if ca is not None else None, cl, 2), "asset_turnover": _div(an(rev), ta, 2),
                "inventory_turnover": _div(an(g("CostOfRevenue", dt)), g("Inventory", dt), 2), "debt_ebitda": _div(debt, an(ebitda), 2), "debt_fcf": _div(debt, an(fcf), 2),  # noqa: E501
                "netdebt_equity": _div(-net_cash if net_cash is not None else None, eq, 2), "netdebt_ebitda": _div(-net_cash if net_cash is not None else None, an(ebitda), 2),  # noqa: E501
                "revenue_growth": _growth(rev, st["TotalRevenue"].get(prev)) if prev else None, "net_income_growth": _growth(ni, st["NetIncome"].get(prev)) if prev else None,  # noqa: E501
                "eps_growth": _growth(eps, st["DilutedEPS"].get(prev)) if prev else None,
                "liab_equity": (g("TotalLiabilitiesNetMinorityInterest", dt) + eq) if g("TotalLiabilitiesNetMinorityInterest", dt) is not None and eq is not None else ta,  # noqa: E501
                "net_cash": _r(net_cash, 1), "net_cash_ps": _div(net_cash, shares, 2), "bvps": _div(eq, shares, 2), "tbvps": _div(g("TangibleBookValue", dt), shares, 2), "fcf_ps": _div(fcf, shares, 2),  # noqa: E501
                "market_cap": mcap, "ev": ev, "price": _r(px, 2),
                "pe": _div(px, an(eps) if eps else None, 2), "ps": _div(mcap, an(rev) if rev else None, 2), "pb": _div(mcap, eq, 2), "ptbv": _div(mcap, g("TangibleBookValue", dt), 2),  # noqa: E501
                "pfcf": _div(mcap, an(fcf) if fcf else None, 2), "pocf": _div(mcap, an(ocf) if ocf else None, 2),
                "ev_sales": _div(ev, an(rev) if rev else None, 2), "ev_ebitda": _div(ev, an(ebitda) if ebitda else None, 2), "ev_ebit": _div(ev, an(ebit) if ebit else None, 2), "ev_fcf": _div(ev, an(fcf) if fcf else None, 2),  # noqa: E501
                "earnings_yield": _pct(an(eps) if eps else None, px), "fcf_yield": _pct(an(fcf) if fcf else None, mcap), "div_yield": _pct(dps, px) if dps else None,  # noqa: E501
                "payout": _pct(abs(div_paid), ni) if div_paid and ni else (_pct(dps, an(eps)) if dps and eps else None), "dps": dps,
            }
            s_prev = (st["OrdinarySharesNumber"].get(prev) or st["DilutedAverageShares"].get(prev)) if prev else None
            vals["buyback_yield"] = -_growth(shares, s_prev) if shares and s_prev and _growth(shares, s_prev) is not None else None
            for key, v in vals.items():
                dv.setdefault(key, {})[dt] = v
        return dv
    derived = {freq: build(freq) for freq in ("annual", "quarterly", "ttm")}
    for freq in ("annual", "quarterly", "ttm"):
        out["ratios"][freq] = {k: derived[freq].get(k, {}) for k, _ in COMPAT_RATIOS}

    def value(freq, key, dt):
        if key.startswith("g:"):
            dates = out["periods"][freq]
            i, back = dates.index(dt), (1 if freq == "annual" else 4)
            prev = dates[i - back] if i >= back else None
            return _growth(value(freq, key[2:], dt), value(freq, key[2:], prev) if prev else None)
        if key[:2] in ("m:", "d:", "r:"):
            return derived[freq].get(key[2:], {}).get(dt)
        if key in base[freq]:
            return base[freq][key].get(dt)
        return derived[freq].get(key, {}).get(dt)
    for name, rows in (("income", INCOME_ROWS), ("balance", BALANCE_ROWS), ("cash", CASH_ROWS), ("ratios", RATIO_ROWS)):
        for freq in ("annual", "quarterly", "ttm"):
            dates = out["periods"][freq]
            table = []
            for key, label, kind, bold in rows:
                vals = {dt: value(freq, key, dt) for dt in dates}
                if any(v is not None for v in vals.values()):
                    table.append({"key": key, "label": label, "kind": kind, "bold": bool(bold), "values": vals})
            out["tables"][name][freq] = table
    # snapshot (compat keys kept) --------------------------------------------------------------------------
    tr = {k: (sorted(v.items())[-1][1] if v else None) for k, v in series.get("trailing", {}).items()}
    a, last = base["annual"], (ad[-1] if ad else None)
    first = ad[-4] if len(ad) >= 4 else (ad[0] if ad else None)
    years = 3 if len(ad) >= 4 else max(1, len(ad) - 1)
    T = out["ttm"]
    rev_ttm = T.get("TotalRevenue") or (a["TotalRevenue"].get(last) if last else None)
    ni_ttm = T.get("NetIncome") or (a["NetIncome"].get(last) if last else None)
    eps_ttm = T.get("DilutedEPS") or (a["DilutedEPS"].get(last) if last else None)
    eq = a["StockholdersEquity"].get(last) if last else None
    debt = a["TotalDebt"].get(last) if last else None
    tt, tdt = derived["ttm"], (ttm_dates[-1] if ttm_dates else None)
    lastq = qd[-1] if qd else None
    shares_now = (base["quarterly"]["OrdinarySharesNumber"].get(lastq) if lastq else None) or (a["OrdinarySharesNumber"].get(last) if last else None)  # noqa: E501
    mcap_now = round(tr["MarketCap"] / CRORE) if tr.get("MarketCap") else (round(last_px * shares_now) if last_px and shares_now else None)
    today = date.today().isoformat()
    dps_ttm = dps_between(f"{int(today[:4]) - 1}{today[4:]}", today) if divs else None
    rt = lambda key: tt.get(key, {}).get(tdt) if tdt else None  # noqa: E731
    out["snapshot"] = {
        "pe": _r(tr.get("PeRatio")) or _div(last_px, eps_ttm, 2), "forward_pe": _r(tr.get("ForwardPeRatio")), "pb": _r(tr.get("PbRatio")) or _div(mcap_now, eq, 2), "ps": _r(tr.get("PsRatio")) or _div(mcap_now, rev_ttm, 2),  # noqa: E501
        "peg": _r(tr.get("PegRatio")), "market_cap_cr": mcap_now, "ev_cr": round(tr["EnterpriseValue"] / CRORE) if tr.get("EnterpriseValue") else rt("ev"),  # noqa: E501
        "ev_ebitda": _r(tr.get("EnterprisesValueEBITDARatio")) or rt("ev_ebitda"), "ev_revenue": _r(tr.get("EnterprisesValueRevenueRatio")) or rt("ev_sales"),  # noqa: E501
        "revenue_ttm_cr": rev_ttm, "net_income_ttm_cr": ni_ttm, "eps_ttm": eps_ttm, "net_margin": _pct(ni_ttm, rev_ttm), "roe": _pct(ni_ttm, eq), "debt_equity": _div(debt, eq),  # noqa: E501
        "fcf_ttm_cr": T.get("FreeCashFlow") or (a["FreeCashFlow"].get(last) if last else None),
        "revenue_cagr_3y": _cagr(a["TotalRevenue"].get(first), a["TotalRevenue"].get(last), years) if first and last else None,
        "eps_cagr_3y": _cagr(a["DilutedEPS"].get(first), a["DilutedEPS"].get(last), years) if first and last else None, "fy": last,
        "roce": out["ratios"]["annual"]["roce"].get(last) if last else None, "interest_coverage": out["ratios"]["annual"]["interest_coverage"].get(last) if last else None,  # noqa: E501
        "revenue_ttm_growth": _growth(T.get("TotalRevenue"), out["ttm_prev"].get("TotalRevenue")), "net_income_ttm_growth": _growth(T.get("NetIncome"), out["ttm_prev"].get("NetIncome")),  # noqa: E501
        "roe_3y_avg": _avg([out["ratios"]["annual"]["roe"].get(dt) for dt in ad[-3:]]), "revenue_cagr_1y": out["ratios"]["annual"]["revenue_growth"].get(last) if last else None,  # noqa: E501
        "profit_cagr_1y": out["ratios"]["annual"]["net_income_growth"].get(last) if last else None, "shares_cr": shares_now, "price": _r(last_px, 2),  # noqa: E501
        "dps_ttm": dps_ttm, "dividend_yield": _pct(dps_ttm, last_px) if dps_ttm else None, "last_dividend": divs[-1] if divs else None,
    }
    s = out["snapshot"]
    out["pros"], out["cons"] = pros_cons(s)
    out["council"] = {"pe": s["pe"], "pb": s["pb"], "roe": s["roe"], "debt_equity": s["debt_equity"], "revenue_growth": s["revenue_cagr_3y"],  # noqa: E501
                      "eps_growth": s["eps_cagr_3y"], "dividend_yield": s["dividend_yield"], "promoter_holding": None, "fii_holding": None, "source": "yahoo fundamentals"}  # noqa: E501
    by_fy: dict[int, float] = {}
    for x in divs:
        y, m = int(x["date"][:4]), int(x["date"][5:7])
        fy = y if m <= 3 else y + 1
        by_fy[fy] = round(by_fy.get(fy, 0) + x["amount"], 2)
    fys = sorted(by_fy)
    cur_fy = date.today().year + (1 if date.today().month > 3 else 0)
    out["dividends"] = {"history": divs[-40:], "splits": series.get("splits") or [], "years_paying": len([y for y in fys if y < cur_fy]), "ttm_dps": dps_ttm,  # noqa: E501
                        "by_fy": [{"fy": y, "dps": by_fy[y], "partial": y >= cur_fy, "growth": _growth(by_fy[y], by_fy.get(y - 1)) if (y - 1) in by_fy and y < cur_fy else None,  # noqa: E501
                                   "yield": _pct(by_fy[y], px_at(f"{y}-03-31")) if px_at(f"{y}-03-31") else None,
                                   "payout": _pct(by_fy[y], a["DilutedEPS"].get(f"{y}-03-31")) if a["DilutedEPS"].get(f"{y}-03-31") else None} for y in fys[-10:]]}  # noqa: E501
    out["fiscal_note"] = _fiscal_note(last)
    out["statistics"] = statistics(out, base, derived, daily)
    out["overview"] = {"performance": [{"fy": dt, "revenue": a["TotalRevenue"].get(dt), "gross_profit": a["GrossProfit"].get(dt), "operating_income": a["OperatingIncome"].get(dt),  # noqa: E501
                                        "net_income": a["NetIncome"].get(dt), "revenue_growth": out["ratios"]["annual"]["revenue_growth"].get(dt),  # noqa: E501
                                        "net_income_growth": out["ratios"]["annual"]["net_income_growth"].get(dt)} for dt in ad], "meta": series.get("meta") or {}}  # noqa: E501
    return out


def _months_apart(a: str, b: str) -> int:
    return (int(b[:4]) - int(a[:4])) * 12 + (int(b[5:7]) - int(a[5:7]))


def _fiscal_note(last: str | None) -> str:
    if not last:
        return "Financials in ₹ crore."
    m = int(last[5:7])
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    return f"Financials in ₹ crore. Fiscal year is {months[m % 12]} – {months[m - 1]}."


def statistics(out: dict, base: dict, derived: dict, daily: list[dict] | None) -> dict:
    s, T, ad, qd, a = out["snapshot"], out["ttm"], out["periods"]["annual"], out["periods"]["quarterly"], base["annual"]
    last, prev = (ad[-1] if ad else None), (ad[-2] if len(ad) >= 2 else None)
    tdt = out["periods"]["ttm"][-1] if out["periods"]["ttm"] else None
    r = lambda k: derived["ttm"].get(k, {}).get(tdt) if tdt else None  # noqa: E731
    an = lambda k, dt=last: derived["annual"].get(k, {}).get(dt) if dt else None  # noqa: E731
    ps: dict = {}
    if daily and len(daily) > 60:
        closes = [b["close"] for b in daily]
        ps["52w_change"] = _growth(closes[-1], closes[0])
        ps["dma50"] = round(sum(closes[-50:]) / 50, 2)
        ps["dma200"] = round(sum(closes[-200:]) / min(200, len(closes)), 2)
        g = lo = 0.0
        for i in range(len(closes) - 14, len(closes)):
            d = closes[i] - closes[i - 1]
            g += max(d, 0)
            lo += max(-d, 0)
        ps["rsi14"] = round(100 - 100 / (1 + g / lo), 1) if lo else 100.0
        vols = [b.get("volume") or 0 for b in daily[-20:]]
        ps["avg_volume_20d"] = round(sum(vols) / len(vols)) if vols else None
    z = None
    if last:
        wc, re_, ebit, tl, sales, ta, mcap = (a["WorkingCapital"].get(last), a["RetainedEarnings"].get(last), a["EBIT"].get(last) if a["EBIT"].get(last) is not None else a["OperatingIncome"].get(last),  # noqa: E501
                                             a["TotalLiabilitiesNetMinorityInterest"].get(last), a["TotalRevenue"].get(last), a["TotalAssets"].get(last), s.get("market_cap_cr"))  # noqa: E501
        if None not in (wc, re_, ebit, tl, sales, ta, mcap) and ta and tl:
            z = round(1.2 * wc / ta + 1.4 * re_ / ta + 3.3 * ebit / ta + 0.6 * mcap / tl + 1.0 * sales / ta, 2)
    f = None
    if last and prev:
        ni, ocf = a["NetIncome"].get(last), a["OperatingCashFlow"].get(last)
        checks = [(an("roa") or 0) > 0, (ocf or 0) > 0, (an("roa") or 0) > (an("roa", prev) or 0), (ocf or 0) > (ni or 0),
                  (a["LongTermDebt"].get(last) or 0) / (a["TotalAssets"].get(last) or 1) <= (a["LongTermDebt"].get(prev) or 0) / (a["TotalAssets"].get(prev) or 1),  # noqa: E501
                  (an("current_ratio") or 0) > (an("current_ratio", prev) or 0), (a["OrdinarySharesNumber"].get(last) or 0) <= (a["OrdinarySharesNumber"].get(prev) or 0) * 1.001,  # noqa: E501
                  (an("gross_margin") or 0) > (an("gross_margin", prev) or 0), (an("asset_turnover") or 0) > (an("asset_turnover", prev) or 0)]  # noqa: E501
        f = sum(1 for c in checks if c)
    lastq = qd[-1] if qd else None
    bq = base["quarterly"]
    dv = out["dividends"]
    groups = {
        "Total valuation": [("Market cap", s.get("market_cap_cr"), "money"), ("Enterprise value", s.get("ev_cr"), "money")],
        "Share statistics": [("Shares outstanding", s.get("shares_cr"), "shares"), ("Shares change (YoY)", -an("buyback_yield") if an("buyback_yield") is not None else None, "pct"),  # noqa: E501
                             ("Shares change (QoQ)", _growth(s.get("shares_cr"), bq["OrdinarySharesNumber"].get(qd[-2]) if len(qd) >= 2 else None), "pct"),  # noqa: E501
                             ("Shares a year ago", bq["OrdinarySharesNumber"].get(qd[-5]) if len(qd) >= 5 else None, "shares")],
        "Valuation ratios": [("PE ratio", s.get("pe"), "ratio"), ("Forward PE", s.get("forward_pe"), "ratio"), ("PS ratio", s.get("ps"), "ratio"), ("PB ratio", s.get("pb"), "ratio"),  # noqa: E501
                             ("P/TBV ratio", r("ptbv"), "ratio"), ("P/FCF ratio", r("pfcf"), "ratio"), ("P/OCF ratio", r("pocf"), "ratio"), ("PEG ratio", s.get("peg"), "ratio")],  # noqa: E501
        "Enterprise valuation": [("EV / sales", s.get("ev_revenue"), "ratio"), ("EV / EBITDA", s.get("ev_ebitda"), "ratio"), ("EV / EBIT", r("ev_ebit"), "ratio"), ("EV / FCF", r("ev_fcf"), "ratio")],  # noqa: E501
        "Financial position": [("Current ratio", r("current_ratio") or an("current_ratio"), "ratio"), ("Quick ratio", r("quick") or an("quick"), "ratio"), ("Debt / equity", s.get("debt_equity"), "ratio"),  # noqa: E501
                               ("Debt / EBITDA", r("debt_ebitda") or an("debt_ebitda"), "ratio"), ("Debt / FCF", an("debt_fcf"), "ratio"), ("Interest coverage", s.get("interest_coverage"), "ratio")],  # noqa: E501
        "Financial efficiency": [("Return on equity (ROE)", s.get("roe"), "pct"), ("Return on assets (ROA)", r("roa") or an("roa"), "pct"), ("Return on invested capital (ROIC)", r("roic") or an("roic"), "pct"),  # noqa: E501
                                 ("Return on capital employed (ROCE)", s.get("roce"), "pct"), ("Asset turnover", r("asset_turnover") or an("asset_turnover"), "ratio"),  # noqa: E501
                                 ("Inventory turnover", r("inventory_turnover") or an("inventory_turnover"), "ratio")],
        "Taxes": [("Income tax (TTM)", T.get("TaxProvision"), "money"), ("Effective tax rate", r("tax_rate") or an("tax_rate"), "pct")],
        "Stock price statistics": [("52-week price change", ps.get("52w_change"), "pct"), ("50-day moving average", ps.get("dma50"), "price"), ("200-day moving average", ps.get("dma200"), "price"),  # noqa: E501
                                   ("Relative strength index (RSI)", ps.get("rsi14"), "ratio"), ("Average volume (20 days)", ps.get("avg_volume_20d"), "int")],  # noqa: E501
        "Income statement (TTM)": [("Revenue", T.get("TotalRevenue"), "money"), ("Gross profit", T.get("GrossProfit"), "money"), ("Operating income", T.get("OperatingIncome"), "money"),  # noqa: E501
                                   ("Pre-tax income", T.get("PretaxIncome"), "money"), ("Net income", T.get("NetIncome"), "money"), ("EBITDA", T.get("EBITDA"), "money"), ("EBIT", T.get("EBIT"), "money"),  # noqa: E501
                                   ("Earnings per share (EPS)", T.get("DilutedEPS"), "pershare")],
        "Balance sheet": [("Cash & short-term investments", bq["CashCashEquivalentsAndShortTermInvestments"].get(lastq) if lastq else None, "money"),  # noqa: E501
                          ("Total debt", bq["TotalDebt"].get(lastq) if lastq else None, "money"), ("Net cash (debt)", r("net_cash"), "money"), ("Net cash per share", r("net_cash_ps"), "pershare"),  # noqa: E501
                          ("Equity (book value)", bq["StockholdersEquity"].get(lastq) if lastq else None, "money"), ("Book value per share", r("bvps"), "pershare"),  # noqa: E501
                          ("Working capital", bq["WorkingCapital"].get(lastq) if lastq else None, "money")],
        "Cash flow (TTM)": [("Operating cash flow", T.get("OperatingCashFlow"), "money"), ("Capital expenditure", T.get("CapitalExpenditure"), "money"),  # noqa: E501
                            ("Depreciation & amortisation", T.get("DepreciationAndAmortization"), "money"), ("Net borrowing", T.get("NetIssuancePaymentsOfDebt"), "money"),  # noqa: E501
                            ("Free cash flow", T.get("FreeCashFlow"), "money"), ("FCF per share", r("fcf_ps"), "pershare")],
        "Margins": [("Gross margin", r("gross_margin"), "pct"), ("Operating margin", r("operating_margin"), "pct"), ("Pre-tax margin", _pct(T.get("PretaxIncome"), T.get("TotalRevenue")), "pct"),  # noqa: E501
                    ("Profit margin", s.get("net_margin"), "pct"), ("EBITDA margin", r("ebitda_margin"), "pct"), ("FCF margin", r("fcf_margin"), "pct")],  # noqa: E501
        "Dividends & yields": [("Dividend per share (TTM)", dv.get("ttm_dps"), "pershare"), ("Dividend yield", s.get("dividend_yield"), "pct"),  # noqa: E501
                               ("Dividend growth (YoY)", next((x["growth"] for x in reversed(dv.get("by_fy", [])) if not x.get("partial")), None), "pct"), ("Years of dividend payments", dv.get("years_paying"), "int"),  # noqa: E501
                               ("Payout ratio", r("payout") or an("payout"), "pct"), ("Buyback yield / dilution", an("buyback_yield"), "pct"), ("Earnings yield", r("earnings_yield"), "pct"),  # noqa: E501
                               ("FCF yield", r("fcf_yield"), "pct")],
        "Scores": [("Altman Z-score", z, "ratio"), ("Piotroski F-score", f, "score")],
    }
    return {k: [{"label": lbl, "value": val, "kind": kind} for lbl, val, kind in rows] for k, rows in groups.items()}


def pros_cons(s: dict) -> tuple[list[str], list[str]]:
    """Plain-language observations from the ratios (rules v0). Thresholds are conventional retail screens."""
    pros: list[str] = []
    cons: list[str] = []
    g = s.get("net_income_ttm_growth") if s.get("net_income_ttm_growth") is not None else s.get("profit_cagr_1y")
    if s.get("eps_cagr_3y") is not None:
        (pros if s["eps_cagr_3y"] >= 15 else cons).append(f"EPS {'grew' if s['eps_cagr_3y'] >= 0 else 'fell'} at {abs(s['eps_cagr_3y']):.0f} % a year over three years"  # noqa: E501
                                                          + (" · strong compounding" if s["eps_cagr_3y"] >= 15 else " · slow"))
    if s.get("revenue_cagr_3y") is not None and s["revenue_cagr_3y"] < 8:
        cons.append(f"Revenue growth is slow: {s['revenue_cagr_3y']:.0f} % a year over three years")
    elif s.get("revenue_cagr_3y") is not None and s["revenue_cagr_3y"] >= 15:
        pros.append(f"Revenue grew {s['revenue_cagr_3y']:.0f} % a year over three years")
    if s.get("roe") is not None:
        (pros if s["roe"] >= 18 else cons).append(f"Return on equity of {s['roe']:.0f} %" + (" · high" if s["roe"] >= 18 else " · below the 18 % bar" if s["roe"] >= 10 else " · low"))  # noqa: E501
    if s.get("roce") is not None and s["roce"] >= 20:
        pros.append(f"ROCE of {s['roce']:.0f} % · capital is used well")
    if s.get("debt_equity") is not None:
        if s["debt_equity"] <= 0.3:
            pros.append(f"Almost debt free · debt to equity {s['debt_equity']:.2f}")
        elif s["debt_equity"] >= 1.5:
            cons.append(f"High leverage · debt to equity {s['debt_equity']:.2f}")
    if s.get("interest_coverage") is not None and s["interest_coverage"] < 2:
        cons.append(f"Interest coverage is thin at {s['interest_coverage']:.1f}×")
    if s.get("pb") is not None and s["pb"] >= 6:
        cons.append(f"Stock trades at {s['pb']:.1f} times book value")
    if s.get("pe") is not None and s.get("eps_cagr_3y") is not None and s["eps_cagr_3y"] > 0 and s["pe"] / s["eps_cagr_3y"] <= 1.2:
        pros.append(f"P/E of {s['pe']:.0f} against {s['eps_cagr_3y']:.0f} % EPS growth · PEG near or below 1")
    if s.get("fcf_ttm_cr") is not None and s["fcf_ttm_cr"] < 0:
        cons.append("Free cash flow is negative over the last year")
    elif s.get("fcf_ttm_cr") is not None and s.get("net_income_ttm_cr") and s["fcf_ttm_cr"] >= 0.8 * s["net_income_ttm_cr"]:
        pros.append("Profits convert into free cash flow")
    if g is not None and g < 0:
        cons.append(f"Profit fell {abs(g):.0f} % in the latest year")
    if s.get("dividend_yield") is not None and s["dividend_yield"] >= 2:
        pros.append(f"Dividend yield of {s['dividend_yield']:.1f} %")
    return pros[:6], cons[:6]
