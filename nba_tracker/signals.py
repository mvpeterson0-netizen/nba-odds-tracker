"""Signals page data: frozen NBA signals (NBA-TH-010 .. 015), every graded bet this season and today's plays.

    python -m nba_tracker.signals [data_dir] [out_dir]     (also called from nba_tracker.build)

Frozen 2026-11-28 from the in-season sweep (claude/NBA_signal_sweep_2026-11-28.md in the project). Rules are frozen:
change a definition only by adding a new versioned signal, never by editing one below.

Team signals bet game lines: DraftKings line and price from the first pre-tip game-lines fetch of the day
(the 7 AM CT pull; FanDuel if DraftKings has none). Player signals bet props: DraftKings line and price from the
latest ~1 h pre-game capture (FanDuel if DraftKings has no line); a line with only a morning capture is not graded.
1 unit flat. Overtime = 5+ periods (games.json), or team minutes over 250 in the box score when periods are missing.
National TV = a broadcast name starting ESPN, ABC, TNT, NBC, Peacock, Prime Video or NBA TV.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .build import norm_name, norm_team, _read, _json, _f

FREEZE_DATE = "2026-11-28"
SEASON_W1 = date(2026, 10, 19)          # Monday of the opening week: W1 = Oct 19-25
NATL = re.compile(r"^(ESPN|ABC|TNT|NBC|Peacock|Prime Video|NBA TV)", re.I)
PROP_MK = {"player_points": "pts", "player_rebounds": "reb", "player_assists": "ast", "player_threes": "fg3m"}
MK_SHORT = {"pts": "Pts", "reb": "Reb", "ast": "Ast", "fg3m": "3PM"}

SIGNALS = [
    {"id": "NBA-TH-010", "key": "otfade", "bet": "Spread", "gates": ["Opponent's last game went to overtime", "This team's last game did not"], "kind": "team", "market": "Spread", "title": "Off-OT fade",
     "short": "Bet against a team whose last game went to overtime",
     "rule": "Team A's previous game went to OT and team B's did not: bet team B on the spread. No bet when both or neither did.",
     "why": "Tired legs the next game. Leads all three markets this season (spread, total, props).",
     "found": "2017-18 to 2025-26 at the consensus closing line, -110: 52.5% on 1,030 bets, +0.3% ROI, positive in 5 of 9 seasons."},
    {"id": "NBA-TH-011", "key": "otunder", "bet": "Under", "gates": ["Either team's last game went to overtime"], "kind": "team", "market": "Total", "title": "Off-OT under",
     "short": "Game Under when either team's last game went to overtime",
     "rule": "Either team's previous game went to OT: bet the game Under.",
     "why": "Same fatigue idea on the total. Same games as Off-OT fade, so not separate evidence.",
     "found": "2017-18 to 2025-26 at the close, -110: 51.6% on 1,069 bets, -1.5% ROI."},
    {"id": "NBA-TH-013", "key": "otb2b", "bet": "Spread", "gates": ["Opponent's last game went to overtime", "That OT game was last night (back-to-back)", "This team's last game was not OT"], "kind": "team", "market": "Spread", "title": "Off-OT + B2B fade",
     "short": "Bet against a team on a back-to-back right after an OT game",
     "rule": "Team A's previous game went to OT and was yesterday; team B's previous game was not OT: bet team B on the spread.",
     "why": "The strongest version of the fatigue idea over ten seasons. Rare: a few bets a month.",
     "found": "2017-18 to 2025-26 at the close, -110: 57.9% on 184 bets, +10.1% ROI, positive in 6 of 9 seasons."},
    {"id": "NBA-TH-014", "key": "natltv", "bet": "Under", "gates": ["Game is on national TV: ESPN, ABC, TNT, NBC, Peacock, Prime Video or NBA TV"], "kind": "team", "market": "Total", "title": "National TV under",
     "short": "Game Under in nationally televised games",
     "rule": "Game on ESPN, ABC, TNT, NBC, Peacock, Prime Video or NBA TV per the ESPN scoreboard: bet the game Under.",
     "why": "Fade-the-public proxy: big audiences lean Over. Weakest freeze: history does not support it.",
     "found": "2018-19 to 2025-26 at the close, -110: 51.5% on 1,916 bets, -1.6% ROI, positive in 2 of 7 seasons."},
    {"id": "NBA-TH-012", "key": "otprops", "bet": "Under", "gates": ["His team's last game went to overtime", "He started that game", "Points, rebounds, assists or threes prop"], "kind": "player", "market": "Pts/Reb/Ast/3PM", "title": "Off-OT starter unders",
     "short": "Starters' prop Unders the game after their team's OT game",
     "rule": "Player started his previous game and his team's previous game went to OT: Under on points, rebounds, assists and threes.",
     "why": "The fatigue idea on player props. All four markets kept even though rebounds lagged before the freeze.",
     "found": "No prop history before this season. In the sweep: points and threes did best, rebounds worst (about -18%)."},
    {"id": "NBA-TH-015", "key": "hotfg", "bet": "Under", "gates": ["Last-5 FG% is 8+ points above his season FG%", "50+ field-goal attempts this season", "Points prop"], "kind": "player", "market": "Points", "title": "Hot-shooter points under",
     "short": "Points Under when a player's last-5 FG% is 8+ points above his season FG%",
     "rule": "Last 5 games FG% minus season-to-date FG% is 0.08 or more, with 50+ FGA on the season: points Under.",
     "why": "Shooting streaks regress; the line tends to follow the hot stretch.",
     "found": "No prop history before this season. In the sweep, points Unders overall returned about -1.7%."},
]


def _dt(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _et_date(start) -> str | None:
    t = _dt(start)
    return (t - timedelta(hours=5)).date().isoformat() if t else None


def _wk(d: str) -> int:
    return (date.fromisoformat(d) - SEASON_W1).days // 7 + 1


def _dec(am):
    am = _f(am)
    if am is None:
        return None
    return 1 + am / 100 if am > 0 else 1 + 100 / -am


def _grade(res: float, price) -> tuple[str, float]:
    """res > 0 = bet won. Returns (W/L/P, units)."""
    if res == 0:
        return "P", 0.0
    if res > 0:
        d = _dec(price) or (1 + 100 / 110)
        return "W", round(d - 1, 4)
    return "L", -1.0


def build(data_dir: Path, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    today_et = (now - timedelta(hours=5)).date().isoformat()

    # ---------- games: finals (games.json) + today's / tomorrow's scoreboards
    games = {gid: dict(g) for gid, g in _json(data_dir / "games.json", {}).items()}
    for name in ("games_today", "games_tomorrow", "results_yesterday"):
        for g in (_json(data_dir / "latest" / f"{name}.json", {}) or {}).get("rows", []):
            gid = g.get("game_id")
            if not gid:
                continue
            cur = games.get(gid, {})
            games[gid] = {**cur, "date": cur.get("date") or _et_date(g.get("start_utc")), "start": g.get("start_utc"),
                          "home": g["home"]["abbr"], "away": g["away"]["abbr"],
                          "home_name": g["home"]["name"], "away_name": g["away"]["name"],
                          "hs": g["home"].get("score"), "as": g["away"].get("score"),
                          "final": bool(g.get("completed")) or cur.get("final", False),
                          "state": g.get("state"), "tv": cur.get("tv") or g.get("broadcasts"),
                          "periods": cur.get("periods") or (g.get("period") if g.get("completed") else None)}
    # broadcast names for older finals come from the daily scoreboard snapshots
    for f in sorted((data_dir / "history").glob("*/games_today.json")):
        for g in (_json(f, {}) or {}).get("rows", []):
            gid = g.get("game_id")
            if gid in games and not games[gid].get("tv") and g.get("broadcasts"):
                games[gid]["tv"] = g["broadcasts"]
    for g in games.values():
        g["date"] = g.get("date") or _et_date(g.get("start"))
        g["natl"] = any(NATL.match(str(b)) for b in (g.get("tv") or []))

    # ---------- box scores
    box = _read(data_dir / "player_games.csv")
    team_min = defaultdict(float)
    for r in box:
        if r.get("played") == "True":
            team_min[(r["game_id"], r["team"])] += _f(r.get("min")) or 0
    for gid, g in games.items():
        if not g.get("final"):
            g["ot"] = False
            continue
        p = _f(g.get("periods"))
        if p:
            g["ot"] = p > 4
        else:
            mins = [team_min.get((gid, g.get("home")), 0), team_min.get((gid, g.get("away")), 0)]
            g["ot"] = max(mins) > 250

    # team schedule -> previous game for every team-game
    sched = defaultdict(list)
    for gid, g in games.items():
        if g.get("start") and g.get("home") and g.get("away"):
            sched[g["home"]].append((g["start"], gid))
            sched[g["away"]].append((g["start"], gid))
    prev = {}  # (gid, team) -> previous game id (final) or None
    for team, lst in sched.items():
        lst.sort()
        last_final = None
        for start, gid in lst:
            prev[(gid, team)] = last_final
            if games[gid].get("final"):
                last_final = gid

    def prev_info(gid, team):
        pg = prev.get((gid, team))
        if not pg:
            return None
        p = games[pg]
        rest = (date.fromisoformat(games[gid]["date"]) - date.fromisoformat(p["date"])).days - 1
        opp = p["away"] if p["home"] == team else p["home"]
        return {"gid": pg, "ot": p.get("ot"), "rest": rest, "opp": opp, "date": p["date"]}

    # player histories (played games, by start time)
    hist = defaultdict(list)
    seen = set()
    for r in sorted(box, key=lambda r: r.get("start_utc") or ""):
        aid = r.get("athlete_id")
        if not aid or (r["game_id"], aid) in seen:
            continue
        seen.add((r["game_id"], aid))
        hist[aid].append(r)
    by_game_name = {}
    latest_team = {}
    for aid, rows in hist.items():
        for r in rows:
            by_game_name[(r["game_id"], norm_name(r["player"]))] = aid
        latest_team[aid] = (rows[-1]["team"], rows[-1]["player"])
    team_names = defaultdict(dict)   # team -> norm name -> aid (latest team)
    for aid, (team, nm) in latest_team.items():
        team_names[team][norm_name(nm)] = aid
    for abbr, rr in _json(data_dir / "rosters.json", {}).items():
        for a in rr.get("players", []):
            if a.get("id") and a.get("name"):
                team_names[abbr].setdefault(norm_name(a["name"]), a["id"])

    def before(aid, start):
        return [r for r in hist.get(aid, []) if (r.get("start_utc") or "") < start and r.get("played") == "True"]

    # ---------- odds events -> ESPN game ids
    def game_for(home_name, commence):
        t = _dt(commence)
        if not t:
            return None
        for gid, g in games.items():
            if norm_team(g.get("home_name")) == norm_team(home_name):
                gt = _dt(g.get("start"))
                if gt and abs((gt - t).total_seconds()) <= 6 * 3600:
                    return gid
        return None

    # game lines: first pre-tip fetch per event, DraftKings else FanDuel
    # the bet point is the first fetch on game day (the 7 AM CT pull); an event first seen in an earlier day's pull
    # uses that game-day fetch, falling back to the latest pre-tip fetch when there was none on game day
    glines = defaultdict(dict)
    olog = []
    for f in sorted((data_dir / "odds_log").glob("*.csv")):
        olog.extend(_read(f))
    fetches = defaultdict(set)
    for r in olog:
        if r.get("in_play") == "False" and r.get("fetched_at", "") < r.get("commence_utc", ""):
            fetches[(r["event_id"], r["commence_utc"])].add(r["fetched_at"])
    first_fetch = {}
    for (k, commence), fs in fetches.items():
        gday = _et_date(commence)
        same = sorted(x for x in fs if _et_date(x) == gday)
        first_fetch[k] = same[0] if same else max(fs)
    ev_gid = {}
    for r in olog:
        k = r["event_id"]
        if first_fetch.get(k) != r.get("fetched_at") or r.get("book") not in ("draftkings", "fanduel"):
            continue
        if k not in ev_gid:
            ev_gid[k] = game_for(r["home_team"], r["commence_utc"])
        gid = ev_gid[k]
        if not gid:
            continue
        side = "home" if r["outcome"] == r["home_team"] else "away" if r["outcome"] == r["away_team"] else r["outcome"].lower()
        glines[(gid, r["book"])][(r["market"], side)] = (_f(r["point"]), _f(r["price"]), r["fetched_at"])

    def gline(gid, market, side):
        for book in ("draftkings", "fanduel"):
            v = glines.get((gid, book), {}).get((market, side))
            if v and v[0] is not None:
                return {"point": v[0], "price": v[1], "book": book, "at": v[2]}
        return None

    # props: pregame latest per (event, market, player, book) for grading; latest of any pull for upcoming plays
    pre, cur = {}, {}
    for r in _read(data_dir / "prop_captures.csv"):
        if r.get("market") not in PROP_MK:
            continue
        key = (r["event_id"], r["market"], r["player"], r["book"])
        for store, ok in ((pre, r.get("pull_type") == "pregame"), (cur, True)):
            if not ok:
                continue
            s = store.setdefault(key, {"at": "", "rows": {}})
            if r["captured_at"] > s["at"]:
                s["at"], s["rows"] = r["captured_at"], {}
            if r["captured_at"] == s["at"]:
                s["rows"][r["side"]] = (_f(r["point"]), _f(r["price"]))
                s["home"], s["commence"], s["pull"] = r["home_team"], r["commence_utc"], r.get("pull_type")

    def pick_lines(store):
        out = {}   # (gid, aid, mk) -> line dict
        for (ev, market, player, book), s in store.items():
            o, u = s["rows"].get("Over"), s["rows"].get("Under")
            if not o or not u or o[0] != u[0] or o[0] is None:
                continue
            if ev not in ev_gid:
                ev_gid[ev] = game_for(s["home"], s["commence"])
            gid = ev_gid[ev]
            if not gid:
                continue
            nn = norm_name(player)
            aid = by_game_name.get((gid, nn))
            if not aid:
                g = games[gid]
                aid = team_names.get(g["home"], {}).get(nn) or team_names.get(g["away"], {}).get(nn)
            if not aid:
                continue
            k = (gid, aid, PROP_MK[market])
            rank = 0 if book == "draftkings" else 1
            if k in out and out[k]["rank"] <= rank:
                continue
            out[k] = {"rank": rank, "book": book, "point": o[0], "o": o[1], "u": u[1], "player": player,
                      "pull": s.get("pull"), "at": s["at"]}
        return out

    pre_lines, cur_lines = pick_lines(pre), pick_lines(cur)
    box_row = {(r["game_id"], r["athlete_id"]): r for r in box if r.get("athlete_id")}

    def team_of(aid, gid):
        r = box_row.get((gid, aid))
        if r:
            return r["team"]
        g = games[gid]
        t = latest_team.get(aid, (None,))[0]
        return t if t in (g["home"], g["away"]) else None

    out = {s["id"]: {**s, "bets": [], "plays": []} for s in SIGNALS}

    def matchup(g):
        return f"{g['away']} @ {g['home']}"

    def upcoming(g):
        return not g.get("final") and g.get("date") and g["date"] >= today_et and g.get("date") <= (date.fromisoformat(today_et) + timedelta(days=1)).isoformat()

    # ---------- team signals
    for gid, g in sorted(games.items(), key=lambda kv: kv[1].get("start") or ""):
        if not g.get("date") or g["date"] < "2026-10-20" or not g.get("home"):
            continue
        final, up = bool(g.get("final")), upcoming(g)
        if not final and not up:
            continue
        H, A = g["home"], g["away"]
        ph, pa = prev_info(gid, H), prev_info(gid, A)
        oth = bool(ph and ph["ot"]); ota = bool(pa and pa["ot"])
        margin = (g["hs"] - g["as"]) if final and g.get("hs") is not None and g.get("as") is not None else None
        total = (g["hs"] + g["as"]) if margin is not None else None

        def spread_bet(sig, team, why):
            side = "home" if team == g["home"] else "away"
            ln = gline(gid, "spreads", side)
            base = {"date": g["date"], "wk": _wk(g["date"]), "gid": gid, "matchup": matchup(g), "start": g.get("start"),
                    "team": team, "why": why}
            if final:
                if not ln or margin is None:
                    return
                m = (margin if side == "home" else -margin) + ln["point"]
                res, u = _grade(m, ln["price"])
                out[sig]["bets"].append({**base, "pick": f"{team} {ln['point']:+g}", "line": ln["point"], "price": ln["price"],
                                         "book": ln["book"], "res": res, "u": u,
                                         "score": f"{g['away']} {g['as']}, {g['home']} {g['hs']}"})
            else:
                out[sig]["plays"].append({**base, "pick": f"{team} {ln['point']:+g}" if ln else f"{team} spread",
                                          "line": ln and ln["point"], "price": ln and ln["price"], "book": ln and ln["book"],
                                          "state": g.get("state")})

        def under_bet(sig, why):
            ln = gline(gid, "totals", "under")
            base = {"date": g["date"], "wk": _wk(g["date"]), "gid": gid, "matchup": matchup(g), "start": g.get("start"), "why": why}
            if final:
                if not ln or total is None:
                    return
                res, u = _grade(ln["point"] - total, ln["price"])
                out[sig]["bets"].append({**base, "pick": f"Under {ln['point']:g}", "line": ln["point"], "price": ln["price"],
                                         "book": ln["book"], "res": res, "u": u, "score": f"{g['away']} {g['as']}, {g['home']} {g['hs']}",
                                         "actual": total})
            else:
                out[sig]["plays"].append({**base, "pick": f"Under {ln['point']:g}" if ln else "Under",
                                          "line": ln and ln["point"], "price": ln and ln["price"], "book": ln and ln["book"],
                                          "state": g.get("state")})

        if oth != ota:
            tired, fresh, p = (H, A, ph) if oth else (A, H, pa)
            why = f"{tired} went to OT vs {p['opp']} ({p['date'][5:].replace('-', '/')})"
            spread_bet("NBA-TH-010", fresh, why)
            if p["rest"] == 0:
                spread_bet("NBA-TH-013", fresh, why + ", back-to-back")
        if oth or ota:
            names = [t for t, o in ((A, ota), (H, oth)) if o]
            under_bet("NBA-TH-011", " and ".join(names) + " played OT last game")
        if g.get("natl"):
            nets = [b for b in (g.get("tv") or []) if NATL.match(str(b))]
            under_bet("NBA-TH-014", "National TV: " + ", ".join(nets))

    # ---------- player signals
    lines_all = {}
    for k, v in pre_lines.items():
        lines_all[k] = ("pre", v)
    for k, v in cur_lines.items():
        if k not in lines_all:
            lines_all[k] = ("cur", v)
    for (gid, aid, mk), (kind, ln) in sorted(lines_all.items(), key=lambda kv: games[kv[0][0]].get("start") or ""):
        g = games[gid]
        final, up = bool(g.get("final")), upcoming(g)
        if not final and not up:
            continue
        if final and kind != "pre":
            continue                                  # graded bets need the pre-game line
        if up and (gid, aid, mk) in cur_lines:
            ln = cur_lines[(gid, aid, mk)]            # show the newest line for plays
        team = team_of(aid, gid)
        if not team:
            continue
        r = box_row.get((gid, aid))
        if final and (not r or r.get("played") != "True"):
            continue                                  # DNP / no box score: void
        past = before(aid, g.get("start") or "")
        base = {"date": g["date"], "wk": _wk(g["date"]), "gid": gid, "matchup": matchup(g), "start": g.get("start"),
                "aid": aid, "player": (latest_team.get(aid) or (None, ln["player"]))[1] or ln["player"], "team": team,
                "mk": mk, "pick": f"Under {ln['point']:g} {MK_SHORT[mk]}", "line": ln["point"], "price": ln["u"], "book": ln["book"]}

        def emit(sig, why):
            if final:
                act = _f(r.get(mk))
                if act is None:
                    return
                res, u = _grade(ln["point"] - act, ln["u"])
                out[sig]["bets"].append({**base, "why": why, "actual": act, "res": res, "u": u})
            else:
                out[sig]["plays"].append({**base, "why": why, "state": g.get("state"),
                                          "pull": "pre-game" if ln.get("pull") == "pregame" else "7 AM"})

        p = prev_info(gid, team)
        if p and p["ot"] and past and past[-1]["game_id"] == p["gid"] and past[-1].get("starter") == "True":
            emit("NBA-TH-012", f"{team} went to OT vs {p['opp']} ({p['date'][5:].replace('-', '/')}); he started")
        if mk == "pts" and past:
            fg = [(_f(x.get("fgm")), _f(x.get("fga"))) for x in past]
            fg = [(m, a) for m, a in fg if m is not None and a is not None]
            sa = sum(a for _, a in fg)
            last5 = fg[-5:]
            if sa >= 50 and len(last5) >= 3 and sum(a for _, a in last5) > 0:
                season = sum(m for m, _ in fg) / sa
                l5 = sum(m for m, _ in last5) / sum(a for _, a in last5)
                if l5 - season >= 0.08:
                    emit("NBA-TH-015", f"Last {len(last5)} FG% {l5:.0%} vs season {season:.0%}")

    for s in out.values():
        s["bets"].sort(key=lambda b: (b["date"], b.get("start") or "", b.get("player") or ""))
        s["plays"].sort(key=lambda b: (b.get("start") or "", b.get("player") or ""))
    return {"generated_utc": now.isoformat(timespec="seconds"), "freeze_date": FREEZE_DATE,
            "season_w1": SEASON_W1.isoformat(), "today": today_et, "signals": list(out.values())}


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    data_dir = Path(argv[0] if argv else "data")
    out_dir = Path(argv[1] if len(argv) > 1 else "site/data")
    out_dir.mkdir(parents=True, exist_ok=True)
    d = build(data_dir)
    (out_dir / "signals.json").write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
    for s in d["signals"]:
        w = sum(b["res"] == "W" for b in s["bets"]); l_ = sum(b["res"] == "L" for b in s["bets"])
        p = sum(b["res"] == "P" for b in s["bets"]); u = sum(b["u"] for b in s["bets"])
        n = len(s["bets"])
        print(f"{s['id']} {s['title']:<26} {w}-{l_}-{p}  {u:+.2f}u  ROI {100 * u / n if n else 0:+.1f}%  plays {len(s['plays'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
