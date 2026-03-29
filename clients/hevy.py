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

    def get_routines(self) -> list[dict]:
        """Return all routines for this account, paginated. Used for conflict detection."""
        routines: list[dict] = []
        page = 1
        while True:
            resp = self._client.get(
                "/v1/routines",
                params={"page": page, "pageSize": _PAGE_SIZE},
            )
            resp.raise_for_status()
            data = resp.json()
            routines.extend(data.get("routines", []))
            if page >= data.get("page_count", 1):
                break
            page += 1
        return routines

    def create_routine_folder(self, title: str) -> dict:
        """Create a routine folder to organise program routines. Returns the created folder dict."""
        resp = self._client.post(
            "/v1/routine_folders",
            json={"routine_folder": {"title": title}},
        )
        resp.raise_for_status()
        return resp.json().get("routine_folder", {})

    def create_routine(
        self,
        title: str,
        notes: str = "",
        folder_id: str | None = None,
        exercises: list[dict] | None = None,
    ) -> dict:
        """POST a new routine to Hevy.

        exercises should be a list of Hevy routine exercise objects:
        [
          {
            "exercise_template_id": "...",
            "superset_id": null,
            "rest_seconds": 90,
            "notes": "",
            "sets": [
              {"type": "normal", "weight_kg": null, "reps": 8,
               "duration_seconds": null, "distance_meters": null}
            ]
          }, ...
        ]
        """
        body = {
            "routine": {
                "title": title,
                "notes": notes,
                "exercises": exercises or [],
            }
        }
        if folder_id is not None:
            body["routine"]["folder_id"] = folder_id
        resp = self._client.post("/v1/routines", json=body)
        resp.raise_for_status()
        return resp.json().get("routine", {})

    def __enter__(self) -> "HevyClient":
        return self

    def __exit__(self, *_) -> None:
        self._client.close()
