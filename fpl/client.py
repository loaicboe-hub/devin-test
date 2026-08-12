"""Client for the official Fantasy Premier League API."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "https://fantasy.premierleague.com/api"
USER_AGENT = "fpl-analysis/0.1 (+https://github.com/loaicboe-hub/devin-test)"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "fpl-analysis"
DEFAULT_TTL = 900.0


class FPLError(RuntimeError):
    """Raised when the FPL API cannot be reached or returns an error."""


class FPLClient:
    """Fetches data from the public FPL endpoints with an on-disk cache.

    The public endpoints are unauthenticated and rate limited, so responses are
    cached for ``ttl`` seconds to avoid hammering the API during analysis runs.
    """

    def __init__(
        self,
        cache_dir: Path | str = DEFAULT_CACHE_DIR,
        ttl: float = DEFAULT_TTL,
        timeout: float = 30.0,
        retries: int = 3,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.ttl = ttl
        self.timeout = timeout
        self.retries = retries

    def bootstrap_static(self, refresh: bool = False) -> dict[str, Any]:
        """Players, teams, positions and gameweeks."""
        return self._get("bootstrap-static/", "bootstrap-static", refresh)

    def fixtures(self, event: int | None = None, refresh: bool = False) -> list[dict[str, Any]]:
        """All fixtures, or only those of a single gameweek."""
        path = "fixtures/" if event is None else f"fixtures/?event={event}"
        name = "fixtures" if event is None else f"fixtures-{event}"
        return self._get(path, name, refresh)

    def element_summary(self, player_id: int, refresh: bool = False) -> dict[str, Any]:
        """Per-gameweek history and remaining fixtures for a single player."""
        return self._get(
            f"element-summary/{player_id}/", f"element-summary-{player_id}", refresh
        )

    def entry(self, entry_id: int, refresh: bool = False) -> dict[str, Any]:
        """Public summary of an FPL manager's team."""
        return self._get(f"entry/{entry_id}/", f"entry-{entry_id}", refresh)

    def _get(self, path: str, cache_name: str, refresh: bool) -> Any:
        cached = None if refresh else self._read_cache(cache_name)
        if cached is not None:
            return cached
        payload = self._fetch(f"{BASE_URL}/{path}")
        self._write_cache(cache_name, payload)
        return payload

    def _fetch(self, url: str) -> Any:
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                last_error = exc
                if exc.code < 500 and exc.code != 429:
                    break
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
            time.sleep(2**attempt)
        raise FPLError(f"failed to fetch {url}: {last_error}") from last_error

    def _cache_path(self, name: str) -> Path:
        return self.cache_dir / f"{name}.json"

    def _read_cache(self, name: str) -> Any:
        path = self._cache_path(name)
        try:
            if time.time() - path.stat().st_mtime > self.ttl:
                return None
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _write_cache(self, name: str, payload: Any) -> None:
        path = self._cache_path(name)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            pass
