"""Built-in traffic log: who looked at which page, without cookies or third parties.

Every page view is appended to data/traffic.jsonl as {ts, path, visitor, ref, ua}. The visitor id is a
salted hash of IP and user agent that changes every day, so nobody can be followed across days and
nothing personal is stored. Static files and API calls are not logged. `summary()` rolls the log up into
views and unique visitors per day, top pages and referrers for the admin view at /admin/traffic, which
is protected by DD_ADMIN_TOKEN. Swap in a hosted product later (Plausible, Umami, PostHog) if you want
funnels; this answers "is anyone coming, and where from" on day one.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

PAGE_PATHS = {"/", "/watchlist", "/heatmap", "/news", "/ipo", "/forex", "/global", "/desk", "/sniper", "/analysis", "/beta", "/legal"}


class Traffic:
    def __init__(self, path: Path = Path("data") / "traffic.jsonl", salt: str | None = None) -> None:
        self.path = path
        self.salt = salt or os.environ.get("DD_TRAFFIC_SALT") or secrets.token_hex(8)
        self._lock = threading.Lock()

    @staticmethod
    def is_page(path: str) -> bool:
        return path in PAGE_PATHS or path.startswith("/ipo/")

    def visitor(self, ip: str, ua: str) -> str:
        day = date.today().isoformat()
        return hashlib.sha256(f"{self.salt}|{day}|{ip}|{ua}".encode()).hexdigest()[:16]

    def record(self, path: str, ip: str, ua: str, ref: str = "") -> None:
        if not self.is_page(path):
            return
        row = {"ts": round(time.time(), 3), "path": "/ipo/…" if path.startswith("/ipo/") else path, "visitor": self.visitor(ip, ua),
               "ref": _host(ref), "ua": _family(ua)}
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")

    def rows(self, days: int = 30) -> list[dict]:
        if not self.path.exists():
            return []
        since = time.time() - days * 86400
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("ts", 0) >= since:
                out.append(r)
        return out

    def summary(self, days: int = 30) -> dict:
        rows = self.rows(days)
        by_day: dict[str, dict] = defaultdict(lambda: {"views": 0, "visitors": set()})
        pages, refs, uas = Counter(), Counter(), Counter()
        visitors_all: set[str] = set()
        for r in rows:
            d = datetime.fromtimestamp(r["ts"], tz=UTC).date().isoformat()
            by_day[d]["views"] += 1
            by_day[d]["visitors"].add(r["visitor"])
            visitors_all.add(r["visitor"])
            pages[r["path"]] += 1
            refs[r.get("ref") or "direct"] += 1
            uas[r.get("ua") or "other"] += 1
        daily = [{"day": d, "views": v["views"], "visitors": len(v["visitors"])} for d, v in sorted(by_day.items())]
        today = date.today().isoformat()
        return {"days": days, "views": len(rows), "visitors": len(visitors_all), "today": next((x for x in daily if x["day"] == today), {"day": today, "views": 0, "visitors": 0}),  # noqa: E501
                "daily": daily, "pages": [{"path": p, "views": n} for p, n in pages.most_common(20)],
                "referrers": [{"ref": r, "views": n} for r, n in refs.most_common(15)], "devices": [{"ua": u, "views": n} for u, n in uas.most_common(8)],  # noqa: E501
                "note": "Visitor ids are salted daily hashes of IP and user agent: no cookies, no personal data, no cross-day tracking."}


def _host(ref: str) -> str:
    if not ref:
        return ""
    ref = ref.split("//", 1)[-1].split("/", 1)[0].lower()
    return "" if ref in ("localhost:8000", "127.0.0.1:8000") else ref


def _family(ua: str) -> str:
    u = (ua or "").lower()
    if "bot" in u or "spider" in u or "crawl" in u:
        return "bot"
    if "mobile" in u or "android" in u or "iphone" in u:
        return "mobile"
    if "ipad" in u or "tablet" in u:
        return "tablet"
    return "desktop" if u else "other"
