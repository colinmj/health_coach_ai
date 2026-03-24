"""Oura Ring API v2 client.

Docs: https://cloud.ouraring.com/v2/docs
Auth: Personal Access Token (Bearer token) — no refresh needed.
Pagination: next_token field in response body.
"""

from typing import Iterator

import httpx

_BASE_URL = "https://api.ouraring.com"
_PAGE_SIZE = 50


class OuraClient:
    def __init__(self, api_key: str) -> None:
        self._client = httpx.Client(
            base_url=_BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    def _get(self, path: str, params: dict | None = None) -> dict:
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
        yield from self._iter_collection("/v2/usercollection/readiness", params)

    def __enter__(self) -> "OuraClient":
        return self

    def __exit__(self, *_) -> None:
        self._client.close()
