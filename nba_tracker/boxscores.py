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
          "position", "starter", "played", "dnp_reason", "min", "pts", "reb", "ast", "fg3m", "fg3a"]


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
                    "dnp_reason": a.get("reason") or ("DNP" if dnp else ""),
                    "min": mins, "pts": _num(get(i_pts)), "reb": _num(get(i_reb)), "ast": _num(get(i_ast)),
                    "fg3m": m3, "fg3a": a3,
                })
    return rows


def finished_games(today: date) -> list[dict]:
    """All finished games from SEASON_START through yesterday (and today's finals)."""
    data, _ = get_json(f"{SITE}/scoreboard", {"dates": f"{SEASON_START:%Y%m%d}-{today:%Y%m%d}", "limit": 1000})
    games = parse_scoreboard(data)
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


def run(data_dir: Path, today: date) -> dict:
    state_path = data_dir / "boxscore_state.json"
    try:
        done = set(json.loads(state_path.read_text())["done"])
    except Exception:
        done = set()
    games = [g for g in finished_games(today) if g["game_id"] not in done]
    games.sort(key=lambda g: str(g.get("start_utc")))
    new_rows, processed, problems = [], [], []
    for g in games[:MAX_PER_RUN]:
        summary, _ = get_json(f"{SITE}/summary", {"event": g["game_id"]})
        rows = parse_summary(summary, g)
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
    return {"new_games": len(processed), "player_rows": len(new_rows), "unparsed": problems}
