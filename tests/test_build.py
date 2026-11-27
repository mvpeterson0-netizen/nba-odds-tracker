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


def test_pregame_line_graded_and_morning_kept(tmp_path):
    am = cap("draftkings", "Over", 26.5, -110, mb=600)
    am.update(captured_at="2026-10-22T15:40:00Z", pull_type="morning")
    pre = cap("draftkings", "Over", 28.5, -115, mb=60)
    pre.update(captured_at="2026-10-23T00:40:00Z", pull_type="pregame")
    setup(tmp_path, [am, pre], [box("28")])
    ln = build.build(tmp_path)["lines"]["3112335"]["g1"]["player_points"]
    assert ln["line"] == 28.5 and ln["pt"] == "pregame" and ln["am"]["line"] == 26.5 and ln["res"] == "under"


def test_estimate_combo_offsets_and_price():
    from nba_tracker.build import estimate_combo
    parts = {"player_points": {"line": 13.5, "pt": "pregame", "book": "draftkings", "cap": "a", "mb": 60},
             "player_rebounds": {"line": 5.5, "pt": "pregame", "book": "draftkings", "cap": "b", "mb": 61},
             "player_assists": {"line": 3.5, "pt": "morning", "book": "draftkings", "cap": "c", "mb": 500}}
    pr = estimate_combo("player_points_rebounds", parts)
    assert pr["line"] == 19.5 and pr["op"] == pr["up"] == -110 and pr["est"] and pr["pt"] == "pregame"
    pra = estimate_combo("player_points_rebounds_assists", parts)
    assert pra["line"] == 22.5 and pra["pt"] == "morning"
    assert estimate_combo("player_points_assists", {"player_points": parts["player_points"]}) is None


def test_estimated_combo_carries_8am_line():
    from nba_tracker.build import estimate_combo
    p = {"player_points": {"line": 20.5, "pt": "pregame", "book": "draftkings", "am": {"line": 19.5}},
         "player_rebounds": {"line": 7.5, "pt": "pregame", "book": "draftkings", "am": {"line": 7.5}}}
    e = estimate_combo("player_points_rebounds", p)
    assert e["line"] == 28.5 and e["am"]["line"] == 27.5
    p["player_rebounds"].pop("am")
    assert "am" not in estimate_combo("player_points_rebounds", p)


def link_row(side, point, price, url=None, book="fanduel", commence="2026-10-23T01:40:00Z"):
    return {"event_id": "e1", "commence_utc": commence, "pull_type": "pregame", "captured_at": "2026-10-22T22:50:00Z",
            "book": book, "market": "player_points", "player": "Nikola Jokić", "side": side, "point": point,
            "price": price, "outcome_link": url or f"https://sportsbook.fanduel.com/addToBetslip?marketId=1&selectionId={side}"}


def test_fanduel_links_before_tip_only(tmp_path):
    from datetime import datetime, timezone
    setup(tmp_path, [cap("draftkings", "Over", 27.5, -115)], [box("31")])
    w(tmp_path / "prop_links.csv", [link_row("Over", 27.5, -112), link_row("Under", 27.5, -108),
                                    link_row("Over", 29.5, 140), link_row("Over", 27.5, -110, book="draftkings"),
                                    link_row("Under", 27.5, -110, url="https://evil.example/x")])
    before = datetime(2026, 10, 22, 23, 0, tzinfo=timezone.utc)
    fd = build.build(tmp_path, before)["links"]["3112335"]["player_points"]["fanduel"]
    assert fd["point"] == 27.5 and fd["gid"] == "g1"          # the point with both sides, closest to even money
    assert fd["o"]["price"] == -112 and fd["u"]["price"] == -108 and "selectionId=Over" in fd["o"]["url"]
    after = datetime(2026, 10, 23, 2, 0, tzinfo=timezone.utc)
    assert build.build(tmp_path, after)["links"] == {}          # game has tipped: no links


# ---------- other books (Arbitrage tab) ----------
OTHER_FIELDS = ["captured_at", "event_id", "minutes_before", "pull_type", "book", "market", "player", "side", "point", "price"]


def oth(book, side, point, price, at="2026-10-22T22:50:00Z", player="Nikola Jokić", market="player_points", pt="pregame"):
    return {"captured_at": at, "event_id": "e1", "minutes_before": 170, "pull_type": pt, "book": book, "market": market,
            "player": player, "side": side, "point": point, "price": price}


def test_books_block_latest_pull_novig_rung_and_filters(tmp_path):
    from datetime import datetime, timezone
    setup(tmp_path, [cap("draftkings", "Over", 27.5, -115), cap("draftkings", "Under", 27.5, -105),
                     cap("fanduel", "Over", 28.5, -110), cap("fanduel", "Under", 28.5, -110),
                     # an older pull of the same game must not leak into the block
                     {**cap("draftkings", "Over", 25.5, -110), "captured_at": "2026-10-22T12:00:00Z"}],
          [box("31")])
    (tmp_path / "other_books").mkdir()
    rows = [oth("betmgm", "Over", 27.5, -110), oth("betmgm", "Under", 27.5, -110),
            oth("betmgm", "Over", 30.5, 150),                                    # one-sided alt: ignored while a two-sided point exists
            oth("betmgm", "Under", 26.5, -110, at="2026-10-22T12:00:00Z"),       # older pull
            oth("novig", "Over", 26.5, -105), oth("novig", "Under", 26.5, -105),
            oth("novig", "Over", 27.5, -112), oth("novig", "Under", 27.5, -108),  # the DraftKings rung: the one shown
            oth("novig", "Over", 29.5, 120), oth("novig", "Under", 29.5, -140),
            oth("betmgm", "Over", 20.5, -110, market="player_points_rebounds_assists"),   # not a real core line: dropped
            oth("betmgm", "Over", 5.5, -110, player="Somebody Unknown")]                  # unmatched player: dropped
    w(tmp_path / "other_books" / "2026-10.csv", rows)
    before = datetime(2026, 10, 22, 23, 0, tzinfo=timezone.utc)
    b = build.build(tmp_path, before)["books"]
    g = b["g1"]
    assert g["cap"] == "2026-10-22T22:50:00Z" and g["pt"] == "pregame"
    by_book = {r[0]: r for r in g["p"]["3112335"]["player_points"]}
    assert set(by_book) == {"draftkings", "fanduel", "betmgm", "novig"}
    assert by_book["betmgm"][1:] == [27.5, -110, -110]
    assert by_book["novig"][1:] == [27.5, -112, -108]          # at the DraftKings line
    assert by_book["fanduel"][1] == 28.5
    assert "player_points_rebounds_assists" not in g["p"]["3112335"]
    # after tip-off nothing is shown
    after = datetime(2026, 10, 23, 2, 0, tzinfo=timezone.utc)
    assert build.build(tmp_path, after)["books"] == {}


def test_books_block_needs_two_books(tmp_path):
    from datetime import datetime, timezone
    setup(tmp_path, [cap("draftkings", "Over", 27.5, -115), cap("draftkings", "Under", 27.5, -105)], [box("31")])
    (tmp_path / "other_books").mkdir()
    w(tmp_path / "other_books" / "2026-10.csv", [oth("betmgm", "Over", 1.5, -110, player="Somebody Unknown")])
    assert build.build(tmp_path, datetime(2026, 10, 22, 23, 0, tzinfo=timezone.utc))["books"] == {}
    assert build.build(tmp_path, datetime(2026, 10, 22, 23, 0, tzinfo=timezone.utc))["lines"]   # the rest is unaffected
