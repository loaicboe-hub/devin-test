import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from fpl.web import Api, BadRequest, DashboardHandler

FIXTURE = json.loads((Path(__file__).parent / "data" / "bootstrap.json").read_text())


class StubClient:
    def __init__(self):
        self.calls = []

    def bootstrap_static(self, refresh=False):
        self.calls.append(refresh)
        return FIXTURE


@pytest.fixture
def api():
    return Api(StubClient())


def test_status_lists_filter_options(api):
    status = api.status({})
    assert status["player_count"] == 4
    assert status["teams"] == ["ARS", "AVL", "CHE"]
    assert status["next_gameweek"] == "Gameweek 2"


def test_players_applies_filters_and_sort(api):
    payload = api.players({"position": ["MID"], "sort": ["value"], "limit": ["1"]})
    assert payload["total"] == 2
    assert [p["name"] for p in payload["players"]] == ["Saka"]
    assert payload["players"][0]["value"] == 12.0


def test_players_rejects_bad_input(api):
    for params in ({"team": ["ZZZ"]}, {"position": ["XXX"]}, {"sort": ["nope"]}, {"limit": ["0"]}):
        with pytest.raises(BadRequest):
            api.players(params)
    with pytest.raises(BadRequest):
        api.players({"max_cost": ["cheap"]})


def test_differentials_and_teams(api):
    picks = api.differentials({"max_ownership": ["20"]})["players"]
    assert [p["name"] for p in picks] == ["Palmer", "Raya"]
    assert api.teams({})["teams"][0] == {"team": "ARS", "points": 120}


def test_refresh_flag_is_forwarded():
    client = StubClient()
    Api(client).players({"refresh": ["1"]})
    assert client.calls == [True]


@pytest.fixture
def server():
    DashboardHandler.api = Api(StubClient())
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def test_server_serves_dashboard_and_api(server):
    with urlopen(f"{server}/") as response:
        assert response.status == 200
        assert b"FPL Analysis" in response.read()
    for asset in ("/app.css", "/app.js"):
        with urlopen(f"{server}{asset}") as response:
            assert response.status == 200
    with urlopen(f"{server}/api/players?limit=2") as response:
        assert len(json.loads(response.read())["players"]) == 2


def test_server_returns_errors_as_json(server):
    with pytest.raises(HTTPError) as bad_request:
        urlopen(f"{server}/api/players?team=ZZZ")
    assert bad_request.value.code == 400
    assert "unknown team" in json.loads(bad_request.value.read())["error"]

    with pytest.raises(HTTPError) as not_found:
        urlopen(f"{server}/api/nope")
    assert not_found.value.code == 404


def test_server_rejects_path_traversal(server):
    with pytest.raises(HTTPError) as exc:
        urlopen(f"{server}/../pyproject.toml")
    assert exc.value.code == 404
