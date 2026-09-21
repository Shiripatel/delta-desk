"""Company fundamentals: financial statements, ratios and a valuation snapshot for NSE-listed companies.

Source: Yahoo Finance's public fundamentals time series
(https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/<SYMBOL>.NS?type=...),
which returns annual and quarterly statement lines (as filed, in rupees) and trailing valuation ratios. No
key, no crumb, about a second per company; results are cached on disk under data/fundamentals/cache for
twelve hours. Indices, FX and commodities have no statements and return None.

Everything is composed into one read model the Analysis page renders Koyfin-style: periods as columns,
income statement, balance sheet, cash flow, ratios, growth, TTM, plus the summary the council's
fundamental agents read (P/E, P/B, ROE, debt to equity, revenue and EPS growth).
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

CACHE_DIR = Path("data") / "fundamentals" / "cache"
CRORE = 1e7
BASE = "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{sym}?type={types}&period1={p1}&period2={p2}"

# yahoo line -> (label, statement, kind)  kind: money (₹ crore) | pershare | ratio
LINES: dict[str, tuple[str, str, str]] = {
    "TotalRevenue": ("Revenue", "income", "money"), "CostOfRevenue": ("Cost of revenue", "income", "money"),
    "GrossProfit": ("Gross profit", "income", "money"), "OperatingIncome": ("Operating income", "income", "money"),
    "EBITDA": ("EBITDA", "income", "money"), "InterestExpense": ("Interest expense", "income", "money"),
    "PretaxIncome": ("Pre-tax income", "income", "money"), "TaxProvision": ("Tax", "income", "money"),
    "NetIncome": ("Net income", "income", "money"), "DilutedEPS": ("Diluted EPS (₹)", "income", "pershare"),
    "TotalAssets": ("Total assets", "balance", "money"), "CurrentAssets": ("Current assets", "balance", "money"),
    "CashAndCashEquivalents": ("Cash and equivalents", "balance", "money"), "TotalDebt": ("Total debt", "balance", "money"),
    "NetDebt": ("Net debt", "balance", "money"), "CurrentLiabilities": ("Current liabilities", "balance", "money"),
    "TotalLiabilitiesNetMinorityInterest": ("Total liabilities", "balance", "money"), "StockholdersEquity": ("Shareholders' equity", "balance", "money"),  # noqa: E501
    "OperatingCashFlow": ("Operating cash flow", "cash", "money"), "CapitalExpenditure": ("Capital expenditure", "cash", "money"),
    "FreeCashFlow": ("Free cash flow", "cash", "money"), "InvestingCashFlow": ("Investing cash flow", "cash", "money"),
    "FinancingCashFlow": ("Financing cash flow", "cash", "money"), "CashDividendsPaid": ("Dividends paid", "cash", "money"),
}
TRAILING = ["PeRatio", "ForwardPeRatio", "PbRatio", "PsRatio", "PegRatio", "MarketCap", "EnterpriseValue", "EnterprisesValueEBITDARatio", "EnterprisesValueRevenueRatio"]  # noqa: E501
RATIOS: list[tuple[str, str]] = [("gross_margin", "Gross margin %"), ("operating_margin", "Operating margin %"), ("ebitda_margin", "EBITDA margin %"),  # noqa: E501
                                 ("net_margin", "Net margin %"), ("roe", "Return on equity %"), ("roa", "Return on assets %"),
                                 ("debt_equity", "Debt to equity"), ("current_ratio", "Current ratio"), ("fcf_margin", "FCF margin %"),
                                 ("revenue_growth", "Revenue growth %"), ("net_income_growth", "Net income growth %"), ("eps_growth", "EPS growth %")]  # noqa: E501
FLOW = {"TotalRevenue", "CostOfRevenue", "GrossProfit", "OperatingIncome", "EBITDA", "InterestExpense", "PretaxIncome", "TaxProvision", "NetIncome",  # noqa: E501
        "DilutedEPS", "OperatingCashFlow", "CapitalExpenditure", "FreeCashFlow", "InvestingCashFlow", "FinancingCashFlow", "CashDividendsPaid"}  # noqa: E501


def _div(a: float | None, b: float | None) -> float | None:
    return round(a / b, 4) if a is not None and b not in (None, 0) else None


def _pct(a: float | None, b: float | None) -> float | None:
    v = _div(a, b)
    return round(v * 100, 1) if v is not None else None


def _growth(cur: float | None, prev: float | None) -> float | None:
    if cur is None or prev is None or prev == 0:
        return None
    return round((cur - prev) / abs(prev) * 100, 1)


def _cagr(a: float | None, b: float | None, years: int) -> float | None:
    if not a or not b or a <= 0 or b <= 0 or years <= 0:
        return None
    return round(((b / a) ** (1 / years) - 1) * 100, 1)


class YahooFundamentals:
    name = "yahoo fundamentals"

    def __init__(self, ttl: float = 12 * 3600, timeout: float = 12.0, cache_dir: Path = CACHE_DIR) -> None:
        self.ttl, self.timeout, self.cache_dir = ttl, timeout, cache_dir
        self._mem: dict[str, tuple[float, dict | None]] = {}
        self._lock = threading.Lock()

    # ---- fetch ----------------------------------------------------------------------------------
    @staticmethod
    def yahoo_symbol(symbol: str) -> str | None:
        from deltadesk.markets import universe
        s = symbol.upper()
        if s in universe.INDICES or s in universe.GLOBAL_BY_KEY or s in universe.FX_WORLD_BY_KEY or s.startswith("FUT:") or s in {f[0] for f in universe.FX}:  # noqa: E501
            return None
        return f"{s}.NS"

    def _fetch(self, ysym: str) -> dict:
        now = int(time.time())
        types = ",".join([f"annual{k}" for k in LINES] + [f"quarterly{k}" for k in LINES] + [f"trailing{k}" for k in TRAILING])
        url = BASE.format(sym=quote(ysym), types=types, p1=now - 7 * 365 * 86400, p2=now)
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (DeltaDesk)"})
        with urlopen(req, timeout=self.timeout) as r:
            raw = json.loads(r.read().decode("utf-8"))
        out: dict[str, dict[str, dict[str, float]]] = {"annual": {}, "quarterly": {}, "trailing": {}}
        for res in raw.get("timeseries", {}).get("result", []):
            t = res["meta"]["type"][0]
            for freq in ("annual", "quarterly", "trailing"):
                if t.startswith(freq):
                    line = t[len(freq):]
                    for row in res.get(t) or []:
                        if row and row.get("reportedValue", {}).get("raw") is not None:
                            out[freq].setdefault(line, {})[row["asOfDate"]] = float(row["reportedValue"]["raw"])
                    break
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
                if now - d.get("fetched_at", 0) < self.ttl:
                    with self._lock:
                        self._mem[key] = (d["fetched_at"], d)
                    return d
            except (json.JSONDecodeError, KeyError):
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

    # ---- compose ---------------------------------------------------------------------------------
    def analysis(self, symbol: str, refresh: bool = False) -> dict | None:
        d = self.raw(symbol, refresh)
        if d is None:
            return None
        if not d.get("series"):
            return {"symbol": symbol.upper(), "error": d.get("error", "no data"), "source": self.name}
        return compose(d)

    def council_summary(self, symbol: str) -> tuple[dict | None, str]:
        """What the council's fundamental agents read; falls back to nothing when the fetch fails."""
        a = self.analysis(symbol)
        if not a or a.get("error"):
            return None, "no data (" + (a.get("error", "not a listed company") if a else "not a listed company") + ")"
        return a["council"], f"{self.name} · FY{a['periods']['annual'][-1][:4]}" if a["periods"]["annual"] else self.name


def compose(d: dict) -> dict:
    series = d["series"]
    out: dict = {"symbol": d["symbol"], "yahoo": d["yahoo"], "source": "yahoo fundamentals", "fetched_at": d["fetched_at"], "currency": "INR",  # noqa: E501
                 "unit": "₹ crore", "lines": {k: {"label": v[0], "statement": v[1], "kind": v[2]} for k, v in LINES.items()},
                 "ratio_labels": dict(RATIOS), "periods": {}, "statements": {}, "ratios": {}, "ttm": {}}
    for freq in ("annual", "quarterly"):
        s = series.get(freq, {})
        dates = sorted({dt for line in s.values() for dt in line})
        dates = dates[-6:] if freq == "annual" else dates[-8:]
        out["periods"][freq] = dates
        st: dict[str, dict[str, float | None]] = {}
        for line, (_, _, kind) in LINES.items():
            vals = s.get(line, {})
            st[line] = {dt: (round(vals[dt] / CRORE, 1) if kind == "money" else round(vals[dt], 2)) if dt in vals else None for dt in dates}
        out["statements"][freq] = st
        r: dict[str, dict[str, float | None]] = {k: {} for k, _ in RATIOS}
        for i, dt in enumerate(dates):
            g = lambda line: st[line].get(dt)  # noqa: E731
            r["gross_margin"][dt] = _pct(g("GrossProfit"), g("TotalRevenue"))
            r["operating_margin"][dt] = _pct(g("OperatingIncome"), g("TotalRevenue"))
            r["ebitda_margin"][dt] = _pct(g("EBITDA"), g("TotalRevenue"))
            r["net_margin"][dt] = _pct(g("NetIncome"), g("TotalRevenue"))
            r["roe"][dt] = _pct(g("NetIncome") * (4 if freq == "quarterly" else 1) if g("NetIncome") is not None else None, g("StockholdersEquity"))  # noqa: E501
            r["roa"][dt] = _pct(g("NetIncome") * (4 if freq == "quarterly" else 1) if g("NetIncome") is not None else None, g("TotalAssets"))  # noqa: E501
            r["debt_equity"][dt] = _div(g("TotalDebt"), g("StockholdersEquity"))
            r["current_ratio"][dt] = _div(g("CurrentAssets"), g("CurrentLiabilities"))
            r["fcf_margin"][dt] = _pct(g("FreeCashFlow"), g("TotalRevenue"))
            back = 1 if freq == "annual" else 4
            prev = dates[i - back] if i - back >= 0 else None
            r["revenue_growth"][dt] = _growth(g("TotalRevenue"), st["TotalRevenue"].get(prev)) if prev else None
            r["net_income_growth"][dt] = _growth(g("NetIncome"), st["NetIncome"].get(prev)) if prev else None
            r["eps_growth"][dt] = _growth(g("DilutedEPS"), st["DilutedEPS"].get(prev)) if prev else None
        out["ratios"][freq] = r
    q = out["statements"].get("quarterly", {})
    qd = out["periods"].get("quarterly", [])
    if len(qd) >= 4:
        for line in FLOW:
            vals = [q[line].get(dt) for dt in qd[-4:]]
            out["ttm"][line] = round(sum(vals), 1) if all(v is not None for v in vals) else None
    tr = {k: (sorted(v.items())[-1][1] if v else None) for k, v in series.get("trailing", {}).items()}
    a, ad = out["statements"].get("annual", {}), out["periods"].get("annual", [])
    last = ad[-1] if ad else None
    first = ad[-4] if len(ad) >= 4 else (ad[0] if ad else None)
    years = 3 if len(ad) >= 4 else max(1, len(ad) - 1)
    rev_ttm = out["ttm"].get("TotalRevenue") or (a["TotalRevenue"].get(last) if last else None)
    ni_ttm = out["ttm"].get("NetIncome") or (a["NetIncome"].get(last) if last else None)
    eq = a["StockholdersEquity"].get(last) if last else None
    debt = a["TotalDebt"].get(last) if last else None
    out["snapshot"] = {
        "pe": _r(tr.get("PeRatio")), "forward_pe": _r(tr.get("ForwardPeRatio")), "pb": _r(tr.get("PbRatio")), "ps": _r(tr.get("PsRatio")), "peg": _r(tr.get("PegRatio")),  # noqa: E501
        "market_cap_cr": round(tr["MarketCap"] / CRORE) if tr.get("MarketCap") else None, "ev_cr": round(tr["EnterpriseValue"] / CRORE) if tr.get("EnterpriseValue") else None,  # noqa: E501
        "ev_ebitda": _r(tr.get("EnterprisesValueEBITDARatio")), "ev_revenue": _r(tr.get("EnterprisesValueRevenueRatio")),
        "revenue_ttm_cr": rev_ttm, "net_income_ttm_cr": ni_ttm, "eps_ttm": out["ttm"].get("DilutedEPS") or (a["DilutedEPS"].get(last) if last else None),  # noqa: E501
        "net_margin": _pct(ni_ttm, rev_ttm), "roe": _pct(ni_ttm, eq), "debt_equity": _div(debt, eq), "fcf_ttm_cr": out["ttm"].get("FreeCashFlow") or (a["FreeCashFlow"].get(last) if last else None),  # noqa: E501
        "revenue_cagr_3y": _cagr(a["TotalRevenue"].get(first), a["TotalRevenue"].get(last), years) if first and last else None,
        "eps_cagr_3y": _cagr(a["DilutedEPS"].get(first), a["DilutedEPS"].get(last), years) if first and last else None,
        "fy": last,
    }
    s = out["snapshot"]
    out["council"] = {"pe": s["pe"], "pb": s["pb"], "roe": s["roe"], "debt_equity": s["debt_equity"], "revenue_growth": s["revenue_cagr_3y"],  # noqa: E501
                      "eps_growth": s["eps_cagr_3y"], "dividend_yield": None, "promoter_holding": None, "fii_holding": None, "source": "yahoo fundamentals"}  # noqa: E501
    return out


def _r(v: float | None) -> float | None:
    return round(v, 2) if v is not None else None
