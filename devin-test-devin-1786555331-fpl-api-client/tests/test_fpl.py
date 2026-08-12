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


@pytest.fixture
def cli(monkeypatch):
    from fpl import cli as cli_module

    monkeypatch.setattr(cli_module, "load_bootstrap", lambda _args: Bootstrap.from_api(FIXTURE))
    return cli_module


def test_cli_cache_flags_work_after_the_subcommand(cli):
    args = cli.build_parser().parse_args(["players", "--refresh", "--cache-ttl", "0"])
    assert args.refresh is True
    assert args.cache_ttl == 0


def test_cli_cache_flags_before_subcommand_are_not_overwritten(cli):
    args = cli.build_parser().parse_args(["--refresh", "players"])
    assert args.refresh is True


def test_cli_rejects_non_positive_limit(cli):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["players", "--limit", "-5"])


def test_cli_rejects_csv_and_json_together(cli):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["players", "--csv", "out.csv", "--json"])


def test_cli_reports_unknown_team(cli, capsys):
    assert cli.main(["players", "--team", "ZZZ"]) == 1
    assert "unknown team" in capsys.readouterr().err


def test_cli_csv_has_full_header_when_no_players_match(cli, tmp_path):
    out = tmp_path / "empty.csv"
    assert cli.main(["players", "--max-cost", "0.1", "--csv", str(out)]) == 0
    header = out.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert header[:2] == ["id", "name"]
    assert header[-2:] == ["value", "form_value"]


def test_cli_ignores_broken_downstream_pipe(cli, monkeypatch):
    def explode(*_args, **_kwargs):
        raise BrokenPipeError

    monkeypatch.setattr(cli, "print_table", explode)
    assert cli.main(["players"]) == 0


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
