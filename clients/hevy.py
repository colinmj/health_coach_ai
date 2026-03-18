"""Hevy API client.

Docs: https://api.hevyapp.com/docs
Auth: api-key header
Workouts are returned newest-first by default.
"""

from typing import Iterator

import httpx

_BASE_URL = "https://api.hevyapp.com"
_PAGE_SIZE = 10


class HevyClient:
    def __init__(self, api_key: str) -> None:
        self._client = httpx.Client(
            base_url=_BASE_URL,
            headers={"api-key": api_key},
            timeout=30.0,
        )

    def iter_workouts(self, page_size: int = _PAGE_SIZE) -> Iterator[dict]:
        """Yield all workouts, paginating automatically (newest-first)."""
        page = 1
        while True:
            resp = self._client.get(
                "/v1/workouts",
                params={"page": page, "pageSize": page_size},
            )
            resp.raise_for_status()
            data = resp.json()

            workouts = data.get("workouts", [])
            yield from workouts

            if page >= data.get("page_count", 1):
                break
            page += 1

    def __enter__(self) -> "HevyClient":
        return self

    def __exit__(self, *_) -> None:
        self._client.close()
