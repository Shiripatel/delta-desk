"""Upstox OAuth login: opens the browser, catches the redirect on localhost, exchanges the code, caches the token.

Setup (once): create an app at https://account.upstox.com/developer/apps with redirect URL
http://127.0.0.1:8765/upstox/callback, then put UPSTOX_API_KEY and UPSTOX_API_SECRET in .env.
Daily: `uv run deltadesk login upstox`. Tokens expire at 03:30 IST the next day.
"""
from __future__ import annotations

import os
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from deltadesk.auth import save_token

AUTH_URL = "https://api.upstox.com/v2/login/authorization/dialog"
DEFAULT_REDIRECT = "http://127.0.0.1:8765/upstox/callback"


def authorize_url(client_id: str, redirect_uri: str) -> str:
    q = urllib.parse.urlencode({"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri})
    return f"{AUTH_URL}?{q}"


def exchange_code(code: str, client_id: str, client_secret: str, redirect_uri: str) -> str:
    import upstox_client  # lazy: optional dependency

    api = upstox_client.LoginApi(upstox_client.ApiClient(upstox_client.Configuration()))
    resp = api.token(api_version="2.0", code=code, client_id=client_id, client_secret=client_secret,
                     redirect_uri=redirect_uri, grant_type="authorization_code")
    return resp.access_token


def _catch_code(redirect_uri: str, timeout: float = 300.0) -> str | None:
    u = urllib.parse.urlparse(redirect_uri)
    got: dict[str, str] = {}
    done = threading.Event()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in qs:
                got["code"] = qs["code"][0]
                body = b"<h3>Delta Desk: Upstox login done. You can close this tab.</h3>"
            else:
                body = b"<h3>No code in the redirect. Check the app's redirect URL.</h3>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)
            done.set()

        def log_message(self, *a):  # silence
            return

    srv = HTTPServer((u.hostname or "127.0.0.1", u.port or 80), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    done.wait(timeout)
    srv.shutdown()
    return got.get("code")


def login(open_browser: bool = True) -> str:
    client_id = os.environ.get("UPSTOX_API_KEY", "")
    client_secret = os.environ.get("UPSTOX_API_SECRET", "")
    redirect_uri = os.environ.get("UPSTOX_REDIRECT_URI", DEFAULT_REDIRECT)
    if not client_id or not client_secret:
        raise SystemExit("Set UPSTOX_API_KEY and UPSTOX_API_SECRET in .env (see deltadesk/auth/upstox_login.py)")
    url = authorize_url(client_id, redirect_uri)
    print("Open this URL to log in to Upstox:\n  " + url)
    if open_browser:
        webbrowser.open(url)
    code = _catch_code(redirect_uri)
    if not code:
        raise SystemExit("Login timed out or the redirect did not carry a code.")
    token = exchange_code(code, client_id, client_secret, redirect_uri)
    p = save_token("upstox", token)
    print(f"Upstox access token saved to {p} (valid until 03:30 IST tomorrow).")
    return token
