# FPL analysis tool

Fetches live data from the official [Fantasy Premier League API](https://fantasy.premierleague.com/api/)
and ranks players by points, form and value.

The public FPL endpoints need no authentication. Responses are cached on disk
(`~/.cache/fpl-analysis`, 15 minutes by default) so repeated analysis runs don't
hammer the API; use `--refresh` to force a fresh fetch.

## Dashboard

```bash
python -m fpl.web --open        # http://127.0.0.1:8000
```

A single-page UI over the same data: summary cards, a sortable player table with
position/club/price/minutes filters, a differentials view and club points
totals, plus CSV export. Served by the standard library — no build step and no
JS dependencies. JSON endpoints: `/api/status`, `/api/players`,
`/api/differentials`, `/api/teams`.

## CLI

```bash
python -m fpl.cli status                                  # dataset + gameweek summary
python -m fpl.cli players --sort value --limit 15         # best points per £m
python -m fpl.cli players --position MID --max-cost 8.0 --available-only
python -m fpl.cli players --sort form --csv players.csv   # export for spreadsheets
python -m fpl.cli differentials --max-ownership 5         # in-form, low-owned picks
python -m fpl.cli teams                                   # total points by club
```

Sort keys: `points`, `form`, `value` (points/£m), `form_value`, `ppg`, `xgi`,
`ict`, `cost`, `ownership`.

`--refresh` and `--cache-ttl` work either before or after the subcommand:

```bash
python -m fpl.cli --refresh players --sort form
python -m fpl.cli players --sort form --refresh
```

## Library

```python
from fpl import FPLClient, Bootstrap
from fpl.analysis import rank

bootstrap = Bootstrap.from_api(FPLClient().bootstrap_static())
for player in rank(bootstrap.players, "value", 10):
    print(player.name, player.team, player.cost, player.value)
```

`FPLClient` also exposes `fixtures(event=None)`, `element_summary(player_id)`
(per-gameweek history) and `entry(entry_id)`.

## Development

```bash
pip install -r requirements-dev.txt
pytest
ruff check .
```
