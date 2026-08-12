"""Command line interface for fetching and analysing FPL data."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import asdict, fields
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
    columns = [f.name for f in fields(Player)] + ["value", "form_value"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
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
    if args.team:
        known = {team.short_name.upper() for team in bootstrap.teams.values()}
        if args.team.upper() not in known:
            raise UsageError(f"unknown team {args.team!r}; expected one of {sorted(known)}")
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


class UsageError(Exception):
    """Raised for invalid input that argparse cannot validate on its own."""


def add_cache_flags(parser: argparse.ArgumentParser, subcommand: bool) -> None:
    """Add the cache flags so they work before or after the subcommand.

    Subcommand copies suppress their defaults so they don't overwrite a value
    that was already given before the subcommand.
    """
    refresh_default = argparse.SUPPRESS if subcommand else False
    ttl_default = argparse.SUPPRESS if subcommand else DEFAULT_TTL
    parser.add_argument(
        "--refresh", action="store_true", default=refresh_default, help="bypass the local cache"
    )
    parser.add_argument(
        "--cache-ttl", type=float, default=ttl_default, help="cache lifetime in seconds"
    )


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError(f"expected a positive integer, got {value!r}")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fpl", description=__doc__)
    add_cache_flags(parser, subcommand=False)
    subparsers = parser.add_subparsers(dest="command", required=True)

    players = subparsers.add_parser("players", help="rank players")
    players.add_argument("--position", choices=["GKP", "DEF", "MID", "FWD"])
    players.add_argument("--team", help="team short name, e.g. ARS")
    players.add_argument("--max-cost", type=float, help="maximum price in £m")
    players.add_argument("--min-minutes", type=int, default=0)
    players.add_argument("--available-only", action="store_true")
    players.add_argument("--sort", choices=sorted(SORT_KEYS), default="points")
    players.add_argument("--limit", type=positive_int, default=20)
    output = players.add_mutually_exclusive_group()
    output.add_argument("--csv", help="write results to a CSV file")
    output.add_argument("--json", action="store_true")
    players.set_defaults(func=cmd_players)

    diff = subparsers.add_parser("differentials", help="in-form, low-owned players")
    diff.add_argument("--max-ownership", type=float, default=10.0)
    diff.add_argument("--limit", type=positive_int, default=20)
    diff.set_defaults(func=cmd_differentials)

    teams = subparsers.add_parser("teams", help="total points by club")
    teams.set_defaults(func=cmd_teams)

    status = subparsers.add_parser("status", help="dataset and gameweek summary")
    status.set_defaults(func=cmd_status)

    for subparser in (players, diff, teams, status):
        add_cache_flags(subparser, subcommand=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (FPLError, UsageError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        # A closed downstream pipe (e.g. `| head`) is not an error; swallow the
        # flush of the already-dead stream on interpreter shutdown.
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
