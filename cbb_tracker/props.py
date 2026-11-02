"""College basketball player-points capture from The Odds API (v4), Power 4 games only.

Player points are pulled ONCE per game, in the morning (PROP_PULLS):
  morning  — first run at or after 8:00 AM Central on game day; retried at most about hourly until the books post
             props or the game tips. This is the graded line (there is no later pull to replace it).
Add "pregame" to PROP_PULLS to also capture within ~70 minutes of tip.
Game spreads and totals are separate (lines.py): 8 AM and about 1 hour before tip.

Each run:
  1. Free /events call with every key: upcoming games, and each key's remaining credits.
  2. Keeps only events that match a Power 4 game on ESPN's scoreboard (see teams.py). Events that match no ESPN
     game at all are listed in the run summary so a naming mismatch is visible instead of silent.
  3. One call per due game for the points market only (1 credit; an empty answer is free), DraftKings and FanDuel.
  4. Appends prices to data/cbb/prop_captures.csv and every attempt to data/cbb/pull_log.csv (append-only).

The credits are shared with the NBA pulls. The NBA pre-game pulls come first: college never spends credits
the NBA pre-game pulls will need for the rest of the month.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from nba_tracker import props as nba
from nba_tracker.props import (BOOKS, CAPTURE_FIELDS, CENTRAL, MORNING_AT, PREGAME_WINDOW, PULL_FIELDS, _append_csv,
                               _credits, _days_left, _get, choose_key, done_pulls, iso, load_keys, migrate_columns,
                               parse_event_props, parse_iso, utcnow)

from .teams import find_game

log = logging.getLogger(__name__)

BASE = "https://api.the-odds-api.com/v4/sports/basketball_ncaab"
MARKETS = ["player_points"]
ET = ZoneInfo("America/New_York")

CBB_GAMES_PER_DAY_EST = 12                      # Power 4 games a day that books post props for (rough)
NBA_PREGAME_PER_DAY = len(nba.CORE) * nba.GAMES_PER_DAY_EST    # credits/day the NBA pre-game pulls need
RETRY_EMPTY = timedelta(minutes=55)             # re-ask for a morning line at most about hourly
PROP_PULLS = ("morning",)                       # when player points are pulled: "morning", and optionally "pregame"


def classify(events: list[dict], games: list[dict], now: datetime, end: datetime) -> tuple[list[tuple[dict, dict]], list[str]]:
    """Upcoming odds events -> ([(event, ESPN game)] for Power 4 games, names of events matching no ESPN game)."""
    p4, unmatched = [], []
    for ev in events:
        try:
            start = parse_iso(ev["commence_time"])
        except (KeyError, ValueError, TypeError):
            continue
        if start <= now or start > end:
            continue
        g = find_game(ev.get("home_team"), ev.get("away_team"), ev["commence_time"], games)
        if g is None:
            unmatched.append(f"{ev.get('away_team')} @ {ev.get('home_team')}")
        elif g.get("p4"):
            p4.append((ev, g))
    return p4, unmatched


def plan(p4_events: list[tuple[dict, dict]], done: set, last_empty: dict[str, datetime], now: datetime) -> list[tuple[dict, dict, str]]:
    """Games due this run, as (event, ESPN game, pull_type)."""
    local = now.astimezone(CENTRAL)
    morning_open = local.time() >= MORNING_AT
    out = []
    for ev, g in p4_events:
        start, eid = parse_iso(ev["commence_time"]), ev.get("id")
        if start <= now:
            continue
        if "pregame" in PROP_PULLS and start - now <= PREGAME_WINDOW:
            if (eid, "pregame") not in done:
                out.append((ev, g, "pregame"))
        elif "morning" in PROP_PULLS and morning_open and start.astimezone(CENTRAL).date() == local.date() \
                and (eid, "morning") not in done:
            if eid in last_empty and now - last_empty[eid] < RETRY_EMPTY:
                continue
            out.append((ev, g, "morning"))
    return sorted(out, key=lambda x: (x[2] != "pregame", x[0]["commence_time"]))


def credits_ok(total: int | None, now: datetime, pull_type: str, cost: int = len(MARKETS)) -> bool:
    """Whether college may spend `cost` credits now. Pre-game: only the NBA's pre-game needs through month end are
    kept back. Morning: also keeps back college's own estimated pre-game pulls. Unknown balance: go ahead."""
    if total is None:
        return True
    left = _days_left(now)
    need = NBA_PREGAME_PER_DAY * left + nba.GUARD_RESERVE + cost
    if pull_type == "morning" and "pregame" in PROP_PULLS:
        need += CBB_GAMES_PER_DAY_EST * left
    return total >= need


def _snapshot_credits(data_dir: Path, remaining: dict) -> None:
    """data/cbb/credit_log.csv: each key's balance, written only when a balance changed (the /events call is free).
    Balances cover ALL use of the key (NBA included), so college's own share comes from the pull logs."""
    path = data_dir / "credit_log.csv"
    row = {"at": iso(utcnow())}
    row.update({f"{k}": v for k, v in sorted(remaining.items())})
    try:
        last = path.read_text().strip().splitlines()[-1].split(",") if path.exists() else None
        header = path.read_text().splitlines()[0].split(",") if path.exists() else None
    except Exception:
        last = header = None
    cols = ["at"] + sorted(remaining)
    if header == cols and last and last[1:] == [str(row[c]) if row[c] is not None else "" for c in cols[1:]]:
        return
    if header and header != cols:                       # a key was added or removed: start a new file
        path.rename(path.with_name(f"credit_log_{iso(utcnow())[:10]}.csv"))
    _append_csv(path, cols, [row])


def _load_state(path: Path) -> dict[str, datetime]:
    try:
        return {k: parse_iso(v) for k, v in json.loads(path.read_text())["empty"].items()}
    except Exception:
        return {}


def _save_state(path: Path, empty: dict[str, datetime]) -> None:
    path.write_text(json.dumps({"empty": {k: iso(v) for k, v in sorted(empty.items())}}, indent=0))


def run(data_dir: Path, keys: list[tuple[str, str]], games: list[dict], day: date, now: datetime | None = None) -> dict:
    """One capture pass. `games` are every Division I game on ESPN's yesterday/today/tomorrow scoreboards."""
    now = now or utcnow()
    summary: dict[str, Any] = {"keys": len(keys), "credits": {}, "pulled": [], "errors": []}
    if not keys:
        summary["status"] = "no_key"
        return summary
    data_dir.mkdir(parents=True, exist_ok=True)

    events: list[dict] | None = None
    remaining: dict[str, int | None] = {}
    for label, key in keys:
        code, body, h = _get(f"{BASE}/events", {"apiKey": key, "dateFormat": "iso"})
        _, rem = _credits(h)
        remaining[label] = rem if code == 200 else (0 if code in (401, 429) else None)
        if code == 200 and events is None and isinstance(body, list):
            events = body
        elif code != 200:
            summary["errors"].append(f"{label}: events HTTP {code or h.get('error')}")
    summary["credits"] = remaining
    _snapshot_credits(data_dir, remaining)
    if events is None:
        summary["status"] = "failed"
        return summary

    end = datetime.combine(day + timedelta(days=2), time(0), tzinfo=ET)     # end of tomorrow (ET): the scoreboards' reach
    p4_events, unmatched = classify(events, games, now, end)
    summary.update({"events": len(events), "p4_events": len(p4_events), "unmatched": unmatched[:30]})

    migrate_columns(data_dir / "prop_captures.csv", CAPTURE_FIELDS)
    migrate_columns(data_dir / "pull_log.csv", PULL_FIELDS)
    done, empty_logged = done_pulls(data_dir)
    state_path = data_dir / "props_state.json"
    live_ids = {e.get("id") for e in events}
    last_empty = {k: v for k, v in _load_state(state_path).items() if k in live_ids}
    due = plan(p4_events, done, last_empty, now)
    summary["due"], summary["pregame_pulled"] = len(due), False
    log_rows, cap_rows = [], []

    for ev, g, ptype in due:
        start = parse_iso(ev["commence_time"])
        mins = int((start - now).total_seconds() // 60)
        matchup = f"{ev.get('away_team')} @ {ev.get('home_team')}"
        total = None if any(v is None for v in remaining.values()) else sum(v for v in remaining.values())
        if not credits_ok(total, now, ptype):
            if (ev["id"], ptype) not in empty_logged:
                log_rows.append({"at": iso(utcnow()), "event_id": ev["id"], "matchup": matchup, "commence_utc": ev["commence_time"],
                                 "minutes_before": mins, "status": "skipped", "rows": 0, "pull_type": ptype,
                                 "note": "credits reserved for NBA pre-game pulls"})
                empty_logged.add((ev["id"], ptype))
            summary["pulled"].append({"matchup": matchup, "type": ptype, "status": "skipped", "rows": 0})
            continue
        cost, tried = len(MARKETS), set()
        status, note, rows, last, rem_after, used = "failed", "", [], None, None, ""
        while True:
            lab = choose_key(remaining, cost, tried)
            if lab is None:
                note = note or "no key with enough credits left"
                status = "no_credits" if status == "failed" and not note.startswith("HTTP") else status
                break
            tried.add(lab)
            captured = iso(utcnow())
            code, body, h = _get(f"{BASE}/events/{ev['id']}/odds", {
                "apiKey": dict(keys)[lab], "bookmakers": ",".join(BOOKS), "markets": ",".join(MARKETS),
                "oddsFormat": "american", "dateFormat": "iso"})
            last, rem_after = _credits(h)
            if rem_after is not None:
                remaining[lab] = rem_after
            used = lab
            if code == 200:
                rows = parse_event_props(body, captured, mins, ptype)
                status = "ok" if rows else "empty"
                note = "" if rows else "no props posted yet"
                break
            note = f"HTTP {code or h.get('error')}"
            if code in (401, 429):
                remaining[lab] = 0
                continue
            break
        if status == "empty":
            last_empty[ev["id"]] = now      # compared against later runs' `now`, so stamp it with the same clock
        else:
            last_empty.pop(ev["id"], None)
        if status != "empty" or (ev["id"], ptype) not in empty_logged:
            log_rows.append({"at": iso(utcnow()), "event_id": ev["id"], "matchup": matchup, "commence_utc": ev["commence_time"],
                             "minutes_before": mins, "status": status, "markets": ",".join(sorted({r["market"] for r in rows})),
                             "rows": len(rows), "credits_last": last, "credits_remaining": rem_after, "key": used,
                             "note": note, "pull_type": ptype})
            if status == "empty":
                empty_logged.add((ev["id"], ptype))
        cap_rows.extend(rows)
        if ptype == "pregame" and status == "ok":
            summary["pregame_pulled"] = True
        summary["pulled"].append({"matchup": matchup, "type": ptype, "status": status, "rows": len(rows)})
        log.info("cbb props %-8s %-50s %s (%d rows, %s min before tip)", ptype, matchup, status, len(rows), mins)

    _append_csv(data_dir / "prop_captures.csv", CAPTURE_FIELDS, cap_rows)
    _append_csv(data_dir / "pull_log.csv", PULL_FIELDS, log_rows)
    _save_state(state_path, last_empty)
    # Game spreads and totals: one bulk call serves every due game. A failure here never stops the props above.
    from . import lines
    try:
        summary["lines"] = lines.run(data_dir, keys, p4_events, remaining, now)
    except Exception as e:
        log.warning("cbb lines failed: %s", e)
        summary["lines"] = {"status": "failed", "error": f"{type(e).__name__}: {e}"[:300]}
    summary["credits"] = remaining
    bad = any(p["status"] == "failed" for p in summary["pulled"]) or summary["lines"].get("status") == "failed"
    summary["status"] = "failed" if bad else "ok"
    return summary
