# nba-odds-tracker

Collects NBA games, results, standings and injuries on a schedule, with sportsbook
odds layered on once an API key is added. Runs in GitHub Actions and commits JSON
snapshots to `data/`.

## Data sources

| Data | Source | Key needed |
| --- | --- | --- |
| Today's games, yesterday's results, standings, injuries | ESPN public JSON endpoints | No |
| Sportsbook odds (moneyline, spread, total) | [The Odds API](https://the-odds-api.com/liveapi/guides/v4/) v4 | Yes — `ODDS_API_KEY` |

ESPN's endpoints are **unofficial and undocumented**; field names can change without
notice. Parsers read every field defensively, and one failing source doesn't stop the
others. The scoreboard sometimes includes an ESPN consensus line (`espn_line`) — useful
as a placeholder, not a substitute for the odds feed.

## Output

```
data/latest/<name>.json                # most recent pull, overwritten each run
data/history/<YYYY-MM-DD>/<name>.json  # daily archive (same-day runs overwrite)
```

Files: `games_today`, `results_yesterday`, `standings`, `injuries`, and `odds` (only
once the key exists). Each is `{fetched_at, source, count, ..., rows: [...]}`.
"Today" is the US Eastern date, matching how the NBA schedules games.

## Schedule

`.github/workflows/update-data.yml` runs tests, then collects at 14:40 and 22:40 UTC
daily, on manual **Run workflow**, and on pushes that change code.

## Adding the odds key

1. Repo → **Settings → Secrets and variables → Actions → New repository secret**
2. Name: `ODDS_API_KEY`, value: your key
3. Next run picks it up automatically — no code change.

Each odds call spends quota (roughly markets × regions; 3 markets × 1 region here).
The quota left is saved in `data/latest/odds.json` under `quota`.

## Run locally

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
python -m nba_tracker                     # today
python -m nba_tracker --date 2026-10-21   # a specific date
ODDS_API_KEY=xxx python -m nba_tracker    # include odds
```
