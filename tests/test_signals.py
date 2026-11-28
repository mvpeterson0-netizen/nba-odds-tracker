from pathlib import Path

from nba_tracker import signals

DATA = Path(__file__).resolve().parents[1] / "data"


def test_signals_build_shape():
    d = signals.build(DATA)
    ids = [s["id"] for s in d["signals"]]
    assert ids == [s["id"] for s in signals.SIGNALS] and len(set(ids)) == 6
    for s in d["signals"]:
        assert s["kind"] in ("team", "player") and s["gates"]
        for b in s["bets"]:
            assert b["res"] in ("W", "L", "P") and b["wk"] >= 1
            assert (b["u"] == -1.0) if b["res"] == "L" else (b["u"] >= 0)


def test_grade():
    assert signals._grade(1.5, -110) == ("W", round(100 / 110, 4))
    assert signals._grade(-0.5, -110) == ("L", -1.0)
    assert signals._grade(0, -110) == ("P", 0.0)


def test_team_plays_carry_slip_links(tmp_path):
    import shutil
    shutil.copytree(DATA, tmp_path / "d", ignore=shutil.ignore_patterns("history", "cbb", "odds_log"))
    shutil.copytree(DATA / "odds_log", tmp_path / "d" / "odds_log")
    base = signals.build(tmp_path / "d")
    plays = [p for s in base["signals"] if s["kind"] == "team" for p in s["plays"]]
    if not plays:
        return   # no upcoming team plays in this snapshot
    assert all(p.get("links") is None for p in plays)   # no game_links.csv yet
