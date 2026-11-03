"""Frozen opponent-defense ranks.

For each game date D, a snapshot of how every defense ranked against each position (G/F/C) in each prop market,
using only games played BEFORE D. Snapshots are written once to data/defense/<D>.json and never rewritten, so the rank
shown for a game stays what it was on the day it was played, however the defenses change afterwards (or if a stat
is later corrected). The player pages read these frozen ranks; the Defense tab shows the live standings.

Ranking (same method the site used to compute live): every graded player-game (a line plus the actual stat; pushes
count, voids don't) credits the opponent with (actual - line). A team's average is shrunk toward 0 as if it had K extra
games at exactly the line, and all teams are ranked: rank N (30) = worst defense, 1 = toughest. Tied scores (for
example teams with no games yet) share the middle rank of their group.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

from .build import MARKETS

K = 5                                  # shrinkage: extra games at exactly the line
POS = ("G", "F", "C")
FOLDER = "defense"


def entries(props: dict) -> dict[str, list[dict]]:
    """`<market>|<pos>` -> [{d, opp, diff}] for every graded player-game."""
    out: dict[str, list[dict]] = {}
    games, players = props["games"], props["players"]
    for aid, by_game in props["lines"].items():
        p = players.get(aid) or {}
        if p.get("pos") not in POS:
            continue
        for gid, ms in by_game.items():
            g = games.get(gid) or {}
            team = p.get("team")
            opp = g.get("away") if team == g.get("home") else g.get("home") if team == g.get("away") else None
            if not opp or not g.get("date"):
                continue
            for mk, l in ms.items():
                if l.get("act") is None or l.get("res") not in ("over", "under", "push"):
                    continue
                out.setdefault(f"{mk}|{p['pos']}", []).append({"d": g["date"], "opp": opp, "diff": l["act"] - l["line"]})
    return out


def table(rows: list[dict], teams: list[str], before: str) -> list[list]:
    """Every team, worst first: [team, rank, n, avg_vs_line|None]. Only games dated before `before` count."""
    agg: dict[str, list[float]] = {}
    for e in rows:
        if e["d"] < before:
            a = agg.setdefault(e["opp"], [0, 0.0])
            a[0] += 1
            a[1] += e["diff"]
    ranked = []
    for t in teams:
        n, s = agg.get(t, (0, 0.0))
        ranked.append({"team": t, "n": n, "s": s, "score": s / (n + K)})
    ranked.sort(key=lambda r: (-r["score"], -r["n"], r["team"]))
    size = len(ranked)
    i = 0
    while i < size:
        j = i
        while j + 1 < size and ranked[j + 1]["score"] == ranked[i]["score"]:
            j += 1
        for r in ranked[i:j + 1]:
            r["rank"] = math.floor(size - (i + j) / 2 + 0.5)
        i = j + 1
    return [[r["team"], r["rank"], r["n"], round(r["s"] / r["n"], 2) if r["n"] else None] for r in ranked]


def snapshot(props: dict, day: str) -> dict[str, list[list]]:
    ent = entries(props)
    teams = sorted({t for g in props["games"].values() for t in (g.get("home"), g.get("away")) if t})
    return {f"{m['id']}|{p}": table(ent.get(f"{m['id']}|{p}", []), teams, day) for m in MARKETS for p in POS}


def _ready(props: dict, day: str) -> bool:
    """Every game before `day` that has finished has its box score in, so the snapshot doesn't miss late results."""
    logged = {r["g"] for rs in props["logs"].values() for r in rs}
    return all(gid in logged for gid, g in props["games"].items() if g.get("date") and g["date"] < day and g.get("final"))


def freeze(data_dir: Path, props: dict, today: str, now: datetime | None = None) -> list[str]:
    """Write the snapshot for every game date up to `today` that doesn't have one yet; never touch an existing file.

    Past dates with no file are backfilled (flagged), computed from the data as it stands now. Today's is written once
    the earlier games are all in, or as soon as the first game of the day has started."""
    now = now or datetime.now(timezone.utc)
    folder = data_dir / FOLDER
    wrote = []
    dates = sorted({g["date"] for g in props["games"].values() if g.get("date") and g["date"] <= today})
    for day in dates:
        path = folder / f"{day}.json"
        if path.exists():
            continue
        backfilled = day < today
        ready = _ready(props, day)
        if day == today and not ready:
            starts = [g["start"] for g in props["games"].values() if g.get("date") == day and g.get("start")]
            if not starts or now.strftime("%Y-%m-%dT%H:%MZ") < min(starts):
                continue                         # earlier games still being graded and no game has started: wait
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "date": day, "frozen_at": now.isoformat(timespec="seconds"), "method": {"k": K},
            "backfilled": backfilled, "prior_games_complete": ready,
            "ranks": snapshot(props, day)}, separators=(",", ":")) + "\n", encoding="utf-8")
        wrote.append(day)
    return wrote


def load(data_dir: Path) -> dict[str, dict]:
    """date -> {"b": backfilled?, "r": {key: rows}} for the site."""
    out = {}
    for f in sorted((data_dir / FOLDER).glob("*.json")):
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
            out[s["date"]] = {"b": bool(s.get("backfilled")), "r": s["ranks"]}
        except Exception:
            continue
    return out
