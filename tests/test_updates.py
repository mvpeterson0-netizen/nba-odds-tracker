import csv
import json
from datetime import datetime, timedelta, timezone

from nba_tracker import espn, updates
from nba_tracker.boxscores import FIELDS

NOW = datetime(2026, 10, 27, 20, 0, tzinfo=timezone.utc)


def test_parse_news_keeps_only_player_tagged_items():
    raw = {"articles": [
        {"headline": "Star scores 50", "published": "2026-10-27T03:00:00Z",
         "links": {"web": {"href": "https://www.espn.com/nba/story/_/id/1"}},
         "categories": [{"type": "team", "teamId": 2}, {"type": "athlete", "athleteId": 4065648}]},
        {"headline": "League notes", "links": {"web": {"href": "https://www.espn.com/nba/story/_/id/2"}},
         "categories": [{"type": "league"}]},
        {"headline": "No link", "categories": [{"type": "athlete", "athleteId": 1}]},
    ]}
    out = espn.parse_news(raw)
    assert list(out) == ["4065648"]
    assert out["4065648"][0]["url"].startswith("https://")


def test_injury_athlete_id_from_links():
    raw = {"injuries": [{"displayName": "Hawks", "abbreviation": "ATL", "injuries": [
        {"status": "Out", "athlete": {"displayName": "A B", "links": [
            {"rel": ["playercard", "desktop", "athlete"], "href": "https://www.espn.com/nba/player/_/id/123/a-b"},
            {"rel": ["news", "desktop", "athlete"], "href": "https://www.espn.com/nba/player/news/_/id/123/a-b"}]}}]}]}
    row = espn.parse_injuries(raw)[0]
    assert row["player_id"] == "123"
    assert row["url"] == "https://www.espn.com/nba/player/news/_/id/123/a-b"


def _box(path, games):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for g in games:
            w.writerow({k: g.get(k, "") for k in FIELDS})


def _row(gid, day, aid="9", team="BOS", mins=20, starter=False, played=True):
    return {"game_id": gid, "game_date": f"2026-10-{day:02d}", "start_utc": f"2026-10-{day:02d}T23:00Z",
            "team": team, "opp": "NYK", "home_away": "home", "athlete_id": aid, "player": "Test Guy",
            "starter": str(starter), "played": str(played), "min": mins}


def _setup(tmp_path, last_min=34, last_start=True):
    rows = [_row(f"g{d}", d) for d in (20, 22, 24)] + [_row("g26", 26, mins=last_min, starter=last_start)]
    _box(tmp_path / "player_games.csv", rows)
    (tmp_path / "latest").mkdir()
    (tmp_path / "latest" / "injuries.json").write_text(json.dumps({"rows": [
        {"player_id": None, "player": "Test Guy", "team_abbr": "BOS", "status": "Day-To-Day",
         "injury": "Ankle", "comment": "Sprained it.", "updated": "2026-10-27T01:00Z"}]}))
    (tmp_path / "rosters.json").write_text(json.dumps({"BOS": {"date": "2026-10-27", "players": [
        {"id": "9", "name": "Test Guy"}]}}))
    (tmp_path / "espn_news.json").write_text(json.dumps({"news": {"9": [
        {"headline": f"h{i}", "date": (NOW - timedelta(days=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "url": f"https://www.espn.com/{i}"} for i in range(6)]}}))


def test_build_items_and_new_logic(tmp_path):
    _setup(tmp_path)
    first = updates.build(tmp_path, NOW)
    its = first["players"]["9"]
    kinds = [i["kind"] for i in its]
    assert kinds.count("ESPN") == 1 and kinds.count("ESPN news") == 3      # max 3 headlines, 7-day window
    assert any("played 34 min (prior average 20)" in i["text"] for i in its)
    assert any("started after coming off the bench" in i["text"] for i in its)
    assert all(i["t"] == "" for i in its)                                    # first run: nothing is "new"
    esp = next(i for i in its if i["kind"] == "ESPN")
    assert esp["text"] == "Day-To-Day (Ankle): Sprained it." and esp["at"] == "2026-10-27T01:00Z"

    # a later run: a new headline is stamped with Dime's detection time; old items keep a blank time
    news = json.loads((tmp_path / "espn_news.json").read_text())
    news["news"]["9"].insert(0, {"headline": "fresh", "date": "2026-10-27T19:00:00Z", "url": "https://www.espn.com/new"})
    (tmp_path / "espn_news.json").write_text(json.dumps(news))
    later = NOW + timedelta(minutes=30)
    its = updates.build(tmp_path, later)["players"]["9"]
    fresh = next(i for i in its if i["text"] == "fresh")
    assert fresh["t"] == "2026-10-27T20:30:00Z"
    assert next(i for i in its if i["kind"] == "ESPN")["t"] == ""
    seen = json.loads((tmp_path / "updates_seen.json").read_text())
    assert not any(k.endswith("https://www.espn.com/2") for k in seen)     # dropped item pruned


def test_no_role_change_when_steady(tmp_path):
    _setup(tmp_path, last_min=22, last_start=False)
    its = updates.build(tmp_path, NOW)["players"]["9"]
    assert not [i for i in its if i["kind"] == "Role"]


def test_roster_move(tmp_path):
    _setup(tmp_path)
    (tmp_path / "rosters.json").write_text(json.dumps({"NY": {"date": "2026-10-27", "players": [
        {"id": "9", "name": "Test Guy"}]}}))
    its = updates.build(tmp_path, NOW)["players"]["9"]
    assert any(i["kind"] == "Roster" and "NY roster (last played for BOS" in i["text"] for i in its)
