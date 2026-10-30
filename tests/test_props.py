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
        if url.endswith("/markets"):
            return 200, {"bookmakers": [{"key": "draftkings", "markets": [{"key": "player_blocks"}, {"key": "player_points"}]}]}, \
                {"x-requests-remaining": "399", "x-requests-last": "1"}
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
    odds_calls = [c for c in calls if c[0].endswith("/odds")]
    assert odds_calls == [(props.BASE + "/events/soon/odds", "k2")]   # k1 has only 3 credits
    caps = (tmp_path / "prop_captures.csv").read_text().splitlines()
    assert len(caps) == 3 and "Nikola Jokic" in caps[1] and ",150," in caps[1]  # 150 min before tip
    # Second run: already captured, nothing pulled.
    calls.clear()
    s2 = props.run(tmp_path, [("ODDS_API_KEY", "k1"), ("ODDS_API_KEY_2", "k2")], NOW)
    assert s2["due"] == 0 and not [c for c in calls if "/events/" in c[0]]   # probe not due again within a week


def test_markets_probe_saved(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(props, "_get", fake_get_factory([], [200]))
    s = props.run(tmp_path, [("ODDS_API_KEY_2", "k2")], NOW)
    assert s["markets_probe"] == "ok"
    p = json.loads((tmp_path / "markets_probe.json").read_text())
    assert p["books"]["draftkings"] == ["player_blocks", "player_points"]


def test_falls_back_to_next_key_on_429(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(props, "_get", fake_get_factory(calls, [429]))
    s = props.run(tmp_path, [("ODDS_API_KEY", "k1"), ("ODDS_API_KEY_2", "k2")], NOW)
    # k2 failed with 429; k1 can't afford 4 credits -> logged, retried next run
    assert s["pulled"][0]["status"] in ("failed", "no_credits")
    assert ("soon", "pregame") not in props.done_pulls(tmp_path)[0]


def test_budget_priorities():
    from datetime import datetime, timezone
    now = datetime(2026, 10, 22, 23, 0, tzinfo=timezone.utc)   # ~9 days left in the month
    core = props.CORE
    assert props.budget(5000, now, "pregame") == core and props.budget(5000, now, "morning") == core
    assert props.budget(485, now, "morning") == core
    # Very low: morning skipped to protect pre-game pulls; pre-game still core.
    assert props.budget(150, now, "morning") is None
    assert props.budget(150, now, "pregame") == core
    assert props.budget(None, now, "morning") == core


def test_plan_morning_and_pregame():
    from datetime import datetime, timezone
    ev = lambda i, t: {"id": i, "commence_time": t, "home_team": "H", "away_team": "A"}
    events = [ev("tonight", "2026-10-23T23:00:00Z"), ev("late", "2026-10-24T02:00:00Z"),
              ev("tomorrow", "2026-10-24T23:00:00Z")]
    early = datetime(2026, 10, 23, 12, 30, tzinfo=timezone.utc)     # 7:30 AM CDT
    assert props.plan(events, set(), early) == []
    eight = datetime(2026, 10, 23, 13, 0, tzinfo=timezone.utc)      # 8:00 AM CDT
    got = [(e["id"], t) for e, t in props.plan(events, set(), eight)]
    assert got == [("tonight", "morning"), ("late", "morning")]      # 9 PM CDT tip is still today
    assert props.plan(events, {("tonight", "morning"), ("late", "morning")}, eight) == []
    hour_before = datetime(2026, 10, 23, 22, 0, tzinfo=timezone.utc)
    got = [(e["id"], t) for e, t in props.plan(events, {("tonight", "morning"), ("late", "morning")}, hour_before)]
    assert got == [("tonight", "pregame")]
    # Morning never pulled (e.g. props posted late): still no morning pull inside the pre-game window.
    got = [(e["id"], t) for e, t in props.plan(events, set(), hour_before)]
    assert got == [("tonight", "pregame"), ("late", "morning")]


def test_lines_due():
    from datetime import datetime, timezone
    from nba_tracker.__main__ import lines_due
    t = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    assert not lines_due(t("2026-10-23T12:30"), t("2026-10-22T23:00"))           # 7:30 AM CDT
    assert lines_due(t("2026-10-23T13:05"), t("2026-10-22T23:00"))               # 8:05 AM CDT
    assert not lines_due(t("2026-10-23T15:00"), t("2026-10-23T13:05"))
    assert not lines_due(t("2026-10-23T22:00"), t("2026-10-23T13:05"))           # once a day only


def test_empty_logged_once(tmp_path, monkeypatch):
    def empty_get(url, params, timeout=25.0):
        if url.endswith("/events"):
            return 200, EVENTS, {"x-requests-remaining": "400"}
        return 200, {**EVENT_ODDS, "bookmakers": []}, {"x-requests-remaining": "400", "x-requests-last": "0"}
    monkeypatch.setattr(props, "_get", empty_get)
    props.run(tmp_path, [("ODDS_API_KEY", "k")], NOW)
    props.run(tmp_path, [("ODDS_API_KEY", "k")], NOW)
    lines = (tmp_path / "pull_log.csv").read_text().splitlines()
    assert len(lines) == 2 and ",empty," in lines[1] and lines[1].endswith(",morning")


def test_migrates_old_files(tmp_path):
    old = "at,event_id,matchup,commence_utc,minutes_before,status,markets,rows,credits_last,credits_remaining,key,note\n" \
          "2026-10-22T22:50:40Z,e1,A @ B,2026-10-22T23:10:00Z,19,ok,player_points,10,4,490,ODDS_API_KEY,\n"
    (tmp_path / "pull_log.csv").write_text(old)
    props.migrate_columns(tmp_path / "pull_log.csv", props.PULL_FIELDS)
    assert props.done_pulls(tmp_path)[0] == {("e1", "pregame")}


def test_free_keys_before_paid_even_when_paid_is_richer():
    assert props.choose_key({'ODDS_API_KEY': 5, 'ODDS_API_KEY_20K': 12945}, 4) == 'ODDS_API_KEY'
    assert props.choose_key({'ODDS_API_KEY': 3, 'ODDS_API_KEY_20K': 12945}, 4) == 'ODDS_API_KEY_20K'
    assert props.choose_key({'ODDS_API_KEY': 5, 'ODDS_API_KEY_20K': 12945}, 4, {'ODDS_API_KEY'}) == 'ODDS_API_KEY_20K'
    assert props.choose_key({'ODDS_API_KEY': None, 'ODDS_API_KEY_20K': 3}, 4) is None
    assert props.choose_key({'ODDS_API_KEY': 2, 'ODDS_API_KEY_20K': 12945}, 1) == 'ODDS_API_KEY'


def test_load_keys_deduplicates_and_keeps_paid_last():
    assert props.load_keys({'ODDS_API_KEY': ' paid ', 'ODDS_API_KEY_2': 'free',
                            'ODDS_API_KEY_3': 'free', 'ODDS_API_KEY_20K': 'paid'}) == [
        ('ODDS_API_KEY_2', 'free'), ('ODDS_API_KEY_20K', 'paid')]
