from datetime import datetime, timezone

from nba_tracker import props

NOW = datetime(2026, 10, 22, 23, 0, tzinfo=timezone.utc)
EVENTS = [
    {"id": "soon", "commence_time": "2026-10-23T01:30:00Z", "home_team": "Oklahoma City Thunder", "away_team": "Denver Nuggets"},
    {"id": "started", "commence_time": "2026-10-22T23:00:00Z", "home_team": "A", "away_team": "B"},
    {"id": "later", "commence_time": "2026-10-23T23:00:00Z", "home_team": "C", "away_team": "D"},
]
EVENT_ODDS = {"id": "soon", "commence_time": "2026-10-23T01:30:00Z", "home_team": "Oklahoma City Thunder",
              "away_team": "Denver Nuggets", "bookmakers": [{"key": "draftkings", "markets": [
                  {"key": "player_points", "last_update": "x", "outcomes": [
                      {"name": "Over", "description": "Nikola Jokic", "price": -115, "point": 27.5},
                      {"name": "Under", "description": "Nikola Jokic", "price": -105, "point": 27.5}]}]}]}


def fake_get_factory(calls, odds_codes):
    def fake_get(url, params, timeout=25.0):
        calls.append((url, params["apiKey"]))
        if url.endswith("/events"):
            rem = {"k1": "3", "k2": "400"}[params["apiKey"]]
            return 200, EVENTS, {"x-requests-remaining": rem, "x-requests-last": "0"}
        code = odds_codes.pop(0)
        if code == 200:
            return 200, EVENT_ODDS, {"x-requests-remaining": "396", "x-requests-last": "1"}
        return code, None, {}
    return fake_get


def test_pulls_only_due_game_with_richest_key(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(props, "_get", fake_get_factory(calls, [200]))
    s = props.run(tmp_path, [("ODDS_API_KEY", "k1"), ("ODDS_API_KEY_2", "k2")], NOW)
    assert s["status"] == "ok" and s["due"] == 1
    odds_calls = [c for c in calls if "/events/" in c[0]]
    assert odds_calls == [(props.BASE + "/events/soon/odds", "k2")]   # k1 has only 3 credits
    caps = (tmp_path / "prop_captures.csv").read_text().splitlines()
    assert len(caps) == 3 and "Nikola Jokic" in caps[1] and ",150," in caps[1]  # 150 min before tip
    # Second run: already captured, nothing pulled.
    calls.clear()
    s2 = props.run(tmp_path, [("ODDS_API_KEY", "k1"), ("ODDS_API_KEY_2", "k2")], NOW)
    assert s2["due"] == 0 and not [c for c in calls if "/events/" in c[0]]


def test_falls_back_to_next_key_on_429(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(props, "_get", fake_get_factory(calls, [429]))
    s = props.run(tmp_path, [("ODDS_API_KEY", "k1"), ("ODDS_API_KEY_2", "k2")], NOW)
    # k2 failed with 429; k1 can't afford 4 credits -> logged, retried next run
    assert s["pulled"][0]["status"] in ("failed", "no_credits")
    assert "soon" not in props.captured_events(tmp_path)
