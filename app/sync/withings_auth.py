"""One-time Withings OAuth2 authorisation flow.

Run:
    python -m sync.withings_auth

Opens your browser, catches the callback on localhost:8585, exchanges the
code for tokens, and writes WITHINGS_ACCESS_TOKEN / WITHINGS_REFRESH_TOKEN
into your .env file.  Re-run only if both tokens become invalid.
"""

import os
import secrets
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx
from dotenv import load_dotenv, set_key

load_dotenv()

_ENV_PATH = Path(".env")
_AUTH_URL = "https://account.withings.com/oauth2_user/authorize2"
_TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"
_SCOPES = "user.metrics"


def _build_auth_url(client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": _SCOPES,
        "state": state,
    }
    return f"{_AUTH_URL}?{urllib.parse.urlencode(params)}"


def _exchange_code(code: str, client_id: str, client_secret: str, redirect_uri: str) -> dict:
    resp = httpx.post(
        _TOKEN_URL,
        data={
            "action": "requesttoken",
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("status") != 0:
        raise RuntimeError(f"Token exchange failed: {body}")
    return body["body"]


def run() -> None:
    client_id = os.environ["WITHINGS_CLIENT_ID"]
    client_secret = os.environ["WITHINGS_CLIENT_SECRET"]
    redirect_uri = os.environ.get("WITHINGS_REDIRECT_URI", "http://localhost:8585/callback")

    state = secrets.token_urlsafe(16)
    received_code: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            if code:
                received_code.append(code)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Authorisation complete. You can close this tab.")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing code parameter.")

        def log_message(self, *_) -> None:
            pass  # suppress request logs

    port = int(urllib.parse.urlparse(redirect_uri).port or 8585)
    server = HTTPServer(("localhost", port), Handler)

    def _serve():
        server.handle_request()

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()

    auth_url = _build_auth_url(client_id, redirect_uri, state)
    print(f"Opening browser for Withings authorisation…\n{auth_url}\n")
    webbrowser.open(auth_url)

    thread.join(timeout=120)

    if not received_code:
        raise RuntimeError("No authorisation code received within 120 seconds.")

    print("Exchanging code for tokens…")
    tokens = _exchange_code(received_code[0], client_id, client_secret, redirect_uri)

    set_key(_ENV_PATH, "WITHINGS_ACCESS_TOKEN", tokens["access_token"])
    set_key(_ENV_PATH, "WITHINGS_REFRESH_TOKEN", tokens["refresh_token"])
    print("Tokens saved to .env. You can now run: python -m sync.withings")


if __name__ == "__main__":
    run()
