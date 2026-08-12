"""Command line interface for fetching and analysing FPL data."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .analysis import SORT_KEYS, differentials, filter_players, rank, team_totals
from .client import DEFAULT_TTL, FPLClient, FPLError
from .models import Bootstrap, Player

COLUMNS = [
    ("name", "Player", 18),
    ("team", "Team", 5),
    ("position", "Pos", 4),
    ("cost", "£m", 5),
    ("total_points", "Pts", 5),
    ("form", "Form", 5),
    ("value", "Pts/£m", 7),
    ("selected_by_percent", "Own%", 6),
]


def _row(player: Player) -> list[str]:
    values = asdict(player) | {"value": player.value}
    return [f"{values[field]}".ljust(width) for field, _, width in COLUMNS]


def print_table(players: list[Player]) -> None:
    header = [title.ljust(width) for _, title, width in COLUMNS]
    print(" ".join(header))
    print("-" * (sum(width for _, _, width in COLUMNS) + len(COLUMNS) - 1))
    for player in players:
        print(" ".join(_row(player)))


def write_csv(players: list[Player], path: Path) -> None:
    fields = list(asdict(players[0]).keys()) + ["value", "form_value"] if players else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for player in players:
            writer.writerow(
                asdict(player) | {"value": player.value, "form_value": player.form_value}
            )


def load_bootstrap(args: argparse.Namespace) -> Bootstrap:
    client = FPLClient(ttl=args.cache_ttl)
    return Bootstrap.from_api(client.bootstrap_static(refresh=args.refresh))


def cmd_players(args: argparse.Namespace) -> int:
    bootstrap = load_bootstrap(args)
    players = filter_players(
        bootstrap.players,
        position=args.position,
        team=args.team,
        max_cost=args.max_cost,
        min_minutes=args.min_minutes,
        available_only=args.available_only,
    )
    selected = rank(players, args.sort, args.limit)
    if args.csv:
        write_csv(selected, Path(args.csv))
        print(f"wrote {len(selected)} players to {args.csv}")
    elif args.json:
        print(json.dumps([asdict(p) | {"value": p.value} for p in selected], indent=2))
    else:
        print_table(selected)
    return 0


def cmd_differentials(args: argparse.Namespace) -> int:
    bootstrap = load_bootstrap(args)
    print_table(differentials(bootstrap.players, args.max_ownership, args.limit))
    return 0


def cmd_teams(args: argparse.Namespace) -> int:
    bootstrap = load_bootstrap(args)
    for team, points in team_totals(bootstrap.players).items():
        print(f"{team:<5} {points:>5}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    bootstrap = load_bootstrap(args)
    current, upcoming = bootstrap.current_gameweek, bootstrap.next_gameweek
    print(f"players: {len(bootstrap.players)}   teams: {len(bootstrap.teams)}")
    print(f"current: {current.name if current else 'pre-season'}")
    if upcoming:
        print(f"next:    {upcoming.name} (deadline {upcoming.deadline_time})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fpl", description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="bypass the local cache")
    parser.add_argument(
        "--cache-ttl", type=float, default=DEFAULT_TTL, help="cache lifetime in seconds"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    players = subparsers.add_parser("players", help="rank players")
    players.add_argument("--position", choices=["GKP", "DEF", "MID", "FWD"])
    players.add_argument("--team", help="team short name, e.g. ARS")
    players.add_argument("--max-cost", type=float, help="maximum price in £m")
    players.add_argument("--min-minutes", type=int, default=0)
    players.add_argument("--available-only", action="store_true")
    players.add_argument("--sort", choices=sorted(SORT_KEYS), default="points")
    players.add_argument("--limit", type=int, default=20)
    players.add_argument("--csv", help="write results to a CSV file")
    players.add_argument("--json", action="store_true")
    players.set_defaults(func=cmd_players)

    diff = subparsers.add_parser("differentials", help="in-form, low-owned players")
    diff.add_argument("--max-ownership", type=float, default=10.0)
    diff.add_argument("--limit", type=int, default=20)
    diff.set_defaults(func=cmd_differentials)

    teams = subparsers.add_parser("teams", help="total points by club")
    teams.set_defaults(func=cmd_teams)

    status = subparsers.add_parser("status", help="dataset and gameweek summary")
    status.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except FPLError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
