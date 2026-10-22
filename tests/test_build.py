import csv
import json

from nba_tracker import build


def w(path, rows):
    with path.open("w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)


def cap(book, side, point, price, mb=150, player="Nikola Jokić", market="player_points"):
    return {"captured_at": "2026-10-22T22:50:00Z", "event_id": "e1", "commence_utc": "2026-10-23T01:40:00Z",
            "minutes_before": mb, "home_team": "Oklahoma City Thunder", "away_team": "Denver Nuggets",
            "book": book, "market": market, "player": player, "side": side, "point": point, "price": price,
            "market_updated": ""}


def box(pts, played="True", aid="3112335", name="Nikola Jokic"):
    return {"game_id": "g1", "game_date": "2026-10-22", "start_utc": "2026-10-23T01:40Z", "team_id": "7", "team": "DEN",
            "opp": "OKC", "home_away": "away", "athlete_id": aid, "player": name, "position": "C", "starter": "True",
            "played": played, "dnp_reason": "" if played == "True" else "Rest", "min": "35", "pts": pts,
            "reb": "12", "ast": "9", "fg3m": "2", "fg3a": "5"}


GAMES = {"g1": {"date": "2026-10-22", "start": "2026-10-23T01:40Z", "home": "OKC", "away": "DEN",
                "home_name": "Oklahoma City Thunder", "away_name": "Denver Nuggets", "final": True}}


def setup(tmp_path, caps, boxes):
    w(tmp_path / "prop_captures.csv", caps)
    w(tmp_path / "player_games.csv", boxes)
    (tmp_path / "games.json").write_text(json.dumps(GAMES))


def test_grades_over_with_dk_primary_and_accent_match(tmp_path):
    setup(tmp_path, [cap("fanduel", "Over", 26.5, -110), cap("draftkings", "Over", 27.5, -115),
                     cap("draftkings", "Under", 27.5, -105), cap("draftkings", "Over", 30.5, -110, mb=-5)],
          [box("31")])
    d = build.build(tmp_path)
    ln = d["lines"]["3112335"]["g1"]["player_points"]
    assert (ln["book"], ln["line"], ln["op"], ln["up"]) == ("draftkings", 27.5, -115, -105)  # in-game capture ignored
    assert ln["act"] == 31 and ln["res"] == "over" and ln["alt"]["fanduel"]["line"] == 26.5


def test_push_and_void(tmp_path):
    setup(tmp_path, [cap("draftkings", "Over", 31, -110)], [box("31")])
    assert build.build(tmp_path)["lines"]["3112335"]["g1"]["player_points"]["res"] == "push"
    setup(tmp_path, [cap("fanduel", "Over", 27.5, -110)], [box("", played="False")])
    ln = build.build(tmp_path)["lines"]["3112335"]["g1"]["player_points"]
    assert ln["res"] == "void" and ln["why"] == "Rest" and ln["book"] == "fanduel"


def test_norm_name():
    assert build.norm_name("Nikola Jokić") == build.norm_name("Nikola Jokic")
    assert build.norm_name("Marvin Bagley III") == "marvin bagley"
    assert build.norm_name("Shai Gilgeous-Alexander") == "shai gilgeous alexander"


def test_combo_market_graded_from_sum(tmp_path):
    setup(tmp_path, [cap("draftkings", "Over", 50.5, -110, market="player_points_rebounds_assists")], [box("31")])
    ln = build.build(tmp_path)["lines"]["3112335"]["g1"]["player_points_rebounds_assists"]
    assert ln["act"] == 31 + 12 + 9 and ln["res"] == "over"
