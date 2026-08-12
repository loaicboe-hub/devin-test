"""Analysis helpers over parsed FPL data."""

from __future__ import annotations

from collections.abc import Iterable

from .models import Player

SORT_KEYS = {
    "points": lambda p: p.total_points,
    "form": lambda p: p.form,
    "value": lambda p: p.value,
    "form_value": lambda p: p.form_value,
    "ppg": lambda p: p.points_per_game,
    "xgi": lambda p: p.expected_goal_involvements,
    "ict": lambda p: p.ict_index,
    "cost": lambda p: p.cost,
    "ownership": lambda p: p.selected_by_percent,
}


def filter_players(
    players: Iterable[Player],
    position: str | None = None,
    team: str | None = None,
    max_cost: float | None = None,
    min_minutes: int = 0,
    available_only: bool = False,
) -> list[Player]:
    result = []
    for player in players:
        if position and player.position.upper() != position.upper():
            continue
        if team and player.team.upper() != team.upper():
            continue
        if max_cost is not None and player.cost > max_cost:
            continue
        if player.minutes < min_minutes:
            continue
        if available_only and not player.available:
            continue
        result.append(player)
    return result


def rank(players: Iterable[Player], key: str = "points", limit: int = 10) -> list[Player]:
    """Return the ``limit`` best players by one of :data:`SORT_KEYS`."""
    if key not in SORT_KEYS:
        raise ValueError(f"unknown sort key {key!r}; expected one of {sorted(SORT_KEYS)}")
    scorer = SORT_KEYS[key]
    return sorted(players, key=lambda p: (scorer(p), p.total_points), reverse=True)[:limit]


def differentials(
    players: Iterable[Player], max_ownership: float = 10.0, limit: int = 10
) -> list[Player]:
    """In-form, low-owned players."""
    pool = [p for p in players if p.selected_by_percent <= max_ownership and p.available]
    return rank(pool, "form", limit)


def team_totals(players: Iterable[Player]) -> dict[str, int]:
    """Total FPL points contributed by each club's players, best first."""
    totals: dict[str, int] = {}
    for player in players:
        totals[player.team] = totals.get(player.team, 0) + player.total_points
    return dict(sorted(totals.items(), key=lambda item: item[1], reverse=True))
