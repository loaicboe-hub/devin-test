import json
import time
from pathlib import Path

import pytest

from fpl.analysis import differentials, filter_players, rank, team_totals
from fpl.client import FPLClient, FPLError
from fpl.models import Bootstrap

FIXTURE = json.loads((Path(__file__).parent / "data" / "bootstrap.json").read_text())


@pytest.fixture
def bootstrap() -> Bootstrap:
    return Bootstrap.from_api(FIXTURE)


def test_bootstrap_parses_players_teams_and_gameweeks(bootstrap):
    assert len(bootstrap.players) == 4
    assert bootstrap.teams[1].short_name == "ARS"
    assert bootstrap.current_gameweek.id == 1
    assert bootstrap.next_gameweek.id == 2


def test_player_fields_are_normalised(bootstrap):
    saka = next(p for p in bootstrap.players if p.name == "Saka")
    assert saka.cost == 10.0
    assert saka.position == "MID"
    assert saka.team == "ARS"
    assert saka.value == 12.0
    assert saka.available


def test_player_handles_missing_numeric_values(bootstrap):
    keeper = next(p for p in bootstrap.players if p.name == "Raya")
    assert keeper.form == 0.0
    assert keeper.expected_goal_involvements == 0.0


def test_filter_players(bootstrap):
    mids = filter_players(bootstrap.players, position="MID")
    assert [p.name for p in mids] == ["Saka", "Palmer"]
    cheap = filter_players(bootstrap.players, max_cost=6.0)
    assert [p.name for p in cheap] == ["Raya"]
    fit = filter_players(bootstrap.players, available_only=True)
    assert "Watkins" not in [p.name for p in fit]


def test_rank_by_value_and_points(bootstrap):
    assert [p.name for p in rank(bootstrap.players, "points", 2)] == ["Saka", "Palmer"]
    assert rank(bootstrap.players, "value", 1)[0].name == "Saka"
    with pytest.raises(ValueError):
        rank(bootstrap.players, "nonsense")


def test_differentials_exclude_popular_and_unavailable(bootstrap):
    names = [p.name for p in differentials(bootstrap.players, max_ownership=20.0)]
    assert "Saka" not in names
    assert "Watkins" not in names
    assert names[0] == "Palmer"


def test_team_totals_sorted_desc(bootstrap):
    assert list(team_totals(bootstrap.players).items())[0] == ("ARS", 120)


def test_client_uses_cache_until_ttl_expires(tmp_path, monkeypatch):
    client = FPLClient(cache_dir=tmp_path, ttl=60)
    calls = []

    def fake_fetch(url):
        calls.append(url)
        return {"elements": []}

    monkeypatch.setattr(client, "_fetch", fake_fetch)
    client.bootstrap_static()
    client.bootstrap_static()
    assert len(calls) == 1

    client.bootstrap_static(refresh=True)
    assert len(calls) == 2

    cached = tmp_path / "bootstrap-static.json"
    stale = time.time() - 120
    import os

    os.utime(cached, (stale, stale))
    client.bootstrap_static()
    assert len(calls) == 3


def test_client_raises_after_retries(tmp_path, monkeypatch):
    client = FPLClient(cache_dir=tmp_path, retries=2)
    monkeypatch.setattr("fpl.client.time.sleep", lambda _: None)

    def boom(*_args, **_kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr("fpl.client.urlopen", boom)
    with pytest.raises(FPLError):
        client.fixtures()
