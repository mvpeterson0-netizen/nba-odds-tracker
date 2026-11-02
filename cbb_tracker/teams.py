"""Matching team names between ESPN and The Odds API.

The two sources name schools differently ("Mississippi Rebels" vs "Ole Miss Rebels", "Michigan St
Spartans" vs "Michigan State Spartans"), and neutral-site games can list home and away the other way
round. Matching is therefore on normalized names, either way round, with a small alias table for the
known differences and a looser nickname-plus-location fallback.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta

# Odds API spelling -> ESPN spelling (both already normalized by `_clean`).
ALIASES = {
    "mississippi rebels": "ole miss rebels",
    "miami fl hurricanes": "miami hurricanes",
    "cal golden bears": "california golden bears",
    "southern california trojans": "usc trojans",
    "louisiana state tigers": "lsu tigers",
    "central florida knights": "ucf knights",
    "pitt panthers": "pittsburgh panthers",
    "north carolina state wolfpack": "nc state wolfpack",
    "brigham young cougars": "byu cougars",
    "texas christian horned frogs": "tcu horned frogs",
    "southern methodist mustangs": "smu mustangs",
}
# Words that say nothing about which school it is.
GENERIC = {"state", "university", "college", "north", "south", "east", "west", "northern", "southern",
           "eastern", "western", "central", "of", "the", "at", "tech", "a", "m", "am", "and"}


def _clean(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[.'’]", "", s)                       # "N.C. State" -> "nc state", "St. John's" -> "st johns"
    s = re.sub(r"[^a-z0-9 ]", " ", s.replace("&", " "))
    return " ".join(s.split())


def team_key(name: str) -> str:
    """Normalized, alias-resolved key. "St" counts as "State" anywhere but the first word (Saint)."""
    toks = _clean(name).split()
    toks = [("state" if t == "st" and i > 0 else t) for i, t in enumerate(toks)]
    s = " ".join(toks)
    return ALIASES.get(s, s)


def _loose(a: str, b: str) -> bool:
    """Same nickname (last word) and at least one distinctive location word in common."""
    ta, tb = a.split(), b.split()
    if len(ta) < 2 or len(tb) < 2 or ta[-1] != tb[-1]:
        return False
    return bool((set(ta[:-1]) & set(tb[:-1])) - GENERIC)


def same_team(a: str, b: str) -> int:
    """2 = same after normalizing, 1 = plausibly the same school, 0 = different."""
    ka, kb = team_key(a), team_key(b)
    if not ka or not kb:
        return 0
    if ka == kb:
        return 2
    return 1 if _loose(ka, kb) else 0


def _t(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def find_game(home: str, away: str, commence: str, games: list[dict], window_h: float = 12.0) -> dict | None:
    """The ESPN game row for an odds event, or None. `games` rows have home/away {name} and start_utc.

    Tried in order: both teams exact; both teams at least loose; one team exact with a start time within
    90 minutes (a team can't play two games at once, so that is unambiguous). Home/away may be swapped."""
    t = _t(commence)
    if t is None:
        return None
    cands = []
    for g in games:
        gt = _t(g.get("start_utc"))
        if gt is None or abs(gt - t) > timedelta(hours=window_h):
            continue
        gh, ga = (g.get("home") or {}).get("name"), (g.get("away") or {}).get("name")
        straight = (same_team(gh, home), same_team(ga, away))
        swapped = (same_team(gh, away), same_team(ga, home))
        best = max((straight, swapped), key=lambda p: (min(p), sum(p)))
        cands.append((best, abs(gt - t), g))
    for need in (2, 1):
        hit = [c for c in cands if min(c[0]) >= need]
        if hit:
            return min(hit, key=lambda c: c[1])[2]
    near = [c for c in cands if max(c[0]) == 2 and c[1] <= timedelta(minutes=90)]
    return min(near, key=lambda c: c[1])[2] if near else None
