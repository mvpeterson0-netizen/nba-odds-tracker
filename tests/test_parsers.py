"""Parser tests against small, hand-built payloads shaped like ESPN / Odds API responses.

The fixtures are illustrative, not captured live responses — re-check them against
real payloads once the workflow has run and saved data.
"""

from nba_tracker import espn, odds

SCOREBOARD = {
    "events": [{
        "id": "401",
        "date": "2026-10-22T23:30Z",
        "shortName": "BOS @ NY",
        "status": {"period": 4, "displayClock": "0.0",
                   "type": {"state": "post", "completed": True, "shortDetail": "Final"}},
        "competitions": [{
            "venue": {"fullName": "Madison Square Garden"},
            "broadcasts": [{"names": ["ESPN"]}],
            "odds": [{"provider": {"name": "ESPN BET"}, "details": "NY -2.5",
                      "spread": -2.5, "overUnder": 221.5}],
            "competitors": [
                {"homeAway": "home", "score": "110", "winner": True,
                 "team": {"id": "18", "abbreviation": "NY", "displayName": "New York Knicks"},
                 "records": [{"name": "overall", "summary": "1-0"}],
                 "leaders": [{"name": "points", "leaders": [
                     {"displayValue": "31", "athlete": {"displayName": "Player A"}}]}]},
                {"homeAway": "away", "score": "104", "winner": False,
                 "team": {"id": "2", "abbreviation": "BOS", "displayName": "Boston Celtics"}},
            ],
        }],
    }]
}

STANDINGS = {"children": [{
    "name": "Eastern Conference",
    "standings": {"entries": [{
        "team": {"id": "2", "abbreviation": "BOS", "displayName": "Boston Celtics"},
        "stats": [
            {"name": "wins", "value": 1.0, "displayValue": "1"},
            {"name": "losses", "value": 0.0, "displayValue": "0"},
            {"name": "streak", "displayValue": "W1"},
        ],
    }]},
}]}

INJURIES = {"injuries": [
    {"id": "9", "displayName": "Golden State Warriors",
     "injuries": [{"status": "Out", "date": "2026-10-20T00:00Z", "shortComment": "Knee.",
                   "athlete": {"id": "1", "displayName": "Player B",
                               "position": {"abbreviation": "G"}},
                   "details": {"type": "Knee", "returnDate": "2026-11-01"}}]},
    {"team": {"id": "13", "abbreviation": "LAL", "displayName": "Los Angeles Lakers"},
     "injuries": [{"status": "Day-To-Day", "type": {"name": "ankle"},
                   "athlete": {"id": "2", "displayName": "Player C"}}]},
]}

ODDS = [{
    "id": "abc", "commence_time": "2026-10-23T00:00:00Z",
    "home_team": "New York Knicks", "away_team": "Boston Celtics",
    "bookmakers": [{"key": "draftkings", "markets": [
        {"key": "spreads", "last_update": "2026-10-22T18:00:00Z", "outcomes": [
            {"name": "New York Knicks", "price": -110, "point": -2.5},
            {"name": "Boston Celtics", "price": -110, "point": 2.5}]},
        {"key": "h2h", "outcomes": [{"name": "New York Knicks", "price": -140}]},
    ]}],
}]


def test_scoreboard():
    (g,) = espn.parse_scoreboard(SCOREBOARD)
    assert g["home"]["abbr"] == "NY" and g["home"]["score"] == 110 and g["home"]["winner"]
    assert g["away"]["abbr"] == "BOS" and g["away"]["score"] == 104
    assert g["home"]["record"] == "1-0"
    assert g["home"]["leaders"]["points"] == {"player": "Player A", "value": "31"}
    assert g["state"] == "post" and g["completed"] is True
    assert g["broadcasts"] == ["ESPN"]
    assert g["espn_line"]["over_under"] == 221.5


def test_scoreboard_handles_empty_and_missing():
    assert espn.parse_scoreboard({}) == []
    assert espn.parse_scoreboard(None) == []
    (g,) = espn.parse_scoreboard({"events": [{"id": "1"}]})
    assert g["home"]["abbr"] is None and g["espn_line"] is None


def test_standings():
    (row,) = espn.parse_standings(STANDINGS)
    assert row["conference"] == "Eastern Conference" and row["abbr"] == "BOS"
    assert row["stats"]["wins"] == 1.0 and row["stats"]["wins_display"] == "1"
    assert row["stats"]["streak"] == "W1"


def test_injuries_both_team_shapes():
    rows = espn.parse_injuries(INJURIES)
    assert [r["team"] for r in rows] == ["Golden State Warriors", "Los Angeles Lakers"]
    assert rows[0]["injury"] == "Knee" and rows[0]["return_date"] == "2026-11-01"
    assert rows[1]["team_abbr"] == "LAL" and rows[1]["injury"] == "ankle"


def test_odds():
    rows = odds.parse_odds(ODDS)
    assert len(rows) == 3
    assert rows[0] == {
        "event_id": "abc", "commence_utc": "2026-10-23T00:00:00Z",
        "home_team": "New York Knicks", "away_team": "Boston Celtics",
        "book": "draftkings", "market": "spreads", "market_updated": "2026-10-22T18:00:00Z",
        "outcome": "New York Knicks", "price": -110, "point": -2.5, "in_play": False,
    }
    assert rows[2]["point"] is None


def test_odds_key_optional(monkeypatch):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    assert odds.api_key() is None
    monkeypatch.setenv("ODDS_API_KEY", "  ")
    assert odds.api_key() is None


def test_errors_redact_api_key():
    import pytest
    import requests
    from nba_tracker.http import FetchError, get_json

    class Boom:
        def get(self, url, **kw):
            raise requests.ConnectionError(f"failed {url}?apiKey={kw['params']['apiKey']}")

    with pytest.raises(FetchError) as exc:
        get_json("https://example.test/odds", {"apiKey": "SECRET123"},
                 retries=2, backoff=0, session=Boom())
    assert "SECRET123" not in str(exc.value) and "***" in str(exc.value)


def test_in_play_flag_and_log(tmp_path):
    import csv
    rows = odds.parse_odds(ODDS, "2026-10-22T23:00:00Z")
    assert all(r["in_play"] is False for r in rows)
    assert all(r["in_play"] is True for r in odds.parse_odds(ODDS, "2026-10-23T01:00:00Z"))
    p = tmp_path / "log.csv"
    odds.append_log(p, rows, "2026-10-22T23:00:00Z")
    odds.append_log(p, rows, "2026-10-22T23:30:00Z")
    got = list(csv.DictReader(p.open()))
    assert len(got) == 6 and got[0]["fetched_at"] == "2026-10-22T23:00:00Z" and got[0]["point"] == "-2.5"


def test_backup_key_names(monkeypatch):
    for v in odds.KEY_VARS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("ODDS_API_KEY_3", "k3")
    assert odds.api_key() == "k3"
