"""Strava API v3 client.

Docs: https://developers.strava.com/docs/reference/
Auth: OAuth2 bearer token with auto-refresh via refresh token.
Pagination: page-based (per_page + page params, stop when empty).
"""

from datetime import datetime
from typing import Callable, Iterator

import httpx

_BASE_URL = "https://www.strava.com/api/v3"
_TOKEN_URL = "https://www.strava.com/oauth/token"
_PAGE_SIZE = 100


class StravaClient:
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

    def _get(self, path: str, params: dict | None = None) -> list | dict:
        resp = self._client.get(path, params=params)
        if resp.status_code == 401:
            self._refresh_access_token()
            resp = self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    def iter_activities(self, after: datetime | None = None) -> Iterator[dict]:
        """Yield all athlete activities, optionally filtered by start time."""
        params: dict = {"per_page": _PAGE_SIZE, "page": 1}
        if after:
            params["after"] = int(after.timestamp())
        while True:
            activities = self._get("/athlete/activities", params)
            if not activities:
                break
            yield from activities
            params["page"] += 1

    def __enter__(self) -> "StravaClient":
        return self

    def __exit__(self, *_) -> None:
        self._client.close()
