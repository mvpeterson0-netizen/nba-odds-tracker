"""Build site/data/props.json: captured prop lines joined to box scores and graded.

    python -m nba_tracker.build [data_dir] [out_dir]

Grading (same rules as the NFL tracker):
  - Line: the last pre-game capture for the game. DraftKings is primary; FanDuel when
    DraftKings has no line for that player and market. Both books are kept.
  - over / under / push: actual stat vs. that line.
  - void: the player had a line but did not play (reason from the box score when given).
  - pending: game not final yet.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

MARKETS = [
    {"id": "player_points", "short": "PTS", "label": "Points", "stat": "pts"},
    {"id": "player_rebounds", "short": "REB", "label": "Rebounds", "stat": "reb"},
    {"id": "player_assists", "short": "AST", "label": "Assists", "stat": "ast"},
    {"id": "player_threes", "short": "3PM", "label": "Threes made", "stat": "fg3m"},
    {"id": "player_points_rebounds_assists", "short": "PRA", "label": "Pts+Reb+Ast", "stat": "pra"},
    {"id": "player_points_rebounds", "short": "P+R", "label": "Pts+Reb", "stat": "pr"},
    {"id": "player_points_assists", "short": "P+A", "label": "Pts+Ast", "stat": "pa"},
    {"id": "player_rebounds_assists", "short": "R+A", "label": "Reb+Ast", "stat": "ra"},
    {"id": "player_steals", "short": "STL", "label": "Steals", "stat": "stl"},
    {"id": "player_blocks", "short": "BLK", "label": "Blocks", "stat": "blk"},
]
STAT = {m["id"]: m["stat"] for m in MARKETS}

# Combo lines estimated from component lines when the books' own combo line wasn't captured.
# Offsets fit to this repo's captures (Oct 2026, ~1,600 DK/FD snapshots): books most often post
# two-stat combos at the sum of the parts + 0.5, and PRA at the exact sum. Priced -110/-110.
COMBO_PARTS = {
    "player_points_rebounds_assists": ["player_points", "player_rebounds", "player_assists"],
    "player_points_rebounds": ["player_points", "player_rebounds"],
    "player_points_assists": ["player_points", "player_assists"],
    "player_rebounds_assists": ["player_rebounds", "player_assists"],
}
COMBO_OFFSET = {"player_points_rebounds_assists": 0.0, "player_points_rebounds": 0.5,
                "player_points_assists": 0.5, "player_rebounds_assists": 0.5}
EST_PRICE = -110.0


def estimate_combo(mk: str, parts: dict) -> dict | None:
    """Estimated combo line from the component line objects, or None if any part is missing."""
    comps = [parts.get(c) for c in COMBO_PARTS[mk]]
    if any(c is None or c.get("line") is None for c in comps):
        return None
    line = sum(c["line"] for c in comps) + COMBO_OFFSET[mk]
    morning = any(c.get("pt") == "morning" for c in comps)
    return {"line": line, "op": EST_PRICE, "up": EST_PRICE, "est": True,
            "pt": "morning" if morning else "pregame",
            "book": comps[0].get("book"), "cap": max(c.get("cap") or "" for c in comps),
            "mb": min(int(c.get("mb") or 0) for c in comps),
            "from": {c: parts[c]["line"] for c in COMBO_PARTS[mk]}, "alt": {},
            **_est_am(mk, comps)}


def _est_am(mk: str, comps: list[dict]) -> dict:
    """8 AM version of a built combo line (for the movement arrow), when every part has one."""
    if any(c.get("pt") == "morning" for c in comps):
        return {}
    ams = [c.get("am") for c in comps]
    if any(not a or a.get("line") is None for a in ams):
        return {}
    return {"am": {"line": sum(a["line"] for a in ams) + COMBO_OFFSET[mk], "op": EST_PRICE, "up": EST_PRICE}}
BOOK_ORDER = ["draftkings", "fanduel"]


def norm_name(n: str) -> str:
    s = unicodedata.normalize("NFKD", str(n or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z ]", "", s.replace("-", " "))
    return " ".join(w for w in s.split() if w not in {"jr", "sr", "ii", "iii", "iv", "v"})


def norm_team(n: str) -> str:
    s = str(n or "").lower()
    s = re.sub(r"^la ", "los angeles ", s)
    return re.sub(r"[^a-z0-9]", "", s)


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def build(data_dir: Path) -> dict:
    caps = _read(data_dir / "prop_captures.csv")
    box = _read(data_dir / "player_games.csv")
    games = _json(data_dir / "games.json", {})
    # Yesterday's, today's and tomorrow's scoreboards add upcoming/live games (and live scores).
    for name in ("results_yesterday", "games_today", "games_tomorrow"):
        for g in (_json(data_dir / "latest" / f"{name}.json", {}) or {}).get("rows", []):
            gid = g.get("game_id")
            if not gid:
                continue
            start = g.get("start_utc")
            try:
                d = (datetime.fromisoformat(start.replace("Z", "+00:00")) - timedelta(hours=5)).date().isoformat()
            except Exception:
                d = None
            cur = games.get(gid, {})
            games[gid] = {**cur, "date": cur.get("date") or d, "start": start,
                          "home": g["home"]["abbr"], "away": g["away"]["abbr"],
                          "home_name": g["home"]["name"], "away_name": g["away"]["name"],
                          "home_id": g["home"]["team_id"], "away_id": g["away"]["team_id"],
                          "hs": g["home"]["score"], "as": g["away"]["score"],
                          "final": bool(g.get("completed")) or cur.get("final", False),
                          "state": g.get("state"), "status": g.get("status")}

    # ---- players and game logs from box scores
    players: dict[str, dict] = {}
    logs: dict[str, list] = defaultdict(list)
    by_game_name: dict[tuple[str, str], str] = {}     # (game_id, norm name) -> athlete id
    name_idx: dict[str, set] = defaultdict(set)        # norm name -> athlete ids
    seen = set()
    for r in sorted(box, key=lambda r: r.get("start_utc") or ""):
        aid = r.get("athlete_id")
        if not aid or (r["game_id"], aid) in seen:
            continue
        seen.add((r["game_id"], aid))
        played = r.get("played") == "True"
        players[aid] = {"name": r["player"], "team": r["team"], "pos": r.get("position") or ""}
        logs[aid].append({"g": r["game_id"], "d": r.get("game_date"), "opp": r.get("opp"), "ha": r.get("home_away"),
                          "st": r.get("starter") == "True", "p": played,
                          "why": r.get("dnp_reason") if not played else "",
                          "min": _f(r.get("min")), "pts": _f(r.get("pts")), "reb": _f(r.get("reb")),
                          "ast": _f(r.get("ast")), "fg3m": _f(r.get("fg3m")),
                          "stl": _f(r.get("stl")), "blk": _f(r.get("blk"))})
        e = logs[aid][-1]
        add = lambda *k: None if any(e[x] is None for x in k) else sum(e[x] for x in k)
        e["pra"], e["pr"], e["pa"], e["ra"] = add("pts", "reb", "ast"), add("pts", "reb"), add("pts", "ast"), add("reb", "ast")
        nn = norm_name(r["player"])
        by_game_name[(r["game_id"], nn)] = aid
        name_idx[nn].add(aid)

    # Rosters cover players with no box score yet.
    for abbr, r in _json(data_dir / "rosters.json", {}).items():
        for a in r.get("players", []):
            aid = a.get("id")
            if not aid or not a.get("name"):
                continue
            if aid not in players:
                players[aid] = {"name": a["name"], "team": abbr, "pos": a.get("pos") or ""}
            else:
                players[aid]["team"] = abbr          # roster is newer than old box scores (trades)
            name_idx[norm_name(a["name"])].add(aid)

    # ---- match odds events to ESPN games (same teams, start within 12 h)
    def game_for(ev_home, ev_away, commence):
        try:
            t = datetime.fromisoformat(commence.replace("Z", "+00:00"))
        except Exception:
            return None
        for gid, g in games.items():
            if norm_team(g.get("home_name")) == norm_team(ev_home) and norm_team(g.get("away_name")) == norm_team(ev_away):
                try:
                    gt = datetime.fromisoformat(str(g.get("start")).replace("Z", "+00:00"))
                except Exception:
                    continue
                if abs((gt - t).total_seconds()) <= 12 * 3600:
                    return gid
        return None

    # ---- lines: for each (event, book, market, player) keep every pre-tip capture, by time.
    # The latest capture is the current line (the ~1 h pre-game pull once it exists, which is
    # what gets graded); the morning (8 AM) capture is kept to show how the line moved.
    snaps: dict[tuple, dict] = defaultdict(lambda: defaultdict(dict))
    for c in caps:
        if (_f(c.get("minutes_before")) or 0) <= 0:
            continue
        snaps[(c["event_id"], c["book"], c["market"], c["player"])][c["captured_at"]][c["side"]] = c
    grouped: dict[tuple, dict] = defaultdict(dict)    # (event, market, player) -> {book: (current sides, morning sides)}
    for (ev, book, mk, pl), by_time in snaps.items():
        times = sorted(by_time)
        cur = by_time[times[-1]]
        am = next((by_time[t] for t in times if (next(iter(by_time[t].values())).get("pull_type") == "morning")), None)
        grouped[(ev, mk, pl)][book] = (cur, am)

    def grade(obj: dict, aid: str, gid: str, mk: str) -> None:
        g = games.get(gid, {})
        log = next((x for x in logs.get(aid, []) if x["g"] == gid), None)
        if g.get("final") and log is not None:
            if not log["p"]:
                obj["res"], obj["why"] = "void", log.get("why") or "did not play"
            else:
                act = log.get(STAT[mk])
                obj["act"] = act
                obj["res"] = None if act is None else ("over" if act > obj["line"] else "under" if act < obj["line"] else "push")
        elif g.get("final"):
            obj["res"], obj["why"] = "void", "no box score entry (likely inactive)"
        else:
            obj["res"] = "pending"

    lines: dict[str, dict] = defaultdict(dict)        # aid -> game_id -> market -> line obj
    unmatched_games, unmatched_players = set(), set()
    ev_game: dict[str, str | None] = {}
    for (ev, mk, pl), books in grouped.items():
        any_row = next(iter(next(iter(books.values()))[0].values()))
        if ev not in ev_game:
            ev_game[ev] = game_for(any_row["home_team"], any_row["away_team"], any_row["commence_utc"])
        gid = ev_game[ev]
        if not gid:
            unmatched_games.add(f'{any_row["away_team"]} @ {any_row["home_team"]}')
            continue
        nn = norm_name(pl)
        aid = by_game_name.get((gid, nn))
        if not aid:
            g = games.get(gid, {})
            cands = [a for a in name_idx.get(nn, ()) if players[a]["team"] in (g.get("home"), g.get("away"))]
            cands = cands or list(name_idx.get(nn, ()))
            aid = cands[0] if len(cands) == 1 else None
        if not aid:
            aid = "n:" + nn                            # no box score yet (e.g. first game of the season)
            g = games.get(gid, {})
            players.setdefault(aid, {"name": pl, "team": "", "pos": "", "nolog": True})
            unmatched_players.add(pl)
        per_book = {}
        for book, (sides, am) in books.items():
            o, u = sides.get("Over"), sides.get("Under")
            base = o or u
            per_book[book] = {"line": _f(base["point"]), "op": _f(o["price"]) if o else None,
                              "up": _f(u["price"]) if u else None, "cap": base["captured_at"],
                              "mb": int(_f(base["minutes_before"]) or 0), "pt": base.get("pull_type") or "pregame"}
            if am and am is not sides:
                ao, au = am.get("Over"), am.get("Under")
                ab = ao or au
                per_book[book]["am"] = {"line": _f(ab["point"]), "op": _f(ao["price"]) if ao else None,
                                        "up": _f(au["price"]) if au else None, "cap": ab["captured_at"]}
        prim = next((b for b in BOOK_ORDER if b in per_book and per_book[b]["line"] is not None), None)
        if prim is None:
            continue
        obj = {**per_book[prim], "book": prim, "alt": {b: v for b, v in per_book.items() if b != prim}}
        grade(obj, aid, gid, mk)
        lines[aid][gid] = {**lines[aid].get(gid, {}), mk: obj}

    # ---- estimated combo lines where the real one is missing
    for aid, by_game in lines.items():
        for gid, ms in by_game.items():
            for mk in COMBO_PARTS:
                if mk in ms:
                    continue
                est = estimate_combo(mk, ms)
                if est:
                    grade(est, aid, gid, mk)
                    ms[mk] = est

    pull_log = _read(data_dir / "pull_log.csv")
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "markets": MARKETS,
        "games": games,
        "players": players,
        "logs": logs,
        "lines": lines,
        "pulls": pull_log[-60:],
        "unmatched": {"games": sorted(unmatched_games), "players": sorted(unmatched_players)},
    }


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    data_dir = Path(argv[0] if argv else "data")
    out_dir = Path(argv[1] if len(argv) > 1 else "site/data")
    out_dir.mkdir(parents=True, exist_ok=True)
    d = build(data_dir)
    (out_dir / "props.json").write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
    print(f"props.json: {len(d['players'])} players, {sum(len(v) for v in d['lines'].values())} player-games with lines, "
          f"unmatched games {len(d['unmatched']['games'])}, players {len(d['unmatched']['players'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
