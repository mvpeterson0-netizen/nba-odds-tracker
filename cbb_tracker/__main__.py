"""Run one college basketball pass: `python -m cbb_tracker`.

Writes (under data/cbb/):
  latest/<name>.json              most recent snapshot (overwritten): results_yesterday, games_today, games_tomorrow
  history/<YYYY-MM-DD>/<name>.json daily archive
  latest/run.json                 run summary read by the website's status line
Only Power 4 games are kept (see espn.py). Player points props go to prop_captures.csv / pull_log.csv.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from nba_tracker.__main__ import envelope, write

from . import boxscores, espn, props

log = logging.getLogger("cbb_tracker")
ET = ZoneInfo("America/New_York")


def run(out: Path, day: date, skip_odds: bool = False) -> int:
    failures = 0
    status: dict[str, str] = {}
    extra: dict = {}
    sb = boxscores.Scoreboards()
    all_games: list[dict] = []
    today_p4: list[dict] = []
    for name, d in (("results_yesterday", day - timedelta(days=1)), ("games_today", day), ("games_tomorrow", day + timedelta(days=1))):
        try:
            games = sb.get(d)
            all_games.extend(games)
            p4 = espn.p4_only(games)
            write(out, day, name, envelope("espn", p4, game_date=d.isoformat(), division_i_games=len(games)))
            if name == "games_today":
                today_p4 = p4
            status[name] = "ok"
            log.info("%-18s %d Power 4 of %d games", name, len(p4), len(games))
        except Exception as e:      # one bad day shouldn't sink the run
            failures += 1
            status[name] = "failed"
            log.error("%s failed: %s", name, e)

    try:
        extra["boxscores"] = boxscores.run(out, day, sb, today_p4)
        status["boxscores"] = "ok"
    except Exception as e:
        failures += 1
        status["boxscores"] = "failed"
        extra["boxscores"] = {"error": f"{type(e).__name__}: {e}"[:500]}
        log.exception("boxscores failed")

    keys = props.load_keys(dict(os.environ))
    if skip_odds:
        status["props"] = "skipped"
    elif not keys:
        log.info("props             skipped (no ODDS_API_KEY set)")
        status["props"] = "no_key"
    else:
        try:
            psum = props.run(out, keys, all_games, day, datetime.now(timezone.utc))
            status["props"] = psum["status"]
            extra["props"] = psum
            if psum["status"] == "failed":
                failures += 1
        except Exception as e:
            failures += 1
            status["props"] = "failed"
            log.error("props failed: %s", e)

    (out / "latest").mkdir(parents=True, exist_ok=True)
    (out / "latest" / "run.json").write_text(json.dumps({
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "game_date": day.isoformat(),
        "repo": os.environ.get("GITHUB_REPOSITORY", "mvpeterson0-netizen/nba-odds-tracker"),
        "power4": sorted(espn.P4_CONFERENCES.values()), "p4_mode": espn.P4_MODE,
        "sources": status,
        **extra,
    }, indent=2) + "\n", encoding="utf-8")
    return failures


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Pull Power 4 college basketball games, box scores and player-points lines.")
    p.add_argument("--date", help="Game date YYYY-MM-DD (default: today, US Eastern)")
    p.add_argument("--out", default="data/cbb", help="Output folder (default: data/cbb)")
    p.add_argument("--skip-odds", action="store_true", help="Don't call the odds API")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    day = date.fromisoformat(args.date) if args.date else datetime.now(ET).date()
    failures = run(Path(args.out), day, args.skip_odds)
    if failures:
        log.error("%d source(s) failed", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
