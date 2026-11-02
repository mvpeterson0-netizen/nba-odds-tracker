import csv
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from cbb_tracker import boxscores, build, espn, props
from cbb_tracker.teams import find_game, same_team, team_key

UTC = timezone.utc


# ---------------------------------------------------------------- fixtures

def team(tid, abbr, name, conf, rank=99):
    loc, _, nick = name.rpartition(" ")
    return {"id": tid, "abbr": abbr, "name": name, "loc": loc, "nick": nick, "conf": conf, "rank": rank}


DUKE = team("150", "DUKE", "Duke Blue Devils", "2", 4)
UNC = team("153", "UNC", "North Carolina Tar Heels", "2")
KU = team("2305", "KU", "Kansas Jayhawks", "8", 7)
GRAM = team("2755", "GRAM", "Grambling Tigers", "26")
NIU = team("2459", "NIU", "Northern Illinois Huskies", "14")
MSU = team("127", "MSU", "Michigan State Spartans", "7")


def ev(eid, home, away, start="2026-11-05T00:30Z", state="pre", completed=False, hs=None, aw=None):
    def comp(side, t, score):
        return {"homeAway": side, "id": t["id"], "score": score, "curatedRank": {"current": t["rank"]},
                "team": {"id": t["id"], "abbreviation": t["abbr"], "displayName": t["name"], "location": t["loc"],
                         "name": t["nick"], "conferenceId": t["conf"]}}
    return {"id": eid, "date": start, "shortName": f"{away['abbr']} @ {home['abbr']}",
            "status": {"type": {"state": state, "completed": completed, "shortDetail": "Final" if completed else "7:30 PM"}},
            "competitions": [{"neutralSite": False, "venue": {"fullName": "Arena"},
                              "competitors": [comp("home", home, hs), comp("away", away, aw)]}]}


# ---------------------------------------------------------------- team names

def test_team_key_handles_known_naming_differences():
    assert team_key("Michigan St Spartans") == team_key("Michigan State Spartans")
    assert team_key("Mississippi Rebels") == team_key("Ole Miss Rebels")
    assert team_key("N.C. State Wolfpack") == team_key("NC State Wolfpack")
    assert team_key("Texas A&M Aggies") == team_key("Texas A&M Aggies")
    assert team_key("Miami (FL) Hurricanes") == team_key("Miami Hurricanes")
    assert same_team("Miami Hurricanes", "Miami (OH) RedHawks") == 0
    assert same_team("Michigan Wolverines", "Michigan State Spartans") == 0
    assert same_team("Washington Huskies", "UConn Huskies") == 0
    assert same_team("Texas A&M Aggies", "North Carolina A&T Aggies") == 0
    assert same_team("Ohio State Buckeyes", "Ohio St Buckeyes") == 2


def test_find_game_either_orientation_and_fallbacks():
    games = [{"game_id": "g1", "start_utc": "2026-11-05T00:30Z", "home": {"name": "Duke Blue Devils"},
              "away": {"name": "Kansas Jayhawks"}, "p4": True},
             {"game_id": "g2", "start_utc": "2026-11-05T00:30Z", "home": {"name": "Michigan Wolverines"},
              "away": {"name": "Ole Miss Rebels"}, "p4": True}]
    assert find_game("Duke Blue Devils", "Kansas Jayhawks", "2026-11-05T00:30:00Z", games)["game_id"] == "g1"
    assert find_game("Kansas Jayhawks", "Duke Blue Devils", "2026-11-05T00:30:00Z", games)["game_id"] == "g1"   # neutral site, swapped
    assert find_game("Michigan Wolverines", "Mississippi Rebels", "2026-11-05T00:35:00Z", games)["game_id"] == "g2"
    # one team exact, the other named strangely, same start: still that team's game
    assert find_game("Duke Blue Devils", "Kansas Univ Jayhawks", "2026-11-05T00:30:00Z", games)["game_id"] == "g1"
    assert find_game("Duke Blue Devils", "Kansas Jayhawks", "2026-11-09T00:30:00Z", games) is None            # wrong day
    assert find_game("Gonzaga Bulldogs", "Baylor Bears", "2026-11-05T00:30:00Z", games) is None


# ---------------------------------------------------------------- ESPN parsing

def test_scoreboard_tags_power4_and_ranks():
    raw = {"events": [ev("1", DUKE, GRAM), ev("2", KU, DUKE), ev("3", NIU, GRAM)]}
    g = espn.parse_scoreboard(raw, date(2026, 11, 4))
    assert [x["p4"] for x in g] == [True, True, False]                         # either team in the Power 4
    assert g[0]["home"]["conf"] == "ACC" and g[0]["away"]["conf"] is None and g[0]["away"]["conf_id"] == "26"
    assert g[0]["home"]["rank"] == 4 and g[0]["away"]["rank"] is None         # ESPN's 99 means unranked
    assert g[1]["home"]["conf"] == "Big 12" and g[1]["date"] == "2026-11-04"
    assert [x["game_id"] for x in espn.p4_only(g)] == ["1", "2"]
    assert espn.is_p4(g[0], "both") is False and espn.is_p4(g[1], "both") is True


def test_power4_conference_ids():
    assert espn.P4_CONFERENCES == {"2": "ACC", "7": "Big Ten", "8": "Big 12", "23": "SEC"}


# ---------------------------------------------------------------- box scores

LABELS = ["MIN", "FG", "3PT", "FT", "OREB", "DREB", "REB", "AST", "STL", "BLK", "TO", "PF", "PTS"]


def summary():
    def grp(t, players):
        return {"team": {"id": t["id"], "abbreviation": t["abbr"]}, "statistics": [{"labels": LABELS, "athletes": players}]}
    star = {"athlete": {"id": "11", "displayName": "Cooper Star", "position": {"abbreviation": "F"}}, "starter": True,
            "stats": ["33", "8-15", "2-5", "5-6", "1", "6", "7", "3", "1", "1", "2", "2", "23"]}
    dnp = {"athlete": {"id": "12", "displayName": "Bench Guy"}, "starter": False, "didNotPlay": True, "stats": []}
    other = {"athlete": {"id": "21", "displayName": "Grambling Guard"}, "starter": True,
             "stats": ["30", "5-12", "1-4", "2-2", "0", "2", "2", "5", "2", "0", "3", "1", "13"]}
    return {"boxscore": {"players": [grp(DUKE, [star, dnp]), grp(GRAM, [other])]}}


def game_row(gid="g1", date_="2026-11-04"):
    h, a = {"team_id": "150", "abbr": "DUKE", "name": DUKE["name"], "score": 80}, {"team_id": "2755", "abbr": "GRAM", "name": GRAM["name"], "score": 60}
    return {"game_id": gid, "start_utc": "2026-11-05T00:30Z", "completed": True, "home": h, "away": a, "date": date_, "p4": True}


def test_parse_summary_keeps_points_only_and_marks_dnp():
    rows = boxscores.parse_summary(summary(), game_row())
    assert list(rows[0]) == boxscores.FIELDS
    by = {r["player"]: r for r in rows}
    assert by["Cooper Star"]["pts"] == 23 and by["Cooper Star"]["played"] is True and by["Cooper Star"]["opp"] == "GRAM"
    assert by["Bench Guy"]["played"] is False
    assert by["Grambling Guard"]["home_away"] == "away" and by["Grambling Guard"]["pts"] == 13


def test_days_to_fetch_always_recent_and_skips_closed_days():
    today = date(2026, 11, 10)
    days = boxscores.days_to_fetch(today, {"2026-11-02", "2026-11-03", "2026-11-04"})
    assert days[-2:] == [date(2026, 11, 9), date(2026, 11, 10)]
    assert date(2026, 11, 3) not in days and date(2026, 11, 5) in days
    assert boxscores.days_to_fetch(date(2026, 11, 1), set()) == []              # before opening day
    long_ago = boxscores.days_to_fetch(date(2027, 3, 1), set())
    assert len(long_ago) == boxscores.MAX_DAYS_PER_RUN and long_ago[-1] == date(2027, 3, 1)


def test_boxscore_run_is_idempotent_and_closes_old_days(tmp_path, monkeypatch):
    finals = [game_row("g1", "2026-11-03"), {**game_row("g2", "2026-11-04"), "p4": True}]
    sb = boxscores.Scoreboards(fetch=lambda d: None)
    sb.get = lambda d: [g for g in finals if g["date"] == d.isoformat()]
    calls = []
    monkeypatch.setattr(boxscores, "get_json", lambda url, params=None, **k: (calls.append(url) or (summary(), {})))
    out = boxscores.run(tmp_path, date(2026, 11, 6), sb, [])
    assert out["new_games"] == 2 and out["player_rows"] == 6
    rows = list(csv.DictReader((tmp_path / "player_games.csv").open()))
    assert {r["game_date"] for r in rows} == {"2026-11-03", "2026-11-04"}
    state = json.loads((tmp_path / "boxscore_state.json").read_text())
    assert state["done"] == ["g1", "g2"] and "2026-11-03" in state["days_done"]
    n = len(calls)
    out2 = boxscores.run(tmp_path, date(2026, 11, 6), sb, [])                    # nothing new: no summary refetched
    assert out2["new_games"] == 0 and len(calls) == n
    assert json.loads((tmp_path / "games.json").read_text())["g1"]["final"] is True


# ---------------------------------------------------------------- props

NOW = datetime(2026, 11, 4, 14, 30, tzinfo=UTC)          # 8:30 AM Central


def odds_event(eid, home, away, start):
    return {"id": eid, "commence_time": start, "home_team": home, "away_team": away}


def espn_game(gid, home, away, start, p4=True):
    return {"game_id": gid, "start_utc": start, "p4": p4, "home": {"name": home}, "away": {"name": away}}


def test_classify_keeps_power4_and_reports_unknown_names():
    games = [espn_game("g1", "Duke Blue Devils", "Grambling Tigers", "2026-11-05T00:30Z"),
             espn_game("g2", "Northern Illinois Huskies", "Grambling Tigers", "2026-11-05T01:00Z", p4=False)]
    events = [odds_event("e1", "Duke Blue Devils", "Grambling Tigers", "2026-11-05T00:30:00Z"),
              odds_event("e2", "Northern Illinois Huskies", "Grambling Tigers", "2026-11-05T01:00:00Z"),
              odds_event("e3", "Zzyzx State Wizards", "Nowhere Tech Owls", "2026-11-05T02:00:00Z"),
              odds_event("e4", "Duke Blue Devils", "Grambling Tigers", "2026-11-03T00:30:00Z")]   # already started
    p4, unmatched = props.classify(events, games, NOW, NOW + timedelta(days=2))
    assert [e["id"] for e, _ in p4] == ["e1"] and unmatched == ["Nowhere Tech Owls @ Zzyzx State Wizards"]


def test_plan_morning_pregame_and_empty_throttle():
    g = {"p4": True}
    far = odds_event("a", "H", "A", "2026-11-05T00:30:00Z")                            # 6:30 PM Central, today
    near = odds_event("b", "H", "A", "2026-11-04T15:20:00Z")                           # 50 min out
    tomorrow = odds_event("c", "H", "A", "2026-11-06T00:30:00Z")                       # a different Central day
    out = props.plan([(far, g), (near, g), (tomorrow, g)], set(), {}, NOW)
    assert [(e["id"], t) for e, _, t in out] == [("b", "pregame"), ("a", "morning")]   # pre-game first
    assert props.plan([(far, g)], {("a", "morning")}, {}, NOW) == []                   # already captured
    assert props.plan([(far, g)], set(), {"a": NOW - timedelta(minutes=20)}, NOW) == []     # asked 20 min ago, empty
    assert len(props.plan([(far, g)], set(), {"a": NOW - timedelta(minutes=70)}, NOW)) == 1
    assert props.plan([(far, g)], set(), {}, datetime(2026, 11, 4, 13, 0, tzinfo=UTC)) == []   # 7:00 AM Central: too early


def test_credits_never_eat_into_nba_pregame_needs():
    now = datetime(2026, 11, 4, 14, 30, tzinfo=UTC)
    assert props.credits_ok(None, now, "pregame")
    nba_need = props.NBA_PREGAME_PER_DAY * props._days_left(now) + props.nba.GUARD_RESERVE
    assert props.credits_ok(int(nba_need) + 5, now, "pregame")
    assert not props.credits_ok(int(nba_need) - 5, now, "pregame")
    assert not props.credits_ok(int(nba_need) + 5, now, "morning")                    # morning also keeps college's own pre-game share
    assert props.credits_ok(20000, now, "morning")


def odds_body(eid, player="Cooper Star", line=22.5):
    def outcome(side, price):
        return {"name": side, "description": player, "price": price, "point": line}
    return {"id": eid, "commence_time": "2026-11-05T00:30:00Z", "home_team": "Duke Blue Devils", "away_team": "Grambling Tigers",
            "bookmakers": [{"key": "draftkings", "markets": [{"key": "player_points", "last_update": "x",
                                                               "outcomes": [outcome("Over", -115), outcome("Under", -105)]}]}]}


def test_run_pulls_points_for_power4_only_and_retries_empties_hourly(tmp_path, monkeypatch):
    events = [odds_event("e1", "Duke Blue Devils", "Grambling Tigers", "2026-11-05T00:30:00Z"),
              odds_event("e2", "Northern Illinois Huskies", "Grambling Tigers", "2026-11-05T01:00:00Z")]
    games = [espn_game("g1", "Duke Blue Devils", "Grambling Tigers", "2026-11-05T00:30Z"),
             espn_game("g2", "Northern Illinois Huskies", "Grambling Tigers", "2026-11-05T01:00Z", p4=False)]
    seen, posted = [], {"yes": False}

    def fake_get(url, params, timeout=25.0):
        seen.append((url, dict(params)))
        hdr = {"x-requests-remaining": "19000", "x-requests-last": "1"}
        if url.endswith("/events"):
            return 200, events, hdr
        if posted["yes"]:
            return 200, odds_body("e1"), hdr
        return 200, {"id": "e1", "bookmakers": []}, hdr

    monkeypatch.setattr(props, "_get", fake_get)
    keys = [("ODDS_API_KEY", "k1")]
    s = props.run(tmp_path, keys, games, date(2026, 11, 4), NOW)
    odds_calls = [u for u, _ in seen if "/odds" in u]
    assert odds_calls == [f"{props.BASE}/events/e1/odds"]                              # the mid-major game is never pulled
    assert seen[-1][1]["markets"] == "player_points" and s["status"] == "ok" and s["p4_events"] == 1
    assert s["pulled"][0]["status"] == "empty"

    seen.clear()
    props.run(tmp_path, keys, games, date(2026, 11, 4), NOW + timedelta(minutes=15))   # too soon to ask again
    assert not [u for u, _ in seen if "/odds" in u]

    posted["yes"] = True
    seen.clear()
    s = props.run(tmp_path, keys, games, date(2026, 11, 4), NOW + timedelta(minutes=60))
    assert s["pulled"][0] == {"matchup": "Grambling Tigers @ Duke Blue Devils", "type": "morning", "status": "ok", "rows": 2}
    caps = list(csv.DictReader((tmp_path / "prop_captures.csv").open()))
    assert {c["market"] for c in caps} == {"player_points"} and {c["pull_type"] for c in caps} == {"morning"}
    seen.clear()
    props.run(tmp_path, keys, games, date(2026, 11, 4), NOW + timedelta(minutes=75))   # captured: not pulled again
    assert not [u for u, _ in seen if "/odds" in u]


def test_run_without_keys_does_nothing(tmp_path):
    assert props.run(tmp_path, [], [], date(2026, 11, 4), NOW)["status"] == "no_key"


# ---------------------------------------------------------------- build

def w(path, rows):
    if not rows:
        return
    with path.open("w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)


def cap(book, side, point, price, mb=60, pull_type="pregame", at="2026-11-04T23:30:00Z", player="Cooper Star", market="player_points"):
    return {"captured_at": at, "event_id": "e1", "commence_utc": "2026-11-05T00:30:00Z", "minutes_before": mb,
            "home_team": "Duke Blue Devils", "away_team": "Grambling Tigers", "book": book, "market": market, "player": player,
            "side": side, "point": point, "price": price, "market_updated": "", "pull_type": pull_type}


def boxrow(aid, name, pts, played="True", team_="DUKE", opp="GRAM", ha="home"):
    return {"game_id": "g1", "game_date": "2026-11-04", "start_utc": "2026-11-05T00:30Z", "team_id": "150", "team": team_,
            "opp": opp, "home_away": ha, "athlete_id": aid, "player": name, "position": "F", "starter": "True", "played": played,
            "dnp_reason": "" if played == "True" else "Coach's decision", "min": "30", "pts": pts}


def setup(tmp_path, caps, boxes, final=True):
    w(tmp_path / "prop_captures.csv", caps)
    w(tmp_path / "player_games.csv", boxes)
    (tmp_path / "games.json").write_text(json.dumps({"g1": {
        "date": "2026-11-04", "start": "2026-11-05T00:30Z", "home": "DUKE", "away": "GRAM", "home_name": "Duke Blue Devils",
        "away_name": "Grambling Tigers", "final": final, "hs": 80, "as": 60, "hc": "ACC", "hr": 4}}))


BNOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


def test_build_grades_points_with_dk_primary_and_morning_movement(tmp_path):
    setup(tmp_path, [cap("fanduel", "Over", 21.5, -110), cap("draftkings", "Over", 22.5, -115), cap("draftkings", "Under", 22.5, -105),
                     cap("draftkings", "Over", 21.5, -110, mb=400, pull_type="morning", at="2026-11-04T14:00:00Z"),
                     cap("draftkings", "Over", 99.5, -110, mb=-5)],
          [boxrow("11", "Cooper Star", "23")])
    d = build.build(tmp_path, BNOW)
    ln = d["lines"]["11"]["g1"]["player_points"]
    assert (ln["book"], ln["line"], ln["op"], ln["up"]) == ("draftkings", 22.5, -115, -105)        # in-game capture ignored
    assert ln["act"] == 23 and ln["res"] == "over" and ln["alt"]["fanduel"]["line"] == 21.5
    assert ln["am"]["line"] == 21.5                                                               # 8 AM line kept for movement
    assert d["markets"] == [{"id": "player_points", "short": "PTS", "label": "Points", "stat": "pts"}]
    assert d["games"]["g1"]["hc"] == "ACC" and d["logs"]["11"][0]["pts"] == 23


def test_build_void_push_pending_and_matches_swapped_odds_names(tmp_path):
    setup(tmp_path, [cap("draftkings", "Over", 23, -110)], [boxrow("11", "Cooper Star", "23")])
    assert build.build(tmp_path, BNOW)["lines"]["11"]["g1"]["player_points"]["res"] == "push"
    setup(tmp_path, [cap("draftkings", "Over", 23, -110)], [boxrow("11", "Cooper Star", "", played="False")])
    ln = build.build(tmp_path, BNOW)["lines"]["11"]["g1"]["player_points"]
    assert ln["res"] == "void" and ln["why"] == "Coach's decision"
    setup(tmp_path, [cap("draftkings", "Over", 23, -110)], [boxrow("11", "Cooper Star", "")], final=False)
    assert build.build(tmp_path, BNOW)["lines"]["11"]["g1"]["player_points"]["res"] == "pending"
    # the book lists the game with home and away reversed (neutral site) and a different school spelling
    c = {**cap("draftkings", "Over", 23, -110), "home_team": "Grambling Tigers", "away_team": "Duke Blue Devils"}
    setup(tmp_path, [c], [boxrow("11", "Cooper Star", "30")])
    assert build.build(tmp_path, BNOW)["lines"]["11"]["g1"]["player_points"]["res"] == "over"


def test_build_reports_unmatched_and_ignores_other_markets(tmp_path):
    other = {**cap("draftkings", "Over", 5.5, -110, market="player_rebounds")}
    ghost = {**cap("draftkings", "Over", 12.5, -110, player="Zed Nobody")}
    setup(tmp_path, [other, ghost, {**cap("draftkings", "Over", 9.5, -110), "event_id": "e9", "home_team": "Zzyzx Wizards", "away_team": "Nowhere Owls"}],
          [boxrow("11", "Cooper Star", "23")])
    d = build.build(tmp_path, BNOW)
    assert "player_rebounds" not in json.dumps(d["lines"])
    assert d["unmatched"]["players"] == ["Zed Nobody"] and d["unmatched"]["games"] == ["Nowhere Owls @ Zzyzx Wizards"]
    assert d["players"]["n:zed nobody"]["nolog"] is True


def test_build_drops_old_games_without_lines(tmp_path):
    setup(tmp_path, [], [boxrow("11", "Cooper Star", "23")])
    idx = json.loads((tmp_path / "games.json").read_text())
    idx["old"] = {**idx["g1"], "date": "2026-11-01"}
    (tmp_path / "games.json").write_text(json.dumps(idx))
    assert set(build.build(tmp_path, datetime(2026, 11, 20, tzinfo=UTC))["games"]) == set()
    assert set(build.build(tmp_path, datetime(2026, 11, 3, 12, tzinfo=UTC))["games"]) == {"g1", "old"}   # cutoff is Nov 1


# ---------------------------------------------------------------- whole run

def test_full_run_writes_power4_files_and_builds(tmp_path, monkeypatch):
    from cbb_tracker import __main__ as cli
    day = date(2026, 11, 4)
    slate = {"events": [ev("g1", DUKE, GRAM, state="post", completed=True, hs=80, aw=60), ev("g3", NIU, GRAM, state="post", completed=True, hs=70, aw=50)]}
    monkeypatch.setattr(espn, "fetch_scoreboard", lambda d: slate if d == day else {"events": []})
    monkeypatch.setattr(boxscores, "get_json", lambda url, params=None, **k: ({"athletes": []} if "roster" in url else summary(), {}))
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    for v in ("ODDS_API_KEY_2", "ODDS_API_KEY_3", "ODDS_API_KEY_4", "ODDS_API_KEY_5", "ODDS_API_KEY_6", "ODDS_API_KEY_20K"):
        monkeypatch.delenv(v, raising=False)
    assert cli.run(tmp_path, day) == 0
    today = json.loads((tmp_path / "latest" / "games_today.json").read_text())
    assert today["count"] == 1 and today["division_i_games"] == 2 and today["rows"][0]["game_id"] == "g1"   # NIU/Grambling dropped
    assert (tmp_path / "history" / "2026-11-04" / "games_today.json").exists()
    run = json.loads((tmp_path / "latest" / "run.json").read_text())
    assert run["sources"]["props"] == "no_key" and run["sources"]["boxscores"] == "ok" and run["boxscores"]["new_games"] == 1
    assert run["power4"] == ["ACC", "Big 12", "Big Ten", "SEC"]
    d = build.build(tmp_path, datetime(2026, 11, 5, 12, tzinfo=UTC))
    assert d["games"]["g1"]["final"] and d["logs"]["11"][0]["pts"] == 23 and "g3" not in d["games"]
