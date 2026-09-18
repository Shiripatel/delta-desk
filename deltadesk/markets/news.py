"""Headlines from public RSS feeds, cached for five minutes, plus trending terms derived from them.

No API keys. If the machine is offline the result is empty with a note; the page keeps working.
Add or remove feeds in FEEDS. Licensed news APIs (Reuters, Bloomberg, Moneycontrol Pro) are a later
phase and plug into the same `Headline` shape.
"""
from __future__ import annotations

import concurrent.futures
import html
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from email.utils import parsedate_to_datetime

FEEDS = [
    ("Economic Times · Markets", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("Moneycontrol · Market reports", "https://www.moneycontrol.com/rss/marketreports.xml"),
    ("Mint · Markets", "https://www.livemint.com/rss/markets"),
    ("Business Standard · Markets", "https://www.business-standard.com/rss/markets-106.rss"),
]
STOP = set("the a an and of to in on for at by with from as is are be was were it its this that these those over "
           "after before up down into out amid says say said will may can could than more most new top today "
           "stock stocks market markets share shares nifty sensex rs crore per cent percent lakh india indian "
           "week day year live news update updates how why what who your you we our here now vs".split())


@dataclass
class Headline:
    title: str
    link: str
    source: str
    published: str          # ISO 8601 or ""
    ts: float               # epoch for sorting

    def json(self) -> dict:
        return asdict(self)


class NewsService:
    def __init__(self, ttl: float = 300.0, timeout: float = 6.0) -> None:
        self.ttl = ttl
        self.timeout = timeout
        self._cache: list[Headline] = []
        self._at = 0.0
        self._errors: dict[str, str] = {}

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
            ts, iso = 0.0, ""
            if pub:
                try:
                    dt = parsedate_to_datetime(pub)
                    ts, iso = dt.timestamp(), dt.isoformat()
                except (TypeError, ValueError):
                    pass
            if title:
                out.append(Headline(title=title, link=link, source=name, published=iso, ts=ts))
        return out

    def headlines(self, limit: int = 60, force: bool = False) -> dict:
        now = time.time()
        if force or now - self._at > self.ttl:
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
                    dedup.append(h)
            self._cache, self._at = dedup, now
        return {"fetched_at": self._at, "errors": self._errors, "sources": [n for n, _ in FEEDS],
                "entries": [h.json() for h in self._cache[:limit]]}

    def trending(self, limit: int = 15) -> dict:
        data = self.headlines()
        counts: dict[str, int] = {}
        for h in self._cache:
            words = re.findall(r"[A-Za-z][A-Za-z&'-]+", h.title)
            for w in words:
                lw = w.lower()
                if lw in STOP or len(lw) < 3:
                    continue
                key = w if w[0].isupper() else lw
                counts[key] = counts.get(key, 0) + 1
        top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
        return {"fetched_at": data["fetched_at"], "errors": data["errors"],
                "entries": [{"term": t, "count": c} for t, c in top if c > 1]}
