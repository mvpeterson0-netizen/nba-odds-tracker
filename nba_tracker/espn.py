"""NBA stats from ESPN's public (unofficial, keyless) JSON endpoints.

These endpoints are undocumented by ESPN and can change without notice, so every
parser here reads fields defensively and never assumes a key exists.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from .http import get_json

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
# Standings live under /apis/v2 — the /apis/site/v2 path only returns a stub.
STANDINGS_URL = "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings"


# ---------------------------------------------------------------- fetchers

def fetch_scoreboard(day: date) -> Any:
    data, _ = get_json(f"{SITE}/scoreboard", {"dates": day.strftime("%Y%m%d")})
    return data


def fetch_standings() -> Any:
    data, _ = get_json(STANDINGS_URL)
    return data


def fetch_injuries() -> Any:
    data, _ = get_json(f"{SITE}/injuries")
    return data


def fetch_news() -> Any:
    """League news (latest 100 items). Used only for headlines ESPN tags with a player."""
    data, _ = get_json(f"{SITE}/news", {"limit": 100})
    return data


# ---------------------------------------------------------------- helpers

_ID_RE = re.compile(r"/id/(\d+)")


def athlete_id(ath: dict) -> str | None:
    """ESPN athlete id: the "id" field when present, else parsed from the athlete's links."""
    if ath.get("id"):
        return str(ath["id"])
    for ln in ath.get("links") or []:
        m = _ID_RE.search(str(ln.get("href") or ""))
        if m:
            return m.group(1)
    return None


def player_news_link(ath: dict) -> str | None:
    """ESPN's player news page from the athlete's links (rel includes "news" and "desktop")."""
    for ln in ath.get("links") or []:
        rel = ln.get("rel") or []
        if "news" in rel and "desktop" in rel and str(ln.get("href") or "").startswith("https://"):
            return ln["href"]
    return None

def _first(seq: Any) -> dict:
    return seq[0] if isinstance(seq, list) and seq and isinstance(seq[0], dict) else {}


def _to_int(val: Any) -> int | None:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


def _record(competitor: dict, name: str) -> str | None:
    for rec in competitor.get("records") or []:
        if rec.get("name") == name or rec.get("type") == name:
            return rec.get("summary")
    return None


def _team_side(competitor: dict) -> dict:
    team = competitor.get("team") or {}
    # Score/winner usually sit on the competitor, but tolerate them on the team.
    score = competitor.get("score", team.get("score"))
    winner = competitor.get("winner", team.get("winner"))
    leaders = {}
    for cat in competitor.get("leaders") or []:
        top = _first(cat.get("leaders"))
        if top:
            leaders[cat.get("name")] = {
                "player": (top.get("athlete") or {}).get("displayName"),
                "value": top.get("displayValue"),
            }
    return {
        "team_id": team.get("id"),
        "abbr": team.get("abbreviation"),
        "name": team.get("displayName"),
        "score": _to_int(score),
        "winner": winner,
        "record": _record(competitor, "overall") or _record(competitor, "total"),
        "home_record": _record(competitor, "home"),
        "away_record": _record(competitor, "road") or _record(competitor, "away"),
        "leaders": leaders or None,
    }


# ---------------------------------------------------------------- parsers

def parse_scoreboard(raw: Any) -> list[dict]:
    """Flatten a scoreboard payload into one row per game."""
    games = []
    for ev in (raw or {}).get("events") or []:
        comp = _first(ev.get("competitions"))
        competitors = comp.get("competitors") or []
        home = next((c for c in competitors if c.get("homeAway") == "home"), {})
        away = next((c for c in competitors if c.get("homeAway") == "away"), {})
        status = (ev.get("status") or comp.get("status") or {})
        stype = status.get("type") or {}
        venue = comp.get("venue") or {}
        # ESPN sometimes embeds a consensus line on the scoreboard. It's a free
        # placeholder until the paid odds feed is wired up — not a replacement.
        line = _first(comp.get("odds"))
        broadcasts = []
        for b in comp.get("broadcasts") or []:
            names = b.get("names")
            if names:
                broadcasts.extend(names)
            elif (b.get("media") or {}).get("shortName"):
                broadcasts.append(b["media"]["shortName"])
        games.append({
            "game_id": ev.get("id"),
            "start_utc": ev.get("date"),
            "short_name": ev.get("shortName"),
            "state": stype.get("state"),          # pre / in / post
            "status": stype.get("shortDetail") or stype.get("description"),
            "completed": stype.get("completed"),
            "period": status.get("period"),
            "clock": status.get("displayClock"),
            "venue": venue.get("fullName"),
            "neutral_site": comp.get("neutralSite"),
            "broadcasts": broadcasts or None,
            "home": _team_side(home),
            "away": _team_side(away),
            "espn_line": {
                "provider": (line.get("provider") or {}).get("name"),
                "details": line.get("details"),
                "spread": line.get("spread"),
                "over_under": line.get("overUnder"),
            } if line else None,
        })
    return games


def parse_standings(raw: Any) -> list[dict]:
    """One row per team. Every stat ESPN returns is kept, keyed by its name."""
    rows = []

    def walk(node: dict, conference: str | None) -> None:
        name = node.get("name") or node.get("abbreviation")
        entries = (node.get("standings") or {}).get("entries") or []
        for e in entries:
            team = e.get("team") or {}
            stats = {}
            for s in e.get("stats") or []:
                key = s.get("name") or s.get("type") or s.get("abbreviation")
                if key:
                    stats[key] = s.get("value", s.get("displayValue"))
                    if "displayValue" in s and s.get("value") is not None:
                        stats[f"{key}_display"] = s["displayValue"]
            rows.append({
                "conference": conference or name,
                "team_id": team.get("id"),
                "abbr": team.get("abbreviation"),
                "name": team.get("displayName"),
                "note": (e.get("note") or {}).get("description"),
                "stats": stats,
            })
        for child in node.get("children") or []:
            walk(child, conference or child.get("name"))

    for child in (raw or {}).get("children") or []:
        walk(child, child.get("name"))
    return rows


def parse_injuries(raw: Any) -> list[dict]:
    """One row per injured player."""
    rows = []
    for group in (raw or {}).get("injuries") or []:
        # Team info appears either nested under "team" or at the group's top level.
        team = group.get("team") or group
        for inj in group.get("injuries") or []:
            ath = inj.get("athlete") or {}
            details = inj.get("details") or {}
            ath_team = ath.get("team") or {}
            rows.append({
                "team_id": team.get("id") or ath_team.get("id"),
                "team": team.get("displayName") or ath_team.get("displayName"),
                "team_abbr": team.get("abbreviation") or ath_team.get("abbreviation"),
                "player_id": athlete_id(ath),
                "player": ath.get("displayName"),
                "position": (ath.get("position") or {}).get("abbreviation"),
                "status": inj.get("status") or (inj.get("type") or {}).get("description"),
                "injury": details.get("type") or (inj.get("type") or {}).get("name"),
                "return_date": details.get("returnDate"),
                "comment": inj.get("shortComment"),
                "updated": inj.get("date"),
                "url": player_news_link(ath),
            })
    return rows


def parse_news(raw: Any) -> dict[str, list[dict]]:
    """Headlines ESPN tags with a player: {athlete id: [{headline, date, url}]}. Untagged items are dropped."""
    out: dict[str, list[dict]] = {}
    for a in (raw or {}).get("articles") or []:
        head = str(a.get("headline") or "").strip()
        url = ((a.get("links") or {}).get("web") or {}).get("href") or ""
        if not head or not str(url).startswith("https://"):
            continue
        ids = {str(c.get("athleteId") or (c.get("athlete") or {}).get("id"))
               for c in a.get("categories") or []
               if c.get("type") == "athlete" and (c.get("athleteId") or (c.get("athlete") or {}).get("id"))}
        for aid in sorted(ids):
            out.setdefault(aid, []).append({"headline": head, "date": a.get("published") or "", "url": url})
    return out
