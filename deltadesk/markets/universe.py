"""Index universe: which symbols belong to which index, with sector and an approximate weight.

Seed lists below are a snapshot and drift as NSE rebalances. `refresh_from_nse()` downloads the
official constituent CSVs from niftyindices.com into data/constituents/ and overrides the seed
symbols and sectors (weights stay approximate: NSE publishes them only in the monthly factsheet PDF).
Weights for indices other than NIFTY 50 are set equal until a factsheet loader exists.
"""
from __future__ import annotations

import csv
import io
import json
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path("data") / "constituents"

NSE_CSV = {
    "NIFTY50": "https://niftyindices.com/IndexConstituent/ind_nifty50list.csv",
    "NIFTYNEXT50": "https://niftyindices.com/IndexConstituent/ind_niftynext50list.csv",
    "BANKNIFTY": "https://niftyindices.com/IndexConstituent/ind_niftybanklist.csv",
    "FINNIFTY": "https://niftyindices.com/IndexConstituent/ind_niftyfinancelist.csv",
    "MIDCPNIFTY": "https://niftyindices.com/IndexConstituent/ind_niftymidcapselect_list.csv",
}


@dataclass
class Constituent:
    symbol: str
    name: str
    sector: str
    weight: float = 0.0      # percent of index, approximate


@dataclass
class Index:
    code: str
    name: str
    exchange: str
    feed_key: str            # what the broker feed calls it (Upstox style shown)
    lot_size: int | None
    fno: bool
    constituents: list[Constituent] = field(default_factory=list)


# ---- seed data (symbol, name, sector, approx weight %) ------------------------------------
_N50 = [
    ("HDFCBANK", "HDFC Bank", "Financials", 12.5), ("ICICIBANK", "ICICI Bank", "Financials", 8.8),
    ("RELIANCE", "Reliance Industries", "Energy", 8.2), ("INFY", "Infosys", "IT", 5.4),
    ("BHARTIARTL", "Bharti Airtel", "Telecom", 4.6), ("LT", "Larsen & Toubro", "Industrials", 3.8),
    ("ITC", "ITC", "FMCG", 3.6), ("TCS", "Tata Consultancy Services", "IT", 3.6),
    ("AXISBANK", "Axis Bank", "Financials", 3.1), ("KOTAKBANK", "Kotak Mahindra Bank", "Financials", 3.0),
    ("SBIN", "State Bank of India", "Financials", 2.9), ("M&M", "Mahindra & Mahindra", "Auto", 2.6),
    ("BAJFINANCE", "Bajaj Finance", "Financials", 2.4), ("HINDUNILVR", "Hindustan Unilever", "FMCG", 2.0),
    ("SUNPHARMA", "Sun Pharmaceutical", "Pharma", 1.8), ("MARUTI", "Maruti Suzuki", "Auto", 1.7),
    ("NTPC", "NTPC", "Utilities", 1.6), ("HCLTECH", "HCL Technologies", "IT", 1.6),
    ("ULTRACEMCO", "UltraTech Cement", "Materials", 1.5), ("TATAMOTORS", "Tata Motors", "Auto", 1.4),
    ("TITAN", "Titan Company", "Consumer", 1.4), ("POWERGRID", "Power Grid", "Utilities", 1.3),
    ("BAJAJFINSV", "Bajaj Finserv", "Financials", 1.2), ("TATASTEEL", "Tata Steel", "Materials", 1.2),
    ("ADANIPORTS", "Adani Ports", "Industrials", 1.1), ("ASIANPAINT", "Asian Paints", "Consumer", 1.1),
    ("ONGC", "ONGC", "Energy", 1.0), ("BEL", "Bharat Electronics", "Industrials", 1.0),
    ("JSWSTEEL", "JSW Steel", "Materials", 1.0), ("COALINDIA", "Coal India", "Energy", 0.9),
    ("NESTLEIND", "Nestle India", "FMCG", 0.9), ("GRASIM", "Grasim Industries", "Materials", 0.9),
    ("TRENT", "Trent", "Consumer", 0.9), ("HINDALCO", "Hindalco", "Materials", 0.8),
    ("ADANIENT", "Adani Enterprises", "Industrials", 0.8), ("TECHM", "Tech Mahindra", "IT", 0.8),
    ("SBILIFE", "SBI Life Insurance", "Financials", 0.8), ("HDFCLIFE", "HDFC Life Insurance", "Financials", 0.7),
    ("BAJAJ-AUTO", "Bajaj Auto", "Auto", 0.7), ("EICHERMOT", "Eicher Motors", "Auto", 0.7),
    ("CIPLA", "Cipla", "Pharma", 0.7), ("DRREDDY", "Dr Reddy's", "Pharma", 0.7),
    ("WIPRO", "Wipro", "IT", 0.7), ("SHRIRAMFIN", "Shriram Finance", "Financials", 0.7),
    ("APOLLOHOSP", "Apollo Hospitals", "Healthcare", 0.7), ("TATACONSUM", "Tata Consumer", "FMCG", 0.6),
    ("JIOFIN", "Jio Financial", "Financials", 0.6), ("HEROMOTOCO", "Hero MotoCorp", "Auto", 0.5),
    ("INDUSINDBK", "IndusInd Bank", "Financials", 0.5), ("BPCL", "BPCL", "Energy", 0.5),
]
_BANK = [
    ("HDFCBANK", "HDFC Bank", "Financials", 27.0), ("ICICIBANK", "ICICI Bank", "Financials", 23.5),
    ("SBIN", "State Bank of India", "Financials", 9.5), ("KOTAKBANK", "Kotak Mahindra Bank", "Financials", 9.0),
    ("AXISBANK", "Axis Bank", "Financials", 8.5), ("INDUSINDBK", "IndusInd Bank", "Financials", 3.5),
    ("BANKBARODA", "Bank of Baroda", "Financials", 3.0), ("PNB", "Punjab National Bank", "Financials", 2.5),
    ("FEDERALBNK", "Federal Bank", "Financials", 2.5), ("AUBANK", "AU Small Finance Bank", "Financials", 2.5),
    ("IDFCFIRSTB", "IDFC First Bank", "Financials", 2.0), ("CANBK", "Canara Bank", "Financials", 2.0),
]
_FIN = [
    ("HDFCBANK", "HDFC Bank", "Financials", 30.0), ("ICICIBANK", "ICICI Bank", "Financials", 20.0),
    ("SBIN", "State Bank of India", "Financials", 7.5), ("AXISBANK", "Axis Bank", "Financials", 7.0),
    ("KOTAKBANK", "Kotak Mahindra Bank", "Financials", 6.5), ("BAJFINANCE", "Bajaj Finance", "Financials", 6.0),
    ("BAJAJFINSV", "Bajaj Finserv", "Financials", 3.0), ("SHRIRAMFIN", "Shriram Finance", "Financials", 2.5),
    ("SBILIFE", "SBI Life Insurance", "Financials", 2.5), ("HDFCLIFE", "HDFC Life Insurance", "Financials", 2.5),
    ("JIOFIN", "Jio Financial", "Financials", 2.0), ("CHOLAFIN", "Cholamandalam Investment", "Financials", 2.0),
    ("ICICIGI", "ICICI Lombard", "Financials", 1.5), ("HDFCAMC", "HDFC AMC", "Financials", 1.5),
    ("MUTHOOTFIN", "Muthoot Finance", "Financials", 1.0), ("SBICARD", "SBI Cards", "Financials", 1.0),
    ("PFC", "Power Finance Corp", "Financials", 1.0), ("RECLTD", "REC", "Financials", 1.0),
    ("ICICIPRULI", "ICICI Prudential Life", "Financials", 1.0), ("LICHSGFIN", "LIC Housing Finance", "Financials", 0.5),
]
_MIDSEL = [
    ("PERSISTENT", "Persistent Systems", "IT", 4.0), ("MAXHEALTH", "Max Healthcare", "Healthcare", 4.0),
    ("DIXON", "Dixon Technologies", "Consumer", 4.0), ("INDHOTEL", "Indian Hotels", "Consumer", 4.0),
    ("LUPIN", "Lupin", "Pharma", 4.0), ("AUROPHARMA", "Aurobindo Pharma", "Pharma", 4.0),
    ("FEDERALBNK", "Federal Bank", "Financials", 4.0), ("IDFCFIRSTB", "IDFC First Bank", "Financials", 4.0),
    ("CUMMINSIND", "Cummins India", "Industrials", 4.0), ("VOLTAS", "Voltas", "Consumer", 4.0),
    ("ASHOKLEY", "Ashok Leyland", "Auto", 4.0), ("MPHASIS", "Mphasis", "IT", 4.0),
    ("COFORGE", "Coforge", "IT", 4.0), ("HDFCAMC", "HDFC AMC", "Financials", 4.0),
    ("GODREJPROP", "Godrej Properties", "Realty", 4.0), ("ASTRAL", "Astral", "Materials", 4.0),
    ("SRF", "SRF", "Materials", 4.0), ("UPL", "UPL", "Materials", 4.0),
    ("CONCOR", "Container Corp", "Industrials", 4.0), ("PIIND", "PI Industries", "Materials", 4.0),
    ("BHARATFORG", "Bharat Forge", "Industrials", 4.0), ("POLYCAB", "Polycab India", "Industrials", 4.0),
    ("OBEROIRLTY", "Oberoi Realty", "Realty", 4.0), ("JUBLFOOD", "Jubilant FoodWorks", "Consumer", 4.0),
    ("SUNDARMFIN", "Sundaram Finance", "Financials", 4.0),
]
_NEXT50 = [
    ("HAL", "Hindustan Aeronautics", "Industrials", 2.0), ("DLF", "DLF", "Realty", 2.0),
    ("VBL", "Varun Beverages", "FMCG", 2.0), ("DIVISLAB", "Divi's Laboratories", "Pharma", 2.0),
    ("PIDILITIND", "Pidilite Industries", "Materials", 2.0), ("SIEMENS", "Siemens", "Industrials", 2.0),
    ("ABB", "ABB India", "Industrials", 2.0), ("TVSMOTOR", "TVS Motor", "Auto", 2.0),
    ("CHOLAFIN", "Cholamandalam Investment", "Financials", 2.0), ("BAJAJHLDNG", "Bajaj Holdings", "Financials", 2.0),
    ("GODREJCP", "Godrej Consumer", "FMCG", 2.0), ("AMBUJACEM", "Ambuja Cements", "Materials", 2.0),
    ("SHREECEM", "Shree Cement", "Materials", 2.0), ("VEDL", "Vedanta", "Materials", 2.0),
    ("ZYDUSLIFE", "Zydus Lifesciences", "Pharma", 2.0), ("TORNTPHARM", "Torrent Pharma", "Pharma", 2.0),
    ("ICICIGI", "ICICI Lombard", "Financials", 2.0), ("ICICIPRULI", "ICICI Prudential Life", "Financials", 2.0),
    ("LICI", "LIC of India", "Financials", 2.0), ("BANKBARODA", "Bank of Baroda", "Financials", 2.0),
    ("PNB", "Punjab National Bank", "Financials", 2.0), ("CANBK", "Canara Bank", "Financials", 2.0),
    ("IOC", "Indian Oil", "Energy", 2.0), ("GAIL", "GAIL", "Energy", 2.0),
    ("ADANIGREEN", "Adani Green", "Utilities", 2.0), ("ADANIPOWER", "Adani Power", "Utilities", 2.0),
    ("TATAPOWER", "Tata Power", "Utilities", 2.0), ("JSWENERGY", "JSW Energy", "Utilities", 2.0),
    ("ZOMATO", "Eternal (Zomato)", "Consumer", 2.0), ("NAUKRI", "Info Edge", "IT", 2.0),
    ("DMART", "Avenue Supermarts", "Consumer", 2.0), ("HAVELLS", "Havells", "Consumer", 2.0),
    ("BOSCHLTD", "Bosch", "Auto", 2.0), ("MOTHERSON", "Samvardhana Motherson", "Auto", 2.0),
    ("IRFC", "IRFC", "Financials", 2.0), ("PFC", "Power Finance Corp", "Financials", 2.0),
    ("RECLTD", "REC", "Financials", 2.0), ("INDIGO", "InterGlobe Aviation", "Industrials", 2.0),
    ("BHEL", "BHEL", "Industrials", 2.0), ("CGPOWER", "CG Power", "Industrials", 2.0),
    ("ATGL", "Adani Total Gas", "Energy", 2.0), ("BRITANNIA", "Britannia", "FMCG", 2.0),
    ("DABUR", "Dabur", "FMCG", 2.0), ("COLPAL", "Colgate-Palmolive", "FMCG", 2.0),
    ("MARICO", "Marico", "FMCG", 2.0), ("UNITDSPR", "United Spirits", "FMCG", 2.0),
    ("LTIM", "LTIMindtree", "IT", 2.0), ("HINDPETRO", "HPCL", "Energy", 2.0),
    ("JINDALSTEL", "Jindal Steel", "Materials", 2.0), ("SBICARD", "SBI Cards", "Financials", 2.0),
]
_SENSEX = [c for c in _N50 if c[0] in {
    "HDFCBANK", "ICICIBANK", "RELIANCE", "INFY", "BHARTIARTL", "LT", "ITC", "TCS", "AXISBANK", "KOTAKBANK",
    "SBIN", "M&M", "BAJFINANCE", "HINDUNILVR", "SUNPHARMA", "MARUTI", "NTPC", "HCLTECH", "ULTRACEMCO",
    "TATAMOTORS", "TITAN", "POWERGRID", "BAJAJFINSV", "TATASTEEL", "ADANIPORTS", "ASIANPAINT", "NESTLEIND",
    "TECHM", "INDUSINDBK", "ZOMATO"}]


def _mk(rows) -> list[Constituent]:
    return [Constituent(*r) for r in rows]


INDICES: dict[str, Index] = {
    "NIFTY50": Index("NIFTY50", "NIFTY 50", "NSE", "NSE_INDEX|Nifty 50", 75, True, _mk(_N50)),
    "BANKNIFTY": Index("BANKNIFTY", "NIFTY BANK", "NSE", "NSE_INDEX|Nifty Bank", 35, True, _mk(_BANK)),
    "FINNIFTY": Index("FINNIFTY", "NIFTY FIN SERVICE", "NSE", "NSE_INDEX|Nifty Fin Service", 65, True, _mk(_FIN)),
    "MIDCPNIFTY": Index("MIDCPNIFTY", "NIFTY MIDCAP SELECT", "NSE", "NSE_INDEX|NIFTY MID SELECT", 140, True, _mk(_MIDSEL)),
    "NIFTYNEXT50": Index("NIFTYNEXT50", "NIFTY NEXT 50", "NSE", "NSE_INDEX|Nifty Next 50", 25, True, _mk(_NEXT50)),
    "SENSEX": Index("SENSEX", "S&P BSE SENSEX", "BSE", "BSE_INDEX|SENSEX", 20, True, _mk(_SENSEX)),
    "INDIAVIX": Index("INDIAVIX", "INDIA VIX", "NSE", "NSE_INDEX|India VIX", None, False, []),
}

# reference levels used only by the synthetic quote provider
SEED_LEVELS = {"NIFTY50": 25_300.0, "BANKNIFTY": 56_200.0, "FINNIFTY": 26_900.0, "MIDCPNIFTY": 13_100.0,
               "NIFTYNEXT50": 68_400.0, "SENSEX": 82_600.0, "INDIAVIX": 13.0}


# ---- other asset classes (symbol, name, tracks / detail, seed price) -------------------------
ETFS = [
    ("NIFTYBEES", "Nippon India Nifty 50 BeES", "NIFTY50", 281.0), ("BANKBEES", "Nippon India Nifty Bank BeES", "BANKNIFTY", 562.0),
    ("JUNIORBEES", "Nippon India Nifty Next 50 BeES", "NIFTYNEXT50", 684.0), ("ITBEES", "Nippon India Nifty IT BeES", "NIFTY50", 41.0),
    ("MIDSELIETF", "ICICI Pru Nifty Midcap Select ETF", "MIDCPNIFTY", 131.0), ("SETFNIF50", "SBI Nifty 50 ETF", "NIFTY50", 262.0),
    ("GOLDBEES", "Nippon India Gold BeES", "GOLD", 78.0), ("SILVERBEES", "Nippon India Silver BeES", "SILVER", 95.0),
    ("LIQUIDBEES", "Nippon India Liquid BeES", "CASH", 1000.0), ("CPSEETF", "Nippon India CPSE ETF", "NIFTY50", 92.0),
    ("MON100", "Motilal Oswal Nasdaq 100 ETF", "GLOBAL", 190.0), ("MAFANG", "Mirae FANG+ ETF", "GLOBAL", 120.0),
]
FX = [("USDINR", "US Dollar / Indian Rupee", "NSE CDS · lot 1,000 USD", 88.10),
      ("EURINR", "Euro / Indian Rupee", "NSE CDS · lot 1,000 EUR", 96.40),
      ("GBPINR", "British Pound / Indian Rupee", "NSE CDS · lot 1,000 GBP", 112.30),
      ("JPYINR", "Japanese Yen / Indian Rupee", "NSE CDS · lot 100,000 JPY", 0.585)]
# key, name, yahoo symbol, decimals, unit, group, seed (for the synthetic provider)
GLOBAL = [
    ("USDINR", "USD / INR", "USDINR=X", 2, "₹ per $", "currency", 88.10),
    ("DXY", "US dollar index", "DX-Y.NYB", 2, "index", "currency", 100.3),
    ("GOLD", "Gold", "GC=F", 1, "$ / oz (COMEX)", "commodity", 4400.0),
    ("SILVER", "Silver", "SI=F", 2, "$ / oz (COMEX)", "commodity", 66.8),
    ("BRENT", "Brent crude", "BZ=F", 2, "$ / bbl", "commodity", 103.7),
    ("NATGAS", "Natural gas", "NG=F", 3, "$ / MMBtu", "commodity", 2.87),
    ("BTC", "Bitcoin", "BTC-USD", 0, "$", "crypto", 77500.0),
    ("ETH", "Ethereum", "ETH-USD", 0, "$", "crypto", 2480.0),
    ("US10Y", "US 10-year yield", "^TNX", 3, "%", "rates", 4.95),
    ("SPX", "S&P 500", "^GSPC", 0, "index", "global", 7638.0),
    ("NDX", "Nasdaq composite", "^IXIC", 0, "index", "global", 26418.0),
    ("DJI", "Dow Jones", "^DJI", 0, "index", "global", 51778.0),
    ("N225", "Nikkei 225", "^N225", 0, "index", "global", 65172.0),
    ("HSI", "Hang Seng", "^HSI", 0, "index", "global", 24805.0),
]
GLOBAL_BY_KEY = {g[0]: g for g in GLOBAL}
FUTURES_UNDERLYINGS = ["NIFTY50", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]


def last_weekday_of_month(year: int, month: int, weekday: int = 1):
    import calendar as _cal
    from datetime import date as _date
    last = _cal.monthrange(year, month)[1]
    d = _date(year, month, last)
    while d.weekday() != weekday:
        d = d.replace(day=d.day - 1)
    return d


def futures_contracts(today):
    """Near and next month index futures. NSE index monthly expiry is the last Tuesday (since Sept 2025)."""
    out = []
    y, m = today.year, today.month
    exps = []
    for _ in range(3):
        e = last_weekday_of_month(y, m, 1)
        if e >= today:
            exps.append(e)
        m += 1
        if m == 13:
            y, m = y + 1, 1
    for code in FUTURES_UNDERLYINGS:
        ix = INDICES[code]
        for i, e in enumerate(exps[:2]):
            und = "NIFTY" if code == "NIFTY50" else code
            out.append({"key": f"FUT:{code}:{e.isoformat()}", "symbol": f"{und} {e:%d%b%y} FUT".upper(), "underlying": code,
                        "expiry": e.isoformat(), "series": "near" if i == 0 else "next", "lot_size": ix.lot_size})
    return out


def all_symbols() -> dict[str, Constituent]:
    out: dict[str, Constituent] = {}
    for ix in INDICES.values():
        for c in ix.constituents:
            out.setdefault(c.symbol, c)
    return out


def refresh_from_nse(timeout: float = 15.0) -> dict[str, int]:
    """Download NSE's official constituent lists; returns {index: rows}. Safe to call offline (returns {})."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    done: dict[str, int] = {}
    for code, url in NSE_CSV.items():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                text = r.read().decode("utf-8-sig")
        except Exception:
            continue
        (DATA_DIR / f"{code}.csv").write_text(text, encoding="utf-8")
        done[code] = _apply_csv(code, text)
    return done


def load_cached() -> dict[str, int]:
    done: dict[str, int] = {}
    if not DATA_DIR.exists():
        return done
    for code in NSE_CSV:
        f = DATA_DIR / f"{code}.csv"
        if f.exists():
            done[code] = _apply_csv(code, f.read_text(encoding="utf-8"))
    return done


def _apply_csv(code: str, text: str) -> int:
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows or "Symbol" not in rows[0]:
        return 0
    ix = INDICES[code]
    old = {c.symbol: c for c in ix.constituents}
    n = len(rows)
    ix.constituents = [
        Constituent(symbol=r["Symbol"].strip(), name=r.get("Company Name", r["Symbol"]).strip(),
                    sector=r.get("Industry", "").strip() or old.get(r["Symbol"].strip(), Constituent("", "", "Other")).sector,
                    weight=old[r["Symbol"].strip()].weight if r["Symbol"].strip() in old else round(100 / n, 2))
        for r in rows
    ]
    return n


def to_json() -> str:
    return json.dumps({k: {"name": v.name, "n": len(v.constituents)} for k, v in INDICES.items()})
