"""Beta programme: waitlist sign-ups, alert rules, and notifiers (WhatsApp Cloud API, Telegram, dry-run).

Storage is plain files under data/ (gitignored): waitlist.jsonl (one sign-up per line), alerts.json
(rules), alerts_log.jsonl (every evaluation that fired). Swap for a database when there is more than
one desk.

Notifiers
* WhatsApp: Meta's Cloud API. Env WHATSAPP_TOKEN and WHATSAPP_PHONE_ID (from developers.facebook.com,
  free tier: user-initiated conversations are free, business-initiated ones need an approved template
  after the 24-hour window). Recipients are E.164 without "+", e.g. 91XXXXXXXXXX.
* Telegram: env TELEGRAM_BOT_TOKEN; the recipient is the chat id the user gets after messaging the bot.
* Dry run: when neither is configured every alert is logged with `sent: false` and shown on the page,
  so the rules can be built and tested before any account exists.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

DATA = Path("data")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?\d{10,15}$")
INTERESTS = {"stocks", "fno", "ipo", "news", "agents"}
KINDS = {"price_move": "price moves more than X % on the day", "price_above": "price crosses above X", "price_below": "price crosses below X",  # noqa: E501
         "verdict_flip": "council verdict changes at a horizon", "bad_news": "a bad-impact headline tags the stock"}


# ---- waitlist -------------------------------------------------------------------------------------
class Waitlist:
    def __init__(self, path: Path = DATA / "waitlist.jsonl") -> None:
        self.path = path
        self._lock = threading.Lock()

    def _rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def join(self, name: str, email: str, phone: str = "", interests: list[str] | None = None, experience: str = "",
             whatsapp_ok: bool = False, source: str = "web") -> dict:
        name, email, phone = (name or "").strip()[:80], (email or "").strip().lower(), re.sub(r"[\s-]", "", phone or "")
        if len(name) < 2:
            return {"ok": False, "error": "name is too short"}
        if not EMAIL_RE.match(email):
            return {"ok": False, "error": "email looks wrong"}
        if phone and not PHONE_RE.match(phone):
            return {"ok": False, "error": "phone should be digits with country code, e.g. +91XXXXXXXXXX"}
        ints = sorted({i for i in (interests or []) if i in INTERESTS})
        with self._lock:
            rows = self._rows()
            if any(r.get("email") == email for r in rows):
                return {"ok": True, "duplicate": True, "position": next(i + 1 for i, r in enumerate(rows) if r.get("email") == email),
                        "total": len(rows)}
            row = {"ts": time.time(), "name": name, "email": email, "phone": phone, "interests": ints, "experience": experience[:40],
                   "whatsapp_ok": bool(whatsapp_ok and phone), "source": source}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            return {"ok": True, "duplicate": False, "position": len(rows) + 1, "total": len(rows) + 1}

    def stats(self) -> dict:
        rows = self._rows()
        by_int: dict[str, int] = {}
        for r in rows:
            for i in r.get("interests", []):
                by_int[i] = by_int.get(i, 0) + 1
        return {"total": len(rows), "whatsapp": sum(1 for r in rows if r.get("whatsapp_ok")), "interests": by_int,
                "last_24h": sum(1 for r in rows if time.time() - r.get("ts", 0) < 86400)}


# ---- notifiers ------------------------------------------------------------------------------------
class Notifier:
    name = "dry-run"

    def send(self, to: str, text: str) -> dict:
        return {"sent": False, "channel": self.name, "to": to, "note": "no WhatsApp/Telegram credentials configured; logged only"}


class WhatsAppNotifier(Notifier):
    name = "whatsapp"

    def __init__(self, token: str, phone_id: str, timeout: float = 10.0) -> None:
        self.token, self.phone_id, self.timeout = token, phone_id, timeout

    def send(self, to: str, text: str) -> dict:
        body = json.dumps({"messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "text", "text": {"body": text[:4000]}}).encode()
        req = urllib.request.Request(f"https://graph.facebook.com/v20.0/{self.phone_id}/messages", data=body,
                                     headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                out = json.load(r)
            return {"sent": True, "channel": self.name, "to": to, "id": (out.get("messages") or [{}])[0].get("id")}
        except Exception as e:  # noqa: BLE001
            return {"sent": False, "channel": self.name, "to": to, "error": f"{type(e).__name__}: {str(e)[:120]}"}


class TelegramNotifier(Notifier):
    name = "telegram"

    def __init__(self, token: str, timeout: float = 10.0) -> None:
        self.token, self.timeout = token, timeout

    def send(self, to: str, text: str) -> dict:
        q = urllib.parse.urlencode({"chat_id": to, "text": text[:4000]})
        try:
            with urllib.request.urlopen(f"https://api.telegram.org/bot{self.token}/sendMessage?{q}", timeout=self.timeout) as r:
                out = json.load(r)
            return {"sent": bool(out.get("ok")), "channel": self.name, "to": to}
        except Exception as e:  # noqa: BLE001
            return {"sent": False, "channel": self.name, "to": to, "error": f"{type(e).__name__}: {str(e)[:120]}"}


def notifier_from_env() -> Notifier:
    if os.environ.get("WHATSAPP_TOKEN") and os.environ.get("WHATSAPP_PHONE_ID"):
        return WhatsAppNotifier(os.environ["WHATSAPP_TOKEN"], os.environ["WHATSAPP_PHONE_ID"])
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        return TelegramNotifier(os.environ["TELEGRAM_BOT_TOKEN"])
    return Notifier()


# ---- alert rules + engine ----------------------------------------------------------------------------
class Alerts:
    def __init__(self, markets, notifier: Notifier | None = None, path: Path = DATA / "alerts.json", log_path: Path = DATA / "alerts_log.jsonl",  # noqa: E501
                 cooldown: float = 3600.0) -> None:
        self.m = markets
        self.notifier = notifier or notifier_from_env()
        self.path, self.log_path, self.cooldown = path, log_path, cooldown
        self.rules: list[dict] = []
        self._lock = threading.Lock()
        self._state: dict[str, dict] = {}       # rule id -> last verdict / last fired
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self.rules = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.rules = []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.rules, indent=2), encoding="utf-8")

    def add(self, contact: str, kind: str, symbol: str, value: float | None = None, horizon: str = "1d", channel: str = "auto") -> dict:
        contact = (contact or "").strip()
        if not contact:
            return {"ok": False, "error": "contact (phone with country code, Telegram chat id, or email) is required"}
        if kind not in KINDS:
            return {"ok": False, "error": f"kind must be one of {sorted(KINDS)}"}
        symbol = (symbol or "").upper().strip()
        if not symbol or not self.m.known(symbol):
            return {"ok": False, "error": f"unknown symbol {symbol!r}"}
        if kind.startswith("price") and (value is None or value <= 0):
            return {"ok": False, "error": "value must be a positive number"}
        rule = {"id": "a" + uuid.uuid4().hex[:8], "ts": time.time(), "contact": contact, "kind": kind, "symbol": symbol,
                "value": value, "horizon": horizon, "channel": channel, "active": True}
        with self._lock:
            self.rules.append(rule)
            self._save()
        return {"ok": True, "rule": rule}

    def remove(self, rule_id: str) -> bool:
        with self._lock:
            n = len(self.rules)
            self.rules = [r for r in self.rules if r["id"] != rule_id]
            if len(self.rules) != n:
                self._save()
            return len(self.rules) != n

    def for_contact(self, contact: str) -> list[dict]:
        return [r for r in self.rules if r["contact"] == contact.strip()]

    def _fire(self, rule: dict, text: str, now: float) -> dict:
        st = self._state.setdefault(rule["id"], {})
        if now - st.get("fired", 0) < self.cooldown:
            return {"skipped": "cooldown"}
        res = self.notifier.send(rule["contact"], text)
        st["fired"] = now
        entry = {"ts": now, "rule": rule["id"], "symbol": rule["symbol"], "kind": rule["kind"], "text": text, **res}
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def evaluate(self, now: float | None = None) -> list[dict]:
        """Check every active rule once. Returns the alerts that fired (or were logged in dry-run)."""
        now = now or time.time()
        fired = []
        active = [r for r in self.rules if r.get("active")]
        if not active:
            return fired
        syms = sorted({r["symbol"] for r in active})
        quotes = self.m.quotes.quotes(syms)
        for r in active:
            q = quotes.get(r["symbol"])
            text = None
            if r["kind"] == "price_move" and q and abs(q.change_pct) >= r["value"]:
                text = f"{r['symbol']} moved {q.change_pct:+.2f} % today to {q.ltp:,.2f} (alert at ±{r['value']} %)."
            elif r["kind"] == "price_above" and q and q.ltp >= r["value"]:
                text = f"{r['symbol']} is at {q.ltp:,.2f}, above your level {r['value']:,.2f}."
            elif r["kind"] == "price_below" and q and q.ltp <= r["value"]:
                text = f"{r['symbol']} is at {q.ltp:,.2f}, below your level {r['value']:,.2f}."
            elif r["kind"] == "verdict_flip":
                v = self.m.council_run(r["symbol"], r.get("horizon") or "1d")["verdict"]
                st = self._state.setdefault(r["id"], {})
                prev = st.get("stance")
                st["stance"] = v["stance"]
                if prev and prev != v["stance"]:
                    text = f"Council on {r['symbol']} ({r.get('horizon') or '1d'}) changed from {prev.upper()} to {v['stance'].upper()} (score {v['score']:+.2f})."  # noqa: E501
            elif r["kind"] == "bad_news":
                news = [h for h in self.m.news.for_symbol(r["symbol"], limit=3) if h.impact == "bad"]
                st = self._state.setdefault(r["id"], {})
                fresh = [h for h in news if h.id not in st.get("seen", [])]
                if fresh:
                    st["seen"] = (st.get("seen", []) + [h.id for h in fresh])[-50:]
                    text = f"Bad-impact news on {r['symbol']}: {fresh[0].title} ({fresh[0].source})."
            if text:
                text += " · Delta Desk, rules model v0, not advice."
                out = self._fire(r, text, now)
                if "skipped" not in out:
                    fired.append(out)
        return fired

    def log(self, limit: int = 50) -> list[dict]:
        if not self.log_path.exists():
            return []
        lines = self.log_path.read_text(encoding="utf-8").splitlines()[-limit:]
        out = []
        for line in reversed(lines):
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def test(self, contact: str) -> dict:
        return self.notifier.send(contact, "Delta Desk test alert. If you can read this, alerts work. Not advice.")
