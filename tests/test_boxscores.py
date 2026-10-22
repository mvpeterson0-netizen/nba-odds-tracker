from nba_tracker import boxscores

GAME = {"game_id": "1", "game_date": "2026-10-21", "start_utc": "2026-10-21T23:00Z",
        "home": {"team_id": "9", "abbr": "GS"}, "away": {"team_id": "2", "abbr": "BOS"}}
SUMMARY = {"boxscore": {"players": [{
    "team": {"id": "9", "abbreviation": "GS"},
    "statistics": [{
        "labels": ["MIN", "FG", "3PT", "FT", "OREB", "DREB", "REB", "AST", "STL", "BLK", "TO", "PF", "+/-", "PTS"],
        "athletes": [
            {"athlete": {"id": "3136776", "displayName": "Stephen Curry", "position": {"abbreviation": "PG"}},
             "starter": True, "didNotPlay": False,
             "stats": ["36", "12-24", "4-10", "4-4", "0", "5", "5", "7", "1", "0", "2", "2", "+8", "32"]},
            {"athlete": {"id": "9", "displayName": "Bench Guy"}, "didNotPlay": True, "reason": "COACH'S DECISION", "stats": []},
        ]}]}]}}


def test_parse_summary():
    rows = boxscores.parse_summary(SUMMARY, GAME)
    c, b = rows
    assert (c["pts"], c["reb"], c["ast"], c["fg3m"], c["fg3a"], c["min"]) == (32, 5, 7, 4, 10, 36)
    assert c["team"] == "GS" and c["opp"] == "BOS" and c["home_away"] == "home" and c["played"] and c["starter"]
    assert b["played"] is False and b["dnp_reason"] == "COACH'S DECISION"


def test_parse_summary_empty():
    assert boxscores.parse_summary({"boxscore": {"teams": [{"team": {"id": "9"}, "statistics": []}]}}, GAME) == []
