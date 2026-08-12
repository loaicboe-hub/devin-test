"""Typed views over the raw FPL payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

AVAILABILITY = {
    "a": "available",
    "d": "doubtful",
    "i": "injured",
    "s": "suspended",
    "u": "unavailable",
    "n": "not in squad",
}


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


@dataclass(frozen=True)
class Team:
    id: int
    name: str
    short_name: str

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Team:
        return cls(id=raw["id"], name=raw["name"], short_name=raw["short_name"])


@dataclass(frozen=True)
class Player:
    id: int
    name: str
    full_name: str
    team: str
    position: str
    cost: float
    total_points: int
    points_per_game: float
    form: float
    minutes: int
    goals: int
    assists: int
    clean_sheets: int
    bonus: int
    expected_goal_involvements: float
    ict_index: float
    selected_by_percent: float
    status: str
    news: str

    @property
    def value(self) -> float:
        """Total points per million of cost."""
        return round(self.total_points / self.cost, 2) if self.cost else 0.0

    @property
    def form_value(self) -> float:
        """Recent form per million of cost."""
        return round(self.form / self.cost, 3) if self.cost else 0.0

    @property
    def available(self) -> bool:
        return self.status == "a"

    @classmethod
    def from_api(
        cls,
        raw: dict[str, Any],
        teams: dict[int, Team],
        positions: dict[int, str],
    ) -> Player:
        first, second = raw.get("first_name", ""), raw.get("second_name", "")
        return cls(
            id=raw["id"],
            name=raw["web_name"],
            full_name=f"{first} {second}".strip(),
            team=teams[raw["team"]].short_name,
            position=positions[raw["element_type"]],
            cost=raw["now_cost"] / 10,
            total_points=raw["total_points"],
            points_per_game=_to_float(raw.get("points_per_game")),
            form=_to_float(raw.get("form")),
            minutes=raw.get("minutes", 0),
            goals=raw.get("goals_scored", 0),
            assists=raw.get("assists", 0),
            clean_sheets=raw.get("clean_sheets", 0),
            bonus=raw.get("bonus", 0),
            expected_goal_involvements=_to_float(raw.get("expected_goal_involvements")),
            ict_index=_to_float(raw.get("ict_index")),
            selected_by_percent=_to_float(raw.get("selected_by_percent")),
            status=raw.get("status", "a"),
            news=raw.get("news", ""),
        )


@dataclass(frozen=True)
class Gameweek:
    id: int
    name: str
    deadline_time: str
    finished: bool
    is_current: bool
    is_next: bool

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Gameweek:
        return cls(
            id=raw["id"],
            name=raw["name"],
            deadline_time=raw["deadline_time"],
            finished=raw.get("finished", False),
            is_current=raw.get("is_current", False),
            is_next=raw.get("is_next", False),
        )


@dataclass(frozen=True)
class Bootstrap:
    """Parsed ``bootstrap-static`` payload."""

    players: list[Player]
    teams: dict[int, Team]
    gameweeks: list[Gameweek]

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Bootstrap:
        teams = {t["id"]: Team.from_api(t) for t in raw["teams"]}
        positions = {p["id"]: p["singular_name_short"] for p in raw["element_types"]}
        return cls(
            players=[Player.from_api(p, teams, positions) for p in raw["elements"]],
            teams=teams,
            gameweeks=[Gameweek.from_api(e) for e in raw["events"]],
        )

    @property
    def current_gameweek(self) -> Gameweek | None:
        return next((gw for gw in self.gameweeks if gw.is_current), None)

    @property
    def next_gameweek(self) -> Gameweek | None:
        return next((gw for gw in self.gameweeks if gw.is_next), None)
