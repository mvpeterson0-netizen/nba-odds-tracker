"""Run one collection pass: `python -m nba_tracker`.

Writes:
  data/latest/<name>.json              — most recent snapshot (overwritten)
  data/history/<YYYY-MM-DD>/<name>.json — daily archive
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

from . import boxscores, espn, odds, props

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


# Game lines (moneyline/spread/total for every game, one 3-credit call) are pulled once a
# day, at the first run at or after 8:00 AM Central. Not shown on the site yet; kept in
# data/latest/odds.json and the monthly odds_log CSV.
CENTRAL = ZoneInfo("America/Chicago")


def lines_due(now: datetime, last: datetime | None) -> bool:
    local = now.astimezone(CENTRAL)
    eight = local.replace(hour=8, minute=0, second=0, microsecond=0)
    return local >= eight and (last is None or last < eight)


def _last_lines_pull(out: Path) -> datetime | None:
    try:
        f = json.loads((out / "latest" / "odds.json").read_text(encoding="utf-8"))["fetched_at"]
        return datetime.fromisoformat(f)
    except Exception:
        return None


def run(out: Path, day: date, skip_odds: bool = False) -> int:
    failures = 0
    status: dict[str, str] = {}
    extra_info: dict = {}
    jobs = [
        ("games_today", lambda: espn.parse_scoreboard(espn.fetch_scoreboard(day)),
         {"game_date": day.isoformat()}),
        ("results_yesterday",
         lambda: espn.parse_scoreboard(espn.fetch_scoreboard(day - timedelta(days=1))),
         {"game_date": (day - timedelta(days=1)).isoformat()}),
        ("games_tomorrow",
         lambda: espn.parse_scoreboard(espn.fetch_scoreboard(day + timedelta(days=1))),
         {"game_date": (day + timedelta(days=1)).isoformat()}),
        ("standings", lambda: espn.parse_standings(espn.fetch_standings()), {}),
        ("injuries", lambda: espn.parse_injuries(espn.fetch_injuries()), {}),
    ]
    for name, job, extra in jobs:
        try:
            rows = job()
            write(out, day, name, envelope("espn", rows, **extra))
            log.info("%-18s %d rows", name, len(rows))
            status[name] = "ok"
        except Exception as e:  # keep going so one bad endpoint doesn't sink the run
            failures += 1
            status[name] = "failed"
            log.error("%s failed: %s", name, e)

    try:
        extra_info["boxscores"] = boxscores.run(out, day)
        status["boxscores"] = "ok"
    except Exception as e:
        failures += 1
        status["boxscores"] = "failed"
        extra_info["boxscores"] = {"error": f"{type(e).__name__}: {e}"[:500]}
        log.exception("boxscores failed")

    keys = props.load_keys(dict(os.environ))
    now = datetime.now(timezone.utc)
    if skip_odds:
        status["odds"] = status["props"] = "skipped"
    elif not keys:
        log.info("odds/props        skipped (no ODDS_API_KEY set)")
        status["odds"] = status["props"] = "no_key"
    else:
        # Player props: checked every run, pulled once per game ~3 h before tip.
        try:
            psum = props.run(out, keys, now)
            status["props"] = psum["status"]
            extra_info["props"] = psum
            if psum["status"] == "failed":
                failures += 1
        except Exception as e:
            failures += 1
            status["props"] = "failed"
            log.error("props failed: %s", e)
        # Game lines (moneyline/spread/total): only in the scheduled slots, to save credits.
        last = _last_lines_pull(out)
        if not lines_due(now, last):
            status["odds"] = "not_due"
            log.info("odds              not due (last pull %s)", last)
        else:
            try:
                raw = quota = None
                for label, key in keys:
                    try:
                        raw, quota = odds.fetch_odds(key)
                        quota["key"] = label
                        break
                    except Exception as e:  # bad/empty key: try the next one
                        log.warning("odds with %s failed: %s", label, e)
                if raw is None:
                    raise RuntimeError("every key failed")
                fetched = now.strftime("%Y-%m-%dT%H:%M:%SZ")
                rows = odds.parse_odds(raw, fetched)
                write(out, day, "odds", envelope("the-odds-api", rows, quota=quota))
                # Every pull is also appended to a permanent log (one CSV per month).
                odds.append_log(out / "odds_log" / f"{fetched[:7]}.csv", rows, fetched)
                log.info("odds              %d rows (quota remaining: %s)", len(rows), quota.get("requests_remaining"))
                status["odds"] = "ok"
            except Exception as e:
                failures += 1
                status["odds"] = "failed"
                log.error("odds failed: %s", e)
    # Run summary, read by the website's status line.
    (out / "latest").mkdir(parents=True, exist_ok=True)
    (out / "latest" / "run.json").write_text(json.dumps({
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "game_date": day.isoformat(),
        "repo": os.environ.get("GITHUB_REPOSITORY", "mvpeterson0-netizen/nba-odds-tracker"),
        "sources": status,
        **extra_info,
    }, indent=2) + "\n", encoding="utf-8")
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
