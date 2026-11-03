# Dime (nba-odds-tracker)

**App:** https://mvpeterson0-netizen.github.io/nba-odds-tracker/ — NBA player props board, player
pages, results, games, odds, standings and injuries. Same layout as the Stix NFL tracker.

**Install on a phone:** iPhone — open the link in Safari → Share → **Add to Home Screen**.
Android — open in Chrome → ⋮ menu → **Install app** (or **Add to Home screen**). It opens full
screen with the Dime icon. Icons live in `site/icons/dime-*.png`; the original artwork is
`site/icons/dime-logo.png`.

Collects NBA games, results, standings and injuries on a schedule, with sportsbook
odds layered on once an API key is added. Runs in GitHub Actions and commits JSON
snapshots to `data/`.

## Data sources

| Data | Source | Key needed |
| --- | --- | --- |
| Today's games, yesterday's results, standings, injuries | ESPN public JSON endpoints | No |
| Player updates (notes icon): ESPN status notes, player-tagged ESPN headlines | ESPN public JSON endpoints (injuries + league news, 1 extra request per run) | No |
| Sportsbook odds (moneyline, spread, total) | [The Odds API](https://the-odds-api.com/liveapi/guides/v4/) v4 | Yes — `ODDS_API_KEY` |

ESPN's endpoints are **unofficial and undocumented**; field names can change without
notice. Parsers read every field defensively, and one failing source doesn't stop the
others. The scoreboard sometimes includes an ESPN consensus line (`espn_line`) — useful
as a placeholder, not a substitute for the odds feed.

### Player updates (notes icon)

A notes icon next to a player's name on the Board and player page opens his updates: ESPN's status
note, ESPN headlines tagged with him (last 7 days, newest 3), roster moves (on a different team's ESPN
roster than in his last box score) and role changes from his team's most recent game (4+ games played;
minutes 10+ away from his prior average, or a bench/starter switch). Red = something Dime first saw
in the last 24 hours. Built by `nba_tracker/updates.py` into `data/latest/updates.json`; first-seen
times live in `data/updates_seen.json`, headlines in `data/espn_news.json` (overwritten each run).
A news failure keeps the previous file and never stops a run. Same risks as Stix: ESPN's endpoints have
no SLA and can change or be blocked, and Disney's Terms of Use limit use to personal, noncommercial use
and bar automated access.

## College basketball (CBB)

The **NBA | CBB** toggle in the header opens a sister section: **Power 4 games** (ACC, Big Ten, Big 12, SEC) and **player
points** only, styled like the NBA side (Board, Results, player pages, Log, Guide). Code is in `cbb_tracker/`, data in
`data/cbb/`, front end in `site/cbb.js`; it runs as its own step after the NBA pull, so a college failure never stops NBA data.

- Games, rankings, conferences, box scores, rosters: ESPN men's college basketball feeds. Power 4 comes from each team's ESPN
  `conferenceId` (2 ACC, 7 Big Ten, 8 Big 12, 23 SEC). `P4_MODE` in `cbb_tracker/espn.py`: `"either"` (default; a Power 4 team
  vs a mid-major counts) or `"both"` (Power 4 vs Power 4 only).
- Player points: The Odds API `basketball_ncaab`, `player_points`, DraftKings/FanDuel, pulled **once per game, at 8 AM Central**
  (retried about hourly until the books post them, up to tip). 1 credit per game pulled (an empty answer is free). That morning
  line is the graded line; set `PROP_PULLS = ("morning", "pregame")` in `cbb_tracker/props.py` to add a pull ~1 h before tip.
- Game spreads and totals (`cbb_tracker/lines.py`): one bulk `/odds` call (`spreads,totals`; 2 credits however many games it
  returns) at **8 AM Central** and again when a Power 4 game is within ~70 min of tip. Shown beside each game, with the move
  since 8 AM; not graded. Raw rows: `data/cbb/line_captures.csv`, calls: `lines_log.csv`.
- Credits come from the **same keys** as the NBA; college never spends credits the NBA pre-game pulls need for the rest of the
  month. Books post college props for only some games; the rest show under "No points lines".
- Credit use: `python -m cbb_tracker.credits --since 2026-11-02` summarizes college spend by day and type from the pull logs,
  next to the all-keys balance drop from `data/cbb/credit_log.csv` (a balance snapshot per run when it changes).
- ESPN and the Odds API spell some schools differently. Odds events matching no ESPN game are listed in the CBB Log tab;
  add an alias in `cbb_tracker/teams.py` if a Power 4 game appears there.
- Local: `python -m cbb_tracker` (needs network), `python -m cbb_tracker.build data/cbb site/data`.

## Output

```
data/latest/<name>.json                # most recent pull, overwritten each run
data/history/<YYYY-MM-DD>/<name>.json  # daily archive (same-day runs overwrite)
```

Files: `games_today`, `results_yesterday`, `standings`, `injuries`, and `odds` (only
once the key exists). Each is `{fetched_at, source, count, ..., rows: [...]}`.
"Today" is the US Eastern date, matching how the NBA schedules games.

## Schedule

`.github/workflows/update-data.yml` runs tests, collects data, commits it, and redeploys the
site to GitHub Pages. NBA player props and game lines are pulled at **8:00 AM Central** on game day
and again **about 1 hour before each tip** (the graded line). College is different: see the College basketball section. GitHub's own schedule is
best-effort, so an external trigger should call the workflow's "Run workflow" (dispatch) API
every 30 minutes. If a source fails, the rest still publish and the run is marked
failed; the site shows a warning banner.

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


## Research thesis registry

Dime keeps a versioned NBA research registry in `data/research/theses.json`. The standing intake policy is documented in `THESIS_INTAKE.md`.

When an authorized coding assistant (ChatGPT, Claude Code, or another repo-aware agent) is used to discuss a concrete, testable NBA prop hypothesis, it should check the registry for duplicates and append a new immutable `NBA-TH-###` entry without requiring a separate “add this thesis” prompt. Registering a thesis does **not** change the live app model, thresholds, or data-collection spend by itself.

The registry is copied into the deployed site and shown at the bottom of the NBA **Results** tab. Dime currently has no authenticated admin layer, so this display is public. Do not put confidential research content in the registry until server-enforced admin access is added.
