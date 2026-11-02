"""College basketball (men's) from ESPN's public JSON endpoints, filtered to the Power 4.

Same caveats as the NBA side: unofficial, undocumented, can change without notice. Every field is read
defensively.

Power 4 = ACC, Big Ten, Big 12, SEC. The scoreboard tags each team with its conference
(team.conferenceId), using ESPN's group ids (checked against ESPN's own conference list).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from nba_tracker.espn import _first, parse_scoreboard as _nba_scoreboard
from nba_tracker.http import get_json

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball"
ALL_D1 = "50"          # ESPN group id for every Division I game (the default scoreboard is only featured games)

P4_CONFERENCES = {"2": "ACC", "7": "Big Ten", "8": "Big 12", "23": "SEC"}

# "either": a game counts when at least one team is Power 4 (includes Power 4 vs mid-major games).
# "both":   only Power 4 vs Power 4. One word to change; everything downstream follows.
P4_MODE = "either"


def fetch_scoreboard(day: date) -> Any:
    data, _ = get_json(f"{SITE}/scoreboard", {"dates": day.strftime("%Y%m%d"), "groups": ALL_D1, "limit": 400})
    return data


def _extra_side(competitor: dict) -> dict:
    team = competitor.get("team") or {}
    cid = str(team.get("conferenceId") or "")
    rank = (competitor.get("curatedRank") or {}).get("current")
    return {
        "conf_id": cid or None,
        "conf": P4_CONFERENCES.get(cid),           # None for everyone outside the Power 4
        "rank": rank if isinstance(rank, int) and 1 <= rank <= 25 else None,   # ESPN uses 99 for unranked
    }


def is_p4(game: dict, mode: str | None = None) -> bool:
    mode = mode or P4_MODE
    h, a = bool((game.get("home") or {}).get("conf")), bool((game.get("away") or {}).get("conf"))
    return (h and a) if mode == "both" else (h or a)


def parse_scoreboard(raw: Any, day: date | str | None = None) -> list[dict]:
    """One row per game (every Division I game), each side tagged with conference and rank, plus `p4`.

    Rows reuse the NBA parser, so they have the same shape (game_id, start_utc, state, completed, home/away
    with team_id/abbr/name/score/record, ...), plus `date` (the scoreboard day ESPN listed it under)."""
    out = []
    for ev in (raw or {}).get("events") or []:
        rows = _nba_scoreboard({"events": [ev]})
        if not rows:
            continue
        g = rows[0]
        comp = _first(ev.get("competitions"))
        for c in comp.get("competitors") or []:
            side = g.get(c.get("homeAway"))
            if side is None:
                continue
            team = c.get("team") or {}
            side.update(_extra_side(c))
            side["loc"], side["nick"] = team.get("location"), team.get("name")
        g["date"] = day.isoformat() if isinstance(day, date) else day
        g["p4"] = is_p4(g)
        out.append(g)
    return out


def p4_only(games: list[dict]) -> list[dict]:
    return [g for g in games if g.get("p4")]
