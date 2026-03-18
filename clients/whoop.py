"""Whoop API v2 client.

Docs: https://developer.whoop.com/docs/developing/
Auth: OAuth2 bearer token with auto-refresh via refresh token.
Pagination: token-based (next_token field).
"""

from pathlib import Path
from typing import Iterator

import httpx
from dotenv import get_key, set_key

_BASE_URL = "https://api.prod.whoop.com"
_TOKEN_URL = f"{_BASE_URL}/oauth/oauth2/token"
_ENV_PATH = Path(".env")
_PAGE_SIZE = 25


class WhoopClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        access_token: str,
        refresh_token: str,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._client = httpx.Client(base_url=_BASE_URL, timeout=30.0)
        self._client.headers["Authorization"] = f"Bearer {access_token}"

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def _refresh_access_token(self) -> None:
        """Exchange the refresh token for a new access token and persist both."""
        resp = httpx.post(
            _TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        resp.raise_for_status()
        tokens = resp.json()
        self._client.headers["Authorization"] = f"Bearer {tokens['access_token']}"
        self._refresh_token = tokens["refresh_token"]
        set_key(_ENV_PATH, "WHOOP_ACCESS_TOKEN", tokens["access_token"])
        set_key(_ENV_PATH, "WHOOP_REFRESH_TOKEN", tokens["refresh_token"])

    def _get(self, path: str, params: dict | None = None) -> dict:
        """GET with one automatic token refresh on 401."""
        resp = self._client.get(path, params=params)
        if resp.status_code == 401:
            self._refresh_access_token()
            resp = self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Iteration helpers
    # ------------------------------------------------------------------

    def _iter_collection(self, path: str, params: dict | None = None) -> Iterator[dict]:
        """Yield all records from a paginated collection endpoint."""
        params = dict(params or {})
        params["limit"] = _PAGE_SIZE
        while True:
            data = self._get(path, params)
            yield from data.get("records", [])
            next_token = data.get("next_token")
            if not next_token:
                break
            params["nextToken"] = next_token

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def iter_cycles(self, start: str | None = None, end: str | None = None) -> Iterator[dict]:
        """Yield all physiological cycles (contains nested recovery data)."""
        params: dict = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        yield from self._iter_collection("/v2/cycle", params)

    def iter_sleep(self, start: str | None = None, end: str | None = None) -> Iterator[dict]:
        """Yield all sleep records (excludes naps by default — filtered in sync)."""
        params: dict = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        yield from self._iter_collection("/v2/activity/sleep", params)

    def __enter__(self) -> "WhoopClient":
        return self

    def __exit__(self, *_) -> None:
        self._client.close()
