"""Headlines from public RSS feeds, tagged with the stocks they mention and scored for impact.

No API keys. Feeds refresh every `ttl` seconds in the background of a request; offline the page keeps
working with an empty list and a note. Impact is a transparent lexicon rule (v0): positive and negative
cues in the headline decide good / bad / neutral and the cues are returned as the reason, so an LLM
analyser can replace `Analyzer` later without changing the page.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import html
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from email.utils import parsedate_to_datetime
from typing import Protocol

from deltadesk.markets.universe import INDICES, all_symbols

FEEDS = [
    ("Economic Times · Markets", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("Economic Times · Stocks", "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"),
    ("Moneycontrol · Market reports", "https://www.moneycontrol.com/rss/marketreports.xml"),
    ("Moneycontrol · Business", "https://www.moneycontrol.com/rss/business.xml"),
    ("Mint · Markets", "https://www.livemint.com/rss/markets"),
    ("Business Standard · Markets", "https://www.business-standard.com/rss/markets-106.rss"),
]
STOP = set("the a an and of to in on for at by with from as is are be was were it its this that these those over "
           "after before up down into out amid says say said will may can could than more most new top today "
           "stock stocks market markets share shares nifty sensex rs crore per cent percent lakh india indian "
           "week day year live news update updates how why what who your you we our here now vs".split())

# extra ways headlines name the big companies; the full company name and the symbol always count
ALIASES = {
    "RELIANCE": ["reliance industries", "ril", "reliance"], "INFY": ["infosys"], "TCS": ["tcs", "tata consultancy"],
    "HDFCBANK": ["hdfc bank"], "ICICIBANK": ["icici bank"], "SBIN": ["sbi", "state bank"], "ITC": ["itc"],
    "LT": ["larsen", "l&t"], "BHARTIARTL": ["airtel", "bharti"], "MARUTI": ["maruti"], "TATAMOTORS": ["tata motors"],
    "WIPRO": ["wipro"], "HCLTECH": ["hcl tech", "hcltech"], "KOTAKBANK": ["kotak"], "AXISBANK": ["axis bank"],
    "SUNPHARMA": ["sun pharma"], "TITAN": ["titan"], "ADANIENT": ["adani enterprises"], "ADANIPORTS": ["adani ports"],
    "ZOMATO": ["zomato", "eternal"], "BAJFINANCE": ["bajaj finance"], "BAJAJFINSV": ["bajaj finserv"],
    "M&M": ["mahindra"], "TATASTEEL": ["tata steel"], "JSWSTEEL": ["jsw steel"], "ONGC": ["ongc"], "NTPC": ["ntpc"],
    "POWERGRID": ["power grid"], "COALINDIA": ["coal india"], "HINDUNILVR": ["hindustan unilever", "hul"],
    "NESTLEIND": ["nestle"], "ASIANPAINT": ["asian paints"], "ULTRACEMCO": ["ultratech"], "TECHM": ["tech mahindra"],
    "HAL": ["hindustan aeronautics", "hal"], "BEL": ["bharat electronics"], "DLF": ["dlf"], "INDIGO": ["indigo"],
    "VEDL": ["vedanta"], "HINDALCO": ["hindalco"], "CIPLA": ["cipla"], "DRREDDY": ["dr reddy"], "TRENT": ["trent"],
    "JIOFIN": ["jio financial"], "INDUSINDBK": ["indusind"], "BPCL": ["bpcl"], "IOC": ["indian oil", "ioc"],
    "SHRIRAMFIN": ["shriram finance"], "DIVISLAB": ["divi's"], "PNB": ["punjab national bank", "pnb"],
    "BANKBARODA": ["bank of baroda"], "CANBK": ["canara bank"], "LICI": ["lic"], "PAYTM": ["paytm"],
}
TOPICS = {"NIFTY50": ["nifty"], "SENSEX": ["sensex"], "RBI": ["rbi", "reserve bank"], "SEBI": ["sebi"],
          "FII": ["fii", "fpi", "foreign investors"], "IPO": ["ipo"], "CRUDE": ["crude", "oil prices"],
          "GOLD": ["gold"], "USDINR": ["rupee"], "FED": ["fed ", "federal reserve", "powell"]}
POS = ["surge", "surges", "jump", "jumps", "rally", "rallies", "soar", "record high", "profit rises", "profit jumps",
       "upgrade", "upgrades", "buyback", "order win", "bags order", "beats", "outperform", "gain", "gains", "climbs", "strong",
       "dividend", "bonus", "approval", "approves", "wins", "expands", "growth", "higher", "up ", "rises", "positive"]
NEG = ["fall", "falls", "plunge", "plunges", "slump", "slumps", "crash", "loss", "losses", "downgrade", "downgrades",
       "probe", "fraud", "default", "penalty", "misses", "weak", "cuts", "cut ", "lower", "down ", "decline", "declines", "drop", "drops",
       "sell-off", "selloff", "tumbles", "slides", "concern", "warning", "ban", "fine", "layoffs", "negative", "resigns"]


@dataclass
class Headline:
    id: str
    title: str
    link: str
    source: str
    published: str          # ISO 8601 or ""
    ts: float               # epoch for sorting
    description: str = ""
    symbols: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    impact: str = "neutral"     # good | bad | neutral
    confidence: float = 0.0
    reason: str = ""

    def json(self) -> dict:
        return asdict(self)


class Analyzer(Protocol):
    name: str

    def analyse(self, h: Headline) -> tuple[str, float, str]: ...


class LexiconAnalyzer:
    """v0: counts positive and negative cues in the headline. The reason lists the cues it saw."""
    name = "lexicon v0"

    def analyse(self, h: Headline) -> tuple[str, float, str]:
        t = " " + h.title.lower() + " "
        has = lambda w: re.search(r"(?<![a-z])" + re.escape(w.strip()) + r"(?![a-z])", t) is not None  # noqa: E731
        pos = [w for w in POS if has(w)]
        neg = [w for w in NEG if has(w)]
        score = len(pos) - len(neg)
        if score >= 1:
            return "good", min(0.9, 0.45 + 0.15 * score), "positive cues: " + ", ".join(w.strip() for w in pos)
        if score <= -1:
            return "bad", min(0.9, 0.45 + 0.15 * -score), "negative cues: " + ", ".join(w.strip() for w in neg)
        if pos and neg:
            return "neutral", 0.35, "mixed cues: " + ", ".join(w.strip() for w in pos + neg)
        return "neutral", 0.25, "no strong cue in the headline"


def _alias_map() -> list[tuple[str, re.Pattern]]:
    out: list[tuple[str, re.Pattern]] = []
    syms = all_symbols()
    for s, c in syms.items():
        names = {c.name.lower()} | set(ALIASES.get(s, []))
        for n in names:
            if len(n) < 3:
                continue
            out.append((s, re.compile(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])", re.I)))
    return out


class NewsService:
    def __init__(self, ttl: float = 90.0, timeout: float = 6.0, analyzer: Analyzer | None = None) -> None:
        self.ttl = ttl
        self.timeout = timeout
        self.analyzer = analyzer or LexiconAnalyzer()
        self._cache: list[Headline] = []
        self._by_id: dict[str, Headline] = {}
        self._at = 0.0
        self._errors: dict[str, str] = {}
        self._aliases = _alias_map()

    # ---- fetching -------------------------------------------------------------------------
    def _fetch_one(self, name: str, url: str) -> list[Headline]:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (DeltaDesk)"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            raw = r.read()
        root = ET.fromstring(raw)
        out = []
        for item in root.iter("item"):
            title = html.unescape((item.findtext("title") or "").strip())
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            desc = html.unescape(re.sub(r"<[^>]+>", " ", item.findtext("description") or "")).strip()
            desc = re.sub(r"\s+", " ", desc)[:500]
            ts, iso = 0.0, ""
            if pub:
                try:
                    dt = parsedate_to_datetime(pub)
                    ts, iso = dt.timestamp(), dt.isoformat()
                except (TypeError, ValueError):
                    pass
            if title:
                hid = hashlib.sha1((link or title).encode("utf-8")).hexdigest()[:12]
                out.append(Headline(id=hid, title=title, link=link, source=name, published=iso, ts=ts, description=desc))
        return out

    def _tag(self, h: Headline) -> None:
        text = h.title + " " + h.description[:200]
        h.symbols = sorted({s for s, rx in self._aliases if rx.search(text)})[:6]
        low = " " + text.lower() + " "
        h.topics = [t for t, words in TOPICS.items() if any(w in low for w in words)]
        h.impact, h.confidence, h.reason = self.analyzer.analyse(h)
        h.confidence = round(h.confidence, 2)

    def refresh(self, force: bool = False) -> None:
        now = time.time()
        if not force and now - self._at < self.ttl:
            return
        items: list[Headline] = []
        self._errors = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(FEEDS)) as ex:
            futs = {ex.submit(self._fetch_one, n, u): n for n, u in FEEDS}
            for f, n in futs.items():
                try:
                    items.extend(f.result())
                except Exception as e:  # noqa: BLE001 - offline or feed changed; keep going
                    self._errors[n] = type(e).__name__
        seen, dedup = set(), []
        for h in sorted(items, key=lambda h: -h.ts):
            k = h.title.lower()
            if k not in seen:
                seen.add(k)
                if h.id in self._by_id:
                    dedup.append(self._by_id[h.id])
                else:
                    self._tag(h)
                    dedup.append(h)
        self._cache, self._at = dedup, now
        self._by_id = {h.id: h for h in dedup}

    # ---- queries --------------------------------------------------------------------------
    def headlines(self, limit: int = 60, force: bool = False) -> dict:
        self.refresh(force)
        return {"fetched_at": self._at, "errors": self._errors, "sources": [n for n, _ in FEEDS],
                "entries": [h.json() for h in self._cache[:limit]]}

    def feed(self, symbols: list[str] | None = None, impact: str | None = None, since: float = 0.0,
             limit: int = 80, force: bool = False) -> dict:
        self.refresh(force)
        rows = self._cache
        if symbols:
            want = {s.upper() for s in symbols}
            rows = [h for h in rows if want & set(h.symbols) or want & set(h.topics)]
        if impact:
            rows = [h for h in rows if h.impact == impact]
        if since:
            rows = [h for h in rows if h.ts > since]
        counts = {"good": sum(1 for h in self._cache if h.impact == "good"), "bad": sum(1 for h in self._cache if h.impact == "bad"),
                  "neutral": sum(1 for h in self._cache if h.impact == "neutral")}
        return {"fetched_at": self._at, "errors": self._errors, "analyzer": self.analyzer.name, "counts": counts,
                "total": len(self._cache), "entries": [h.json() for h in rows[:limit]]}

    def item(self, hid: str) -> dict | None:
        self.refresh()
        h = self._by_id.get(hid)
        return h.json() if h else None

    def for_symbol(self, symbol: str, limit: int = 5) -> list[Headline]:
        self.refresh()
        s = symbol.upper()
        return [h for h in self._cache if s in h.symbols or s in h.topics][:limit]

    def trending(self, limit: int = 15) -> dict:
        data = self.headlines()
        counts: dict[str, int] = {}
        for h in self._cache:
            for w in re.findall(r"[A-Za-z][A-Za-z&'-]+", h.title):
                lw = w.lower()
                if lw in STOP or len(lw) < 3:
                    continue
                key = w if w[0].isupper() else lw
                counts[key] = counts.get(key, 0) + 1
        top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
        return {"fetched_at": data["fetched_at"], "errors": data["errors"],
                "entries": [{"term": t, "count": c} for t, c in top if c > 1]}


_ = INDICES  # index codes are valid topic filters too
