"""Oura Ring API v2 client.

Docs: https://cloud.ouraring.com/v2/docs
Auth: OAuth2 bearer token with auto-refresh. Oura refresh tokens are single-use —
      the new refresh token must be persisted immediately after each refresh.
Pagination: next_token field in response body.
"""

import os
from typing import Callable, Iterator

import httpx

_BASE_URL = "https://api.ouraring.com"
_TOKEN_URL = "https://api.ouraring.com/oauth/token"
_PAGE_SIZE = 50


class OuraClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        access_token: str,
        refresh_token: str,
        on_token_refresh: Callable[[str, str], None] | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._on_token_refresh = on_token_refresh
        self._client = httpx.Client(base_url=_BASE_URL, timeout=30.0)
        self._client.headers["Authorization"] = f"Bearer {access_token}"

    def _refresh_access_token(self) -> None:
        """Exchange the refresh token for a new access + refresh token pair.

        Oura refresh tokens are single-use — must persist immediately.
        """
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
        if self._on_token_refresh:
            self._on_token_refresh(tokens["access_token"], tokens["refresh_token"])

    def _get(self, path: str, params: dict | None = None) -> dict:
        """GET with one automatic token refresh on 401."""
        resp = self._client.get(path, params=params)
        if resp.status_code == 401:
            self._refresh_access_token()
            resp = self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    def _iter_collection(self, path: str, params: dict | None = None) -> Iterator[dict]:
        params = dict(params or {})
        while True:
            data = self._get(path, params)
            yield from data.get("data", [])
            next_token = data.get("next_token")
            if not next_token:
                break
            params["next_token"] = next_token

    def iter_sleep(self, start_date: str | None = None) -> Iterator[dict]:
        """Yield all sleep session records."""
        params: dict = {}
        if start_date:
            params["start_date"] = start_date
        yield from self._iter_collection("/v2/usercollection/sleep", params)

    def iter_readiness(self, start_date: str | None = None) -> Iterator[dict]:
        """Yield all daily readiness records (recovery score, HRV, RHR)."""
        params: dict = {}
        if start_date:
            params["start_date"] = start_date
        yield from self._iter_collection("/v2/usercollection/daily_readiness", params)

    def __enter__(self) -> "OuraClient":
        return self

    def __exit__(self, *_) -> None:
        self._client.close()
