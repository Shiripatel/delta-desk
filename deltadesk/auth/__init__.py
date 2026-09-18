"""Broker credentials and tokens. Secrets come from the environment (.env); daily tokens are cached
under data/ so a restart during the session does not need a new login."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

TOKEN_DIR = Path("data")


def token_path(broker: str) -> Path:
    return TOKEN_DIR / f"{broker}_token.json"


def save_token(broker: str, access_token: str, extra: dict | None = None) -> Path:
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    p = token_path(broker)
    p.write_text(json.dumps({"access_token": access_token, "obtained_at": time.time(), **(extra or {})}, indent=2), encoding="utf-8")
    return p


def load_token(broker: str) -> str | None:
    """Environment variable first (<BROKER>_ACCESS_TOKEN), then the cached file from today's login."""
    env = os.environ.get(f"{broker.upper()}_ACCESS_TOKEN")
    if env:
        return env
    p = token_path(broker)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return d.get("access_token")
