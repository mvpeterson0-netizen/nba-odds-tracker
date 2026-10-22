"""Run one collection pass: `python -m nba_tracker`.

Writes:
  data/latest/<name>.json              — most recent snapshot (overwritten)
  data/history/<YYYY-MM-DD>/<name>.json — daily archive
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import espn, odds

log = logging.getLogger("nba_tracker")

# The NBA schedules its "day" on US Eastern time.
NBA_TZ = ZoneInfo("America/New_York")


def write(out: Path, day: date, name: str, payload: dict) -> None:
    for folder in (out / "latest", out / "history" / day.isoformat()):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{name}.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def envelope(source: str, rows: list, **extra) -> dict:
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "count": len(rows),
        **extra,
        "rows": rows,
    }


def run(out: Path, day: date, skip_odds: bool = False) -> int:
    failures = 0
    jobs = [
        ("games_today", lambda: espn.parse_scoreboard(espn.fetch_scoreboard(day)),
         {"game_date": day.isoformat()}),
        ("results_yesterday",
         lambda: espn.parse_scoreboard(espn.fetch_scoreboard(day - timedelta(days=1))),
         {"game_date": (day - timedelta(days=1)).isoformat()}),
        ("standings", lambda: espn.parse_standings(espn.fetch_standings()), {}),
        ("injuries", lambda: espn.parse_injuries(espn.fetch_injuries()), {}),
    ]
    for name, job, extra in jobs:
        try:
            rows = job()
            write(out, day, name, envelope("espn", rows, **extra))
            log.info("%-18s %d rows", name, len(rows))
        except Exception as e:  # keep going so one bad endpoint doesn't sink the run
            failures += 1
            log.error("%s failed: %s", name, e)

    key = odds.api_key()
    if skip_odds:
        log.info("odds              skipped (--skip-odds)")
    elif not key:
        log.info("odds              skipped (ODDS_API_KEY not set)")
    else:
        try:
            raw, quota = odds.fetch_odds(key)
            rows = odds.parse_odds(raw)
            write(out, day, "odds", envelope("the-odds-api", rows, quota=quota))
            log.info("odds              %d rows (quota remaining: %s)",
                     len(rows), quota.get("requests_remaining"))
        except Exception as e:
            failures += 1
            log.error("odds failed: %s", e)
    return failures


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Pull NBA stats (and odds, if keyed).")
    p.add_argument("--date", help="Game date YYYY-MM-DD (default: today, US Eastern)")
    p.add_argument("--out", default="data", help="Output folder (default: data)")
    p.add_argument("--skip-odds", action="store_true", help="Don't call the odds API")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    day = date.fromisoformat(args.date) if args.date else datetime.now(NBA_TZ).date()
    failures = run(Path(args.out), day, args.skip_odds)
    if failures:
        log.error("%d source(s) failed", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
