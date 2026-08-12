"""Local web dashboard for the FPL analysis data.

Serves a single-page UI plus a small JSON API on top of :mod:`fpl.client`,
using only the standard library.
"""

from __future__ import annotations

import argparse
import json
import webbrowser
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .analysis import SORT_KEYS, differentials, filter_players, rank, team_totals
from .client import DEFAULT_TTL, FPLClient, FPLError
from .models import Bootstrap, Player

STATIC_DIR = Path(__file__).parent / "static"
CONTENT_TYPES = {".html": "text/html", ".css": "text/css", ".js": "text/javascript"}


class BadRequest(ValueError):
    """Raised when query parameters are invalid."""


def player_payload(player: Player) -> dict[str, object]:
    return asdict(player) | {"value": player.value, "form_value": player.form_value}


class Api:
    """Query handlers shared by the HTTP server and the tests."""

    def __init__(self, client: FPLClient | None = None) -> None:
        self.client = client or FPLClient()

    def bootstrap(self, refresh: bool = False) -> Bootstrap:
        return Bootstrap.from_api(self.client.bootstrap_static(refresh=refresh))

    def status(self, query: dict[str, list[str]]) -> dict[str, object]:
        bootstrap = self.bootstrap(_flag(query, "refresh"))
        current, upcoming = bootstrap.current_gameweek, bootstrap.next_gameweek
        return {
            "player_count": len(bootstrap.players),
            "team_count": len(bootstrap.teams),
            "teams": sorted(team.short_name for team in bootstrap.teams.values()),
            "positions": ["GKP", "DEF", "MID", "FWD"],
            "sort_keys": sorted(SORT_KEYS),
            "current_gameweek": current.name if current else None,
            "next_gameweek": upcoming.name if upcoming else None,
            "next_deadline": upcoming.deadline_time if upcoming else None,
        }

    def players(self, query: dict[str, list[str]]) -> dict[str, object]:
        bootstrap = self.bootstrap(_flag(query, "refresh"))
        team = _str(query, "team")
        if team:
            known = {t.short_name.upper() for t in bootstrap.teams.values()}
            if team.upper() not in known:
                raise BadRequest(f"unknown team {team!r}")
        position = _str(query, "position")
        if position and position.upper() not in {"GKP", "DEF", "MID", "FWD"}:
            raise BadRequest(f"unknown position {position!r}")
        sort_key = _str(query, "sort") or "points"
        if sort_key not in SORT_KEYS:
            raise BadRequest(f"unknown sort key {sort_key!r}")

        pool = filter_players(
            bootstrap.players,
            position=position,
            team=team,
            max_cost=_float(query, "max_cost"),
            min_minutes=_int(query, "min_minutes", 0),
            available_only=_flag(query, "available_only"),
        )
        limit = _int(query, "limit", 50)
        if limit < 1:
            raise BadRequest("limit must be a positive integer")
        return {
            "total": len(pool),
            "sort": sort_key,
            "players": [player_payload(p) for p in rank(pool, sort_key, limit)],
        }

    def differentials(self, query: dict[str, list[str]]) -> dict[str, object]:
        bootstrap = self.bootstrap(_flag(query, "refresh"))
        limit = _int(query, "limit", 20)
        if limit < 1:
            raise BadRequest("limit must be a positive integer")
        max_ownership = _float(query, "max_ownership")
        picks = differentials(
            bootstrap.players, 10.0 if max_ownership is None else max_ownership, limit
        )
        return {"players": [player_payload(p) for p in picks]}

    def teams(self, query: dict[str, list[str]]) -> dict[str, object]:
        bootstrap = self.bootstrap(_flag(query, "refresh"))
        totals = team_totals(bootstrap.players)
        return {"teams": [{"team": name, "points": points} for name, points in totals.items()]}


def _str(query: dict[str, list[str]], name: str) -> str | None:
    values = query.get(name)
    value = values[0].strip() if values else ""
    return value or None


def _flag(query: dict[str, list[str]], name: str) -> bool:
    return (_str(query, name) or "").lower() in {"1", "true", "yes"}


def _int(query: dict[str, list[str]], name: str, default: int) -> int:
    raw = _str(query, name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise BadRequest(f"{name} must be an integer, got {raw!r}") from exc


def _float(query: dict[str, list[str]], name: str) -> float | None:
    raw = _str(query, name)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError as exc:
        raise BadRequest(f"{name} must be a number, got {raw!r}") from exc


class DashboardHandler(BaseHTTPRequestHandler):
    """Serves the static dashboard and the JSON API."""

    api: Api = Api()
    server_version = "fpl-dashboard"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._serve_api(parsed.path, parse_qs(parsed.query))
        else:
            self._serve_static(parsed.path)

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _serve_api(self, path: str, query: dict[str, list[str]]) -> None:
        handlers = {
            "/api/status": self.api.status,
            "/api/players": self.api.players,
            "/api/differentials": self.api.differentials,
            "/api/teams": self.api.teams,
        }
        handler = handlers.get(path)
        if handler is None:
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            self._send_json(handler(query))
        except BadRequest as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except FPLError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)

    def _serve_static(self, path: str) -> None:
        name = "index.html" if path in {"", "/"} else path.lstrip("/")
        target = (STATIC_DIR / name).resolve()
        if not target.is_file() or STATIC_DIR.resolve() not in target.parents:
            self._send_bytes(b"not found", "text/plain", HTTPStatus.NOT_FOUND)
            return
        content_type = CONTENT_TYPES.get(target.suffix, "application/octet-stream")
        self._send_bytes(target.read_bytes(), f"{content_type}; charset=utf-8")

    def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status)

    def _send_bytes(
        self, body: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(host: str = "127.0.0.1", port: int = 8000, ttl: float = DEFAULT_TTL) -> None:
    DashboardHandler.api = Api(FPLClient(ttl=ttl))
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"FPL dashboard running at http://{host}:{port} (ctrl-c to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fpl-web", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--cache-ttl", type=float, default=DEFAULT_TTL)
    parser.add_argument("--open", action="store_true", help="open the dashboard in a browser")
    args = parser.parse_args(argv)
    if args.open:
        webbrowser.open(f"http://{args.host}:{args.port}")
    serve(args.host, args.port, args.cache_ttl)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
