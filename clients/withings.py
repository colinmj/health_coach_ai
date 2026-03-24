"""Withings API client.

Docs: https://developer.withings.com/api-reference/
Auth: OAuth2 bearer token with auto-refresh via refresh token.
Pagination: offset-based (more == 1 signals additional pages).
"""

from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator

import httpx
from dotenv import set_key

_BASE_URL = "https://wbsapi.withings.net"
_TOKEN_URL = f"{_BASE_URL}/v2/oauth2"
_ENV_PATH = Path(".env")

# Measure type codes: https://developer.withings.com/api-reference/#tag/measure/operation/measure-getmeas
_MEASTYPES = "1,5,6,8,76,77,88"


class WithingsClient:
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

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def _refresh_access_token(self) -> None:
        """Exchange the refresh token for a new access token and persist both."""
        resp = httpx.post(
            _TOKEN_URL,
            data={
                "action": "requesttoken",
                "grant_type": "refresh_token",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": self._refresh_token,
            },
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("status") != 0:
            raise RuntimeError(f"Withings token refresh failed: {body}")
        tokens = body["body"]
        self._client.headers["Authorization"] = f"Bearer {tokens['access_token']}"
        self._refresh_token = tokens["refresh_token"]
        if self._on_token_refresh:
            self._on_token_refresh(tokens["access_token"], tokens["refresh_token"])
        else:
            set_key(_ENV_PATH, "WITHINGS_ACCESS_TOKEN", tokens["access_token"])
            set_key(_ENV_PATH, "WITHINGS_REFRESH_TOKEN", tokens["refresh_token"])

    def _post(self, path: str, params: dict) -> dict:
        """POST with one automatic token refresh on 401 or invalid_token status."""
        resp = self._client.post(path, data=params)
        resp.raise_for_status()
        body = resp.json()
        if body.get("status") == 401:
            self._refresh_access_token()
            resp = self._client.post(path, data=params)
            resp.raise_for_status()
            body = resp.json()
        if body.get("status") != 0:
            raise RuntimeError(f"Withings API error: {body}")
        return body

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def iter_body_measurements(self, startdate: int | None = None) -> Iterator[dict]:
        """Yield raw measuregrp dicts for all body composition measurements.

        Args:
            startdate: Unix timestamp; if provided, only measurements after this
                       date are returned.
        """
        params: dict = {
            "action": "getmeas",
            "meastype": _MEASTYPES,
            "category": 1,  # real measures (not targets)
        }
        if startdate is not None:
            params["startdate"] = startdate

        offset = 0
        while True:
            if offset:
                params["offset"] = offset
            body = self._post("/measure", params)
            measure_grps = body.get("body", {}).get("measuregrps", [])
            yield from measure_grps
            if body.get("body", {}).get("more") != 1:
                break
            offset = body["body"].get("offset", offset + len(measure_grps))

    def __enter__(self) -> "WithingsClient":
        return self

    def __exit__(self, *_) -> None:
        self._client.close()
