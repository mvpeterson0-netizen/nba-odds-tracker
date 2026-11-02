"""Build site/data/cbb.json: Power 4 player-points lines joined to box scores and graded.

    python -m cbb_tracker.build [data_dir] [out_dir]

Same output shape and grading rules as the NBA side (nba_tracker/build.py), points only:
  - Line: the last pre-tip capture for the game; DraftKings first, FanDuel when DraftKings has none.
  - over / under / push against the player's actual points; void if he had a line but didn't play;
    pending until the game is final.
  - The 8 AM line is kept so the board can show how the line moved.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from nba_tracker.build import BOOK_ORDER, _f, _json, _read, norm_name

from .teams import find_game

MARKETS = [{"id": "player_points", "short": "PTS", "label": "Points", "stat": "pts"}]
MK = "player_points"
ET = ZoneInfo("America/New_York")
KEEP_DAYS = 2      # games without lines are dropped from the site file once they are older than this


def _snap(rows: list[dict], home: str) -> dict:
    """One capture's rows (both markets) -> {sp: home spread, spp: its price, tot: total, op/up: over/under prices}."""
    out: dict = {}
    for r in rows:
        if r["market"] == "spreads" and r["name"] == home:
            out["sp"], out["spp"] = _f(r["point"]), _f(r["price"])
        elif r["market"] == "totals" and r["name"] == "Over":
            out["tot"], out["op"] = _f(r["point"]), _f(r["price"])
        elif r["market"] == "totals" and r["name"] == "Under":
            out["up"] = _f(r["price"])
    return out


def _game_lines(caps: list[dict], match_rows: list[dict], games: dict) -> dict:
    by_ev: dict[str, dict] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for c in caps:
        if (_f(c.get("minutes_before")) or 0) > 0:
            by_ev[c["event_id"]][c["book"]][c["captured_at"]].append(c)
    out: dict[str, dict] = {}
    for ev, books in by_ev.items():
        first = next(iter(next(iter(books.values())).values()))[0]
        hit = find_game(first["home_team"], first["away_team"], first["commence_utc"], match_rows)
        if not hit:
            continue
        per = {}
        for book, by_time in books.items():
            times = sorted(by_time)
            cur = _snap(by_time[times[-1]], first["home_team"])
            if "sp" not in cur and "tot" not in cur:
                continue
            cur.update({"cap": times[-1], "mb": int(_f(by_time[times[-1]][0]["minutes_before"]) or 0),
                        "pt": by_time[times[-1]][0].get("pull_type") or "pregame"})
            am_t = next((t for t in times if by_time[t][0].get("pull_type") == "morning"), None)
            if am_t and am_t != times[-1]:
                cur["am"] = _snap(by_time[am_t], first["home_team"])
            per[book] = cur
        prim = next((b for b in BOOK_ORDER if b in per), None)
        if prim:
            out[hit["game_id"]] = {**per[prim], "book": prim, "alt": {b: v for b, v in per.items() if b != prim}}
    return out


def build(data_dir: Path, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    caps = _read(data_dir / "prop_captures.csv")
    box = _read(data_dir / "player_games.csv")
    games = _json(data_dir / "games.json", {})
    # Yesterday's, today's and tomorrow's Power 4 scoreboards add upcoming and live games (and live scores).
    for name in ("results_yesterday", "games_today", "games_tomorrow"):
        for g in (_json(data_dir / "latest" / f"{name}.json", {}) or {}).get("rows", []):
            gid, h, a = g.get("game_id"), g.get("home") or {}, g.get("away") or {}
            if not gid:
                continue
            cur = games.get(gid, {})
            games[gid] = {**cur, "date": g.get("date") or cur.get("date"), "start": g.get("start_utc"),
                          "home": h.get("abbr"), "away": a.get("abbr"), "home_name": h.get("name"), "away_name": a.get("name"),
                          "home_id": h.get("team_id"), "away_id": a.get("team_id"), "hs": h.get("score"), "as": a.get("score"),
                          "hc": h.get("conf"), "ac": a.get("conf"), "hr": h.get("rank"), "ar": a.get("rank"),
                          "final": bool(g.get("completed")) or cur.get("final", False),
                          "state": g.get("state"), "status": g.get("status")}

    # ---- players and game logs from box scores
    players: dict[str, dict] = {}
    logs: dict[str, list] = defaultdict(list)
    by_game_name: dict[tuple[str, str], str] = {}
    name_idx: dict[str, set] = defaultdict(set)
    seen = set()
    for r in sorted(box, key=lambda r: r.get("start_utc") or ""):
        aid = r.get("athlete_id")
        if not aid or (r["game_id"], aid) in seen:
            continue
        seen.add((r["game_id"], aid))
        played = r.get("played") == "True"
        players[aid] = {"name": r["player"], "team": r["team"], "pos": r.get("position") or ""}
        logs[aid].append({"g": r["game_id"], "d": r.get("game_date"), "opp": r.get("opp"), "ha": r.get("home_away"),
                          "st": r.get("starter") == "True", "p": played, "why": r.get("dnp_reason") if not played else "",
                          "min": _f(r.get("min")), "pts": _f(r.get("pts"))})
        nn = norm_name(r["player"])
        by_game_name[(r["game_id"], nn)] = aid
        name_idx[nn].add(aid)
    for abbr, r in _json(data_dir / "rosters.json", {}).items():       # players with no box score yet
        for a in r.get("players", []):
            aid = a.get("id")
            if not aid or not a.get("name"):
                continue
            if aid not in players:
                players[aid] = {"name": a["name"], "team": abbr, "pos": a.get("pos") or ""}
            else:
                players[aid]["team"] = abbr
            name_idx[norm_name(a["name"])].add(aid)

    # ---- odds events -> ESPN games (names differ between the sources; see teams.py)
    match_rows = [{"game_id": gid, "start_utc": g.get("start"), "home": {"name": g.get("home_name")},
                   "away": {"name": g.get("away_name")}} for gid, g in games.items() if g.get("start")]

    # ---- lines: every pre-tip capture per (event, book, player), by time; latest = current, morning kept
    snaps: dict[tuple, dict] = defaultdict(lambda: defaultdict(dict))
    for c in caps:
        if c.get("market") != MK or (_f(c.get("minutes_before")) or 0) <= 0:
            continue
        snaps[(c["event_id"], c["book"], c["player"])][c["captured_at"]][c["side"]] = c
    grouped: dict[tuple, dict] = defaultdict(dict)
    for (ev, book, pl), by_time in snaps.items():
        times = sorted(by_time)
        am = next((by_time[t] for t in times if next(iter(by_time[t].values())).get("pull_type") == "morning"), None)
        grouped[(ev, pl)][book] = (by_time[times[-1]], am)

    def grade(obj: dict, aid: str, gid: str) -> None:
        g = games.get(gid, {})
        log = next((x for x in logs.get(aid, []) if x["g"] == gid), None)
        if g.get("final") and log is not None:
            if not log["p"]:
                obj["res"], obj["why"] = "void", log.get("why") or "did not play"
            else:
                act = log.get("pts")
                obj["act"] = act
                obj["res"] = None if act is None else ("over" if act > obj["line"] else "under" if act < obj["line"] else "push")
        elif g.get("final"):
            obj["res"], obj["why"] = "void", "no box score entry (likely inactive)"
        else:
            obj["res"] = "pending"

    lines: dict[str, dict] = defaultdict(dict)
    unmatched_games, unmatched_players = set(), set()
    ev_game: dict[str, str | None] = {}
    for (ev, pl), books in grouped.items():
        any_row = next(iter(next(iter(books.values()))[0].values()))
        if ev not in ev_game:
            hit = find_game(any_row["home_team"], any_row["away_team"], any_row["commence_utc"], match_rows)
            ev_game[ev] = hit["game_id"] if hit else None
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
            aid = "n:" + nn
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
        grade(obj, aid, gid)
        lines[aid][gid] = {MK: obj}

    # ---- game spreads and totals (lines.py): latest pre-tip capture per book, plus the 8 AM one for movement
    game_lines = _game_lines(_read(data_dir / "line_captures.csv"), match_rows, games)

    # Keep the site file lean: games without any line are only needed for the board's three days.
    with_lines = {gid for gs in lines.values() for gid in gs} | set(game_lines)
    cutoff = (now.astimezone(ET) - timedelta(days=KEEP_DAYS)).date().isoformat()
    games = {gid: g for gid, g in games.items() if gid in with_lines or str(g.get("date") or "") >= cutoff}
    pull_log = _read(data_dir / "pull_log.csv")
    return {
        "generated_utc": now.isoformat(timespec="seconds"),
        "markets": MARKETS,
        "games": games,
        "players": players,
        "logs": dict(logs),
        "lines": lines,
        "game_lines": game_lines,
        "pulls": pull_log[-60:],
        "unmatched": {"games": sorted(unmatched_games), "players": sorted(unmatched_players)},
    }


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    data_dir = Path(argv[0] if argv else "data/cbb")
    out_dir = Path(argv[1] if len(argv) > 1 else "site/data")
    out_dir.mkdir(parents=True, exist_ok=True)
    d = build(data_dir)
    (out_dir / "cbb.json").write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
    print(f"cbb.json: {len(d['players'])} players, {sum(len(v) for v in d['lines'].values())} player-games with lines, "
          f"{len(d['games'])} games, unmatched games {len(d['unmatched']['games'])}, players {len(d['unmatched']['players'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
