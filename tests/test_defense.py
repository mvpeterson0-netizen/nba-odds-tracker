import json
from datetime import datetime, timezone

from nba_tracker import defense

TEAMS = ["AAA", "BBB", "CCC", "DDD"]


def props(extra_final=True):
    """Two guards (G1 on AAA, G2 on BBB). Dates: 10-20 and 10-21 played; 10-22 is 'today'."""
    games = {
        "g1": {"date": "2026-10-20", "start": "2026-10-20T23:00Z", "home": "AAA", "away": "CCC", "final": True},
        "g2": {"date": "2026-10-21", "start": "2026-10-21T23:00Z", "home": "BBB", "away": "DDD", "final": extra_final},
        "g3": {"date": "2026-10-22", "start": "2026-10-22T23:00Z", "home": "AAA", "away": "BBB", "final": False},
    }
    players = {"p1": {"name": "G1", "team": "AAA", "pos": "G"}, "p2": {"name": "G2", "team": "BBB", "pos": "G"},
               "c1": {"name": "C1", "team": "AAA", "pos": "C"}}
    pts = lambda line, act, res: {"line": line, "act": act, "res": res}
    lines = {
        "p1": {"g1": {"player_points": pts(20.5, 30, "over")}},            # AAA guard vs CCC: CCC gave up +9.5
        "p2": {"g2": {"player_points": pts(20.5, 18, "under")}},           # BBB guard vs DDD: DDD held him -2.5
        "c1": {"g1": {"player_points": pts(10.5, 10.5, "push")}},          # center, separate table
    }
    logs = {"p1": [{"g": "g1"}], "p2": [{"g": "g2"}] if extra_final else [], "c1": [{"g": "g1"}]}
    return {"games": games, "players": players, "lines": lines, "logs": logs}


def row(snap, key, team):
    return next(r for r in snap[key] if r[0] == team)


def test_rank_orientation_and_shrinkage():
    snap = defense.snapshot(props(), "2026-10-22")
    key = "player_points|G"
    worst, tough = row(snap, key, "CCC"), row(snap, key, "DDD")
    assert worst[1] == 4 and tough[1] == 1            # N = worst defense, 1 = toughest
    assert worst[2] == 1 and worst[3] == 9.5          # one graded game, +9.5 vs the line
    # teams with no games tie in the middle (ranks 2 and 3 share, rounded)
    assert {row(snap, key, "AAA")[1], row(snap, key, "BBB")[1]} <= {2, 3}


def test_only_games_before_the_date_count():
    snap = defense.snapshot(props(), "2026-10-20")     # nothing played before the first date
    assert all(r[2] == 0 for r in snap["player_points|G"])
    snap = defense.snapshot(props(), "2026-10-21")     # only 10-20 counts
    assert row(snap, "player_points|G", "CCC")[2] == 1 and row(snap, "player_points|G", "DDD")[2] == 0


def test_freeze_writes_once_and_never_rewrites(tmp_path):
    now = datetime(2026, 10, 22, 14, 0, tzinfo=timezone.utc)
    wrote = defense.freeze(tmp_path, props(), "2026-10-22", now)
    assert wrote == ["2026-10-20", "2026-10-21", "2026-10-22"]
    f = tmp_path / "defense" / "2026-10-22.json"
    first = f.read_text()
    saved = json.loads(first)
    assert saved["backfilled"] is False and tmp_path.joinpath("defense", "2026-10-21.json").exists()
    assert json.loads((tmp_path / "defense" / "2026-10-21.json").read_text())["backfilled"] is True
    # later the data changes (a stat is graded differently); the saved snapshot must not change
    p2 = props()
    p2["lines"]["p1"]["g1"]["player_points"] = {"line": 20.5, "act": 5, "res": "under"}
    assert defense.freeze(tmp_path, p2, "2026-10-22", now) == []
    assert f.read_text() == first
    assert defense.load(tmp_path)["2026-10-22"]["r"]["player_points|G"] == saved["ranks"]["player_points|G"]


def test_today_waits_for_earlier_box_scores_until_tip(tmp_path):
    p = props(extra_final=True)
    p["logs"]["p2"] = []                                # g2 is final but its box score hasn't landed
    p["logs"]["c1"] = [{"g": "g1"}]
    morning = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
    assert "2026-10-22" not in defense.freeze(tmp_path, p, "2026-10-22", morning)
    after_tip = datetime(2026, 10, 22, 23, 5, tzinfo=timezone.utc)
    assert "2026-10-22" in defense.freeze(tmp_path, p, "2026-10-22", after_tip)
    assert json.loads((tmp_path / "defense" / "2026-10-22.json").read_text())["prior_games_complete"] is False
