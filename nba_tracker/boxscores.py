"""Player box scores from ESPN game summaries, backfilled from the start of the season.

data/player_games.csv  one row per player per finished game (append-only)
data/boxscore_state.json  finished game ids already processed
data/samples/summary_sample.json  one raw summary, saved when parsing finds no players (for debugging)
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .espn import SITE, parse_scoreboard
from .http import get_json

log = logging.getLogger(__name__)

SEASON_START = date(2026, 10, 20)   # first regular-season date to backfill from
MAX_PER_RUN = 40                    # summaries fetched per run (first run backfills, later runs top up)

FIELDS = ["game_id", "game_date", "start_utc", "team_id", "team", "opp", "home_away", "athlete_id", "player",
          "position", "starter", "played", "dnp_reason", "min", "pts", "reb", "ast", "fg3m", "fg3a", "stl", "blk", "tov"]


def _num(v: Any) -> float | None:
    try:
        return float(str(v).replace("+", ""))
    except (TypeError, ValueError):
        return None


def _made_att(v: Any) -> tuple[float | None, float | None]:
    s = str(v or "")
    if "-" in s[1:]:
        a, b = s.split("-", 1)
        return _num(a), _num(b)
    return _num(s), None


def parse_summary(summary: dict, game: dict) -> list[dict]:
    """Rows for every player listed in a finished game's box score."""
    box = (summary or {}).get("boxscore") or {}
    groups = box.get("players") or [t for t in box.get("teams") or [] if t.get("players")]
    teams = {game["home"]["team_id"]: ("home", game["home"]["abbr"], game["away"]["abbr"]),
             game["away"]["team_id"]: ("away", game["away"]["abbr"], game["home"]["abbr"])}
    rows = []
    for grp in groups:
        team = grp.get("team") or {}
        tid = str(team.get("id") or "")
        side, abbr, opp = teams.get(tid, (None, team.get("abbreviation"), None))
        stats_blocks = grp.get("statistics") or (grp.get("players") or [{}])[0].get("statistics") or []
        for st in stats_blocks:
            labels = [str(x).upper() for x in (st.get("labels") or st.get("names") or [])]
            keys = [str(x) for x in (st.get("keys") or [])]

            def col(*cands):
                for c in cands:
                    if c in labels:
                        return labels.index(c)
                    if c in keys:
                        return keys.index(c)
                return None
            i_min, i_pts, i_reb, i_ast = col("MIN", "minutes"), col("PTS", "points"), col("REB", "rebounds"), col("AST", "assists")
            i_3 = col("3PT", "threePointFieldGoalsMade-threePointFieldGoalsAttempted")
            i_stl, i_blk, i_to = col("STL", "steals"), col("BLK", "blocks"), col("TO", "turnovers")
            for a in st.get("athletes") or []:
                ath = a.get("athlete") or {}
                stats = a.get("stats") or []
                get = lambda i: stats[i] if i is not None and i < len(stats) else None
                dnp = bool(a.get("didNotPlay")) or not stats
                m3, a3 = _made_att(get(i_3))
                mins = _num(get(i_min))
                rows.append({
                    "game_id": game["game_id"], "game_date": game.get("game_date"), "start_utc": game.get("start_utc"),
                    "team_id": tid, "team": abbr, "opp": opp, "home_away": side,
                    "athlete_id": ath.get("id"), "player": ath.get("displayName"),
                    "position": (ath.get("position") or {}).get("abbreviation"),
                    "starter": bool(a.get("starter")),
                    "played": (not dnp) and (mins is None or mins > 0),
                    # ESPN can attach a reason to players who did play; keep it only for DNPs.
                    "dnp_reason": (a.get("reason") or "DNP") if dnp else "",
                    "min": mins, "pts": _num(get(i_pts)), "reb": _num(get(i_reb)), "ast": _num(get(i_ast)),
                    "fg3m": m3, "fg3a": a3,
                    "stl": _num(get(i_stl)), "blk": _num(get(i_blk)), "tov": _num(get(i_to)),
                })
    return rows


def finished_games(today: date) -> list[dict]:
    """All finished games from SEASON_START through yesterday (and today's finals)."""
    try:
        data, _ = get_json(f"{SITE}/scoreboard", {"dates": f"{SEASON_START:%Y%m%d}-{today:%Y%m%d}", "limit": 1000})
        games = parse_scoreboard(data)
    except Exception as e:  # fall back to one request per date
        log.warning("scoreboard date range failed (%s); fetching day by day", e)
        games, d = [], SEASON_START
        while d <= today:
            data, _ = get_json(f"{SITE}/scoreboard", {"dates": f"{d:%Y%m%d}"})
            games.extend(parse_scoreboard(data))
            d += timedelta(days=1)
    out = []
    for g in games:
        if g.get("completed"):
            # NBA dates are Eastern; derive from the UTC start (ET = UTC-4/5; -5h is safe for night games).
            from datetime import datetime
            try:
                start = datetime.fromisoformat(str(g["start_utc"]).replace("Z", "+00:00"))
                g["game_date"] = (start - timedelta(hours=5)).date().isoformat()
            except (KeyError, ValueError):
                g["game_date"] = None
            out.append(g)
    return out


def _update_games_index(data_dir: Path, games: list[dict]) -> None:
    """data/games.json: finished games with team names, used to match odds events to box scores."""
    path = data_dir / "games.json"
    try:
        idx = json.loads(path.read_text())
    except Exception:
        idx = {}
    for g in games:
        idx[g["game_id"]] = {
            "date": g.get("game_date"), "start": g.get("start_utc"),
            "home": g["home"].get("abbr"), "away": g["away"].get("abbr"),
            "home_name": g["home"].get("name"), "away_name": g["away"].get("name"),
            "home_id": g["home"].get("team_id"), "away_id": g["away"].get("team_id"),
            "hs": g["home"].get("score"), "as": g["away"].get("score"), "final": True,
        }
    path.write_text(json.dumps(dict(sorted(idx.items())), indent=0))


def update_rosters(data_dir: Path, today_games: list[dict], today: date) -> int:
    """data/rosters.json: rosters for teams playing today, refreshed once a day per team.
    Lets players with no box score yet (first game of the season, new signings) be matched."""
    path = data_dir / "rosters.json"
    try:
        rosters = json.loads(path.read_text())
    except Exception:
        rosters = {}
    fetched = 0
    for g in today_games:
        for side in ("home", "away"):
            t = g.get(side) or {}
            tid, abbr = t.get("team_id"), t.get("abbr")
            if not tid or rosters.get(abbr, {}).get("date") == today.isoformat():
                continue
            data, _ = get_json(f"{SITE}/teams/{tid}/roster")
            items = (data or {}).get("athletes") or []
            if items and isinstance(items[0], dict) and "items" in items[0]:   # grouped by position
                items = [a for grp in items for a in grp.get("items") or []]
            rosters[abbr] = {"date": today.isoformat(), "team_id": tid, "players": [
                {"id": a.get("id"), "name": a.get("displayName") or a.get("fullName"),
                 "pos": (a.get("position") or {}).get("abbreviation")} for a in items if a.get("id")]}
            fetched += 1
    if fetched:
        path.write_text(json.dumps(rosters, indent=0))
    return fetched


def run(data_dir: Path, today: date) -> dict:
    state_path = data_dir / "boxscore_state.json"
    # Schema change (new columns): rebuild the file from ESPN once. Box scores are free to re-fetch.
    csv_path = data_dir / "player_games.csv"
    if csv_path.exists():
        with csv_path.open(newline="", encoding="utf-8") as f:
            header = next(csv.reader(f), [])
        if header != FIELDS:
            log.info("player_games.csv columns changed; rebuilding from ESPN")
            csv_path.unlink()
            state_path.unlink(missing_ok=True)
    try:
        done = set(json.loads(state_path.read_text())["done"])
    except Exception:
        done = set()
    try:
        today_games = json.loads((data_dir / "latest" / "games_today.json").read_text())["rows"]
        rosters_fetched = update_rosters(data_dir, today_games, today)
    except Exception as e:
        log.warning("rosters failed: %s", e)
        rosters_fetched = -1
    finals = finished_games(today)
    _update_games_index(data_dir, finals)
    games = [g for g in finals if g["game_id"] not in done]
    games.sort(key=lambda g: str(g.get("start_utc")))
    new_rows, processed, problems = [], [], []
    errors = []
    for g in games[:MAX_PER_RUN]:
        try:
            summary, _ = get_json(f"{SITE}/summary", {"event": g["game_id"]})
            rows = parse_summary(summary, g)
        except Exception as e:
            errors.append(f"{g['game_id']}: {type(e).__name__}: {e}"[:300])
            continue
        if not rows:
            problems.append(g["game_id"])
            sample = data_dir / "samples" / "summary_sample.json"
            if not sample.exists():
                sample.parent.mkdir(parents=True, exist_ok=True)
                slim = {k: v for k, v in (summary or {}).items() if k in ("boxscore", "header", "gameInfo")}
                sample.write_text(json.dumps(slim, indent=1)[:2_000_000])
            continue
        new_rows.extend(rows)
        processed.append(g["game_id"])
    if new_rows:
        path = data_dir / "player_games.csv"
        new = not path.exists()
        with path.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerows(new_rows)
    if processed:
        state_path.write_text(json.dumps({"done": sorted(done | set(processed))}, indent=0))
    log.info("boxscores         %d new games (%d player rows), %d unparsed, %d still queued",
             len(processed), len(new_rows), len(problems), max(0, len(games) - MAX_PER_RUN))
    return {"new_games": len(processed), "player_rows": len(new_rows), "unparsed": problems,
            "queued": len(games), "errors": errors[:5], "rosters_fetched": rosters_fetched}
