"""Player box scores for finished Power 4 games, from ESPN game summaries.

data/cbb/player_games.csv      one row per player per finished game (append-only; points only)
data/cbb/boxscore_state.json   {"done": [game ids], "days_done": [dates]} so nothing is fetched twice
data/cbb/games.json            finished games with team names, used to match odds events to box scores
data/cbb/rosters.json          rosters of teams playing today (players with no box score yet)

Unlike the NBA side, college has hundreds of games a day, so a date-range request is too big. Each run
fetches the scoreboard for every day not yet fully processed (always today and yesterday), oldest first.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from nba_tracker.boxscores import parse_summary as _nba_parse_summary
from nba_tracker.http import get_json

from . import espn

log = logging.getLogger(__name__)

SEASON_START = date(2026, 11, 2)    # opening day of the 2026-27 season (ESPN's calendar starts here)
MAX_PER_RUN = 40                    # summaries fetched per run
MAX_DAYS_PER_RUN = 8                # scoreboard days fetched per run when catching up
SETTLE_DAYS = 3                     # a day this old is closed even if a game never finished (postponed)

FIELDS = ["game_id", "game_date", "start_utc", "team_id", "team", "opp", "home_away", "athlete_id", "player",
          "position", "starter", "played", "dnp_reason", "min", "pts"]


def parse_summary(summary: dict, game: dict) -> list[dict]:
    """Box score rows for one finished game (points only)."""
    return [{k: r.get(k) for k in FIELDS} for r in _nba_parse_summary(summary, game)]


class Scoreboards:
    """Memoized scoreboard fetches, so a day used by two jobs is requested once."""

    def __init__(self, fetch: Callable | None = None):
        # Looked up at call time (not bound as a default), so swapping espn.fetch_scoreboard takes effect.
        self._fetch, self._cache = fetch or (lambda d: espn.fetch_scoreboard(d)), {}

    def get(self, day: date) -> list[dict]:
        if day not in self._cache:
            self._cache[day] = espn.parse_scoreboard(self._fetch(day), day)
        return self._cache[day]


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def days_to_fetch(today: date, days_done: set[str]) -> list[date]:
    """Days still open, oldest first, always including yesterday and today."""
    out, d = [], SEASON_START
    while d <= today:
        if d >= today - timedelta(days=1) or d.isoformat() not in days_done:
            out.append(d)
        d += timedelta(days=1)
    recent = [d for d in out if d >= today - timedelta(days=1)]
    backlog = [d for d in out if d < today - timedelta(days=1)][:max(0, MAX_DAYS_PER_RUN - len(recent))]
    return backlog + recent


def update_games_index(data_dir: Path, games: list[dict]) -> None:
    path = data_dir / "games.json"
    idx = _load(path, {})
    for g in games:
        h, a = g["home"], g["away"]
        idx[g["game_id"]] = {
            "date": g.get("date"), "start": g.get("start_utc"), "home": h.get("abbr"), "away": a.get("abbr"),
            "home_name": h.get("name"), "away_name": a.get("name"), "home_id": h.get("team_id"), "away_id": a.get("team_id"),
            "hs": h.get("score"), "as": a.get("score"), "hc": h.get("conf"), "ac": a.get("conf"),
            "hr": h.get("rank"), "ar": a.get("rank"), "final": True,
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(sorted(idx.items())), indent=0))


def update_rosters(data_dir: Path, today_games: list[dict], today: date) -> int:
    """Rosters for the teams in today's Power 4 games, refreshed once a day per team."""
    path = data_dir / "rosters.json"
    rosters = _load(path, {})
    fetched = 0
    for g in today_games:
        for side in ("home", "away"):
            t = g.get(side) or {}
            tid, abbr = t.get("team_id"), t.get("abbr")
            if not tid or rosters.get(abbr, {}).get("date") == today.isoformat():
                continue
            try:
                data, _ = get_json(f"{espn.SITE}/teams/{tid}/roster")
            except Exception as e:     # one bad roster shouldn't stop the others
                log.warning("roster %s failed: %s", abbr, e)
                continue
            items = (data or {}).get("athletes") or []
            if items and isinstance(items[0], dict) and "items" in items[0]:
                items = [a for grp in items for a in grp.get("items") or []]
            rosters[abbr] = {"date": today.isoformat(), "team_id": tid, "players": [
                {"id": a.get("id"), "name": a.get("displayName") or a.get("fullName"),
                 "pos": (a.get("position") or {}).get("abbreviation")} for a in items if a.get("id")]}
            fetched += 1
    if fetched:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rosters, indent=0))
    return fetched


def run(data_dir: Path, today: date, sb: Scoreboards, today_games: list[dict]) -> dict:
    data_dir.mkdir(parents=True, exist_ok=True)
    state_path, csv_path = data_dir / "boxscore_state.json", data_dir / "player_games.csv"
    if csv_path.exists():                       # schema change: rebuild once (box scores are free to refetch)
        with csv_path.open(newline="", encoding="utf-8") as f:
            header = next(csv.reader(f), [])
        if header != FIELDS:
            csv_path.unlink()
            state_path.unlink(missing_ok=True)
    state = _load(state_path, {})
    done, days_done = set(state.get("done", [])), set(state.get("days_done", []))
    errors: list[str] = []
    try:
        rosters_fetched = update_rosters(data_dir, today_games, today)
    except Exception as e:
        log.warning("rosters failed: %s", e)
        rosters_fetched = -1

    finals, closed = [], []
    for d in days_to_fetch(today, days_done):
        try:
            games = [g for g in sb.get(d) if g["p4"]]
        except Exception as e:
            errors.append(f"scoreboard {d}: {type(e).__name__}: {e}"[:300])
            continue
        finals.extend(g for g in games if g.get("completed"))
        if d <= today - timedelta(days=2) and (all(g.get("completed") for g in games) or d <= today - timedelta(days=SETTLE_DAYS)):
            closed.append(d.isoformat())
    update_games_index(data_dir, finals)

    todo = sorted((g for g in finals if g["game_id"] not in done), key=lambda g: str(g.get("start_utc")))
    new_rows, processed, problems = [], [], []
    for g in todo[:MAX_PER_RUN]:
        try:
            summary, _ = get_json(f"{espn.SITE}/summary", {"event": g["game_id"]})
            rows = parse_summary(summary, g)
        except Exception as e:
            errors.append(f"{g['game_id']}: {type(e).__name__}: {e}"[:300])
            continue
        if not rows:
            problems.append(g["game_id"])
            continue
        for r in rows:
            r["game_date"] = g.get("date")
        new_rows.extend(rows)
        processed.append(g["game_id"])
    if new_rows:
        new = not csv_path.exists()
        with csv_path.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerows(new_rows)
    # A game ESPN still can't give us a box score for after SETTLE_DAYS is dropped rather than retried forever.
    stale = (today - timedelta(days=SETTLE_DAYS)).isoformat()
    giveup = {g["game_id"] for g in todo if g["game_id"] in problems and str(g.get("date")) <= stale}
    # A day closes only once nothing from it is still waiting for a box score.
    waiting = {g["date"] for g in todo if g["game_id"] not in processed and g["game_id"] not in giveup}
    state_path.write_text(json.dumps({"done": sorted(done | set(processed) | giveup),
                                      "days_done": sorted(days_done | (set(closed) - waiting))}, indent=0))
    log.info("cbb boxscores     %d new games (%d player rows), %d unparsed, %d still queued",
             len(processed), len(new_rows), len(problems), max(0, len(todo) - MAX_PER_RUN))
    return {"new_games": len(processed), "player_rows": len(new_rows), "unparsed": problems,
            "queued": len(todo), "errors": errors[:5], "rosters_fetched": rosters_fetched}
