"""NBA player prop capture from The Odds API (v4), spread across several keys.

Two captures per game:
  morning  — the first run at or after 8:00 AM Central on game day (retried each run
             until the books have posted props, as long as tip is more than ~70 min away)
  pregame  — the first run within PREGAME_WINDOW (~1 hour) of tip; if no run lands in
             the window, the next run before tip takes it. This is the graded line.

Each run:
  1. Calls the free /events endpoint with every key — lists upcoming games and reports
     each key's remaining credits without spending any.
  2. Pulls DraftKings + FanDuel props for every game that is due (one call per game;
     core markets only: points, rebounds, assists, threes — 4 credits; an empty answer is free.
     Combo lines (PRA, P+R, P+A, R+A) are built from these in build.py, not pulled).
  3. Appends every price to data/prop_captures.csv and every attempt to data/pull_log.csv.
     Both files are append-only: captured lines are irreplaceable.

Nothing is pulled at or after tip-off.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

from .odds import KEY_VARS

log = logging.getLogger(__name__)

BASE = "https://api.the-odds-api.com/v4/sports/basketball_nba"
CORE = ["player_points", "player_rebounds", "player_assists", "player_threes"]
# No longer pulled (credits): combos are derived from CORE in build.py; steals/blocks dropped.
# Kept so older captures in prop_captures.csv still map to known markets.
EXTRA = ["player_points_rebounds_assists", "player_points_rebounds", "player_points_assists",
         "player_rebounds_assists", "player_steals", "player_blocks"]
GAMES_PER_DAY_EST = 7.5   # rough NBA average (1,230 games over ~165 days); used only for the guard
BOOKS = ["draftkings", "fanduel"]
CENTRAL = ZoneInfo("America/Chicago")
MORNING_AT = time(8, 0)                         # morning pull: 8:00 AM Central on game day
PREGAME_WINDOW = timedelta(minutes=70)          # pregame pull: first run within ~1 h of tip
PULLS_PER_GAME = 2
RESERVE = 0                                    # credits to leave untouched on each key
GUARD_RESERVE = 20                             # extra cushion kept for core markets

CAPTURE_FIELDS = ["captured_at", "event_id", "commence_utc", "minutes_before", "home_team", "away_team",
                  "book", "market", "player", "side", "point", "price", "market_updated", "pull_type"]
PULL_FIELDS = ["at", "event_id", "matchup", "commence_utc", "minutes_before", "status", "markets",
               "rows", "credits_last", "credits_remaining", "key", "note", "pull_type"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _get(url: str, params: dict, timeout: float = 25.0) -> tuple[int, Any, dict]:
    """Single GET without retries (a retry could double-spend credits). Never logs the key."""
    try:
        r = requests.get(url, params=params, timeout=timeout,
                         headers={"User-Agent": "nba-odds-tracker/0.2", "Accept": "application/json"})
    except requests.RequestException as e:
        return 0, None, {"error": type(e).__name__}
    try:
        body = r.json()
    except ValueError:
        body = None
    return r.status_code, body, dict(r.headers)


def _credits(h: dict) -> tuple[int | None, int | None]:
    def num(v):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None
    low = {k.lower(): v for k, v in h.items()}
    return num(low.get("x-requests-last")), num(low.get("x-requests-remaining"))


def load_keys(env: dict) -> list[tuple[str, str]]:
    """[(label, key)] for every non-empty ODDS_API_KEY / _2 … _6."""
    return [(var, env[var].strip()) for var in KEY_VARS if env.get(var, "").strip()]


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _append_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows(rows)


def migrate_columns(path: Path, fields: list[str], default_type: str = "pregame") -> None:
    """Add the pull_type column to an older file in place (rows before it existed were pre-game pulls)."""
    if not path.exists():
        return
    with path.open(newline="", encoding="utf-8") as f:
        header = next(csv.reader(f), [])
    if header == fields:
        return
    rows = _read_csv(path)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "pull_type": r.get("pull_type") or default_type})
    tmp.replace(path)


def done_pulls(data_dir: Path) -> tuple[set, set]:
    """(event, pull_type) pairs already captured, and pairs already logged as 'empty'."""
    done, empty = set(), set()
    for r in _read_csv(data_dir / "pull_log.csv"):
        k = (r.get("event_id"), r.get("pull_type") or "pregame")
        if r.get("status") == "ok":
            done.add(k)
        elif r.get("status") == "empty":
            empty.add(k)
    return done, empty


def plan(events: list[dict], done: set, now: datetime) -> list[tuple[dict, str]]:
    """Games due this run, as (event, pull_type)."""
    local = now.astimezone(CENTRAL)
    morning_open = local.time() >= MORNING_AT
    out = []
    for ev in events:
        try:
            start = parse_iso(ev["commence_time"])
        except (KeyError, ValueError):
            continue
        if start <= now:
            continue
        eid = ev.get("id")
        if start - now <= PREGAME_WINDOW:
            if (eid, "pregame") not in done:
                out.append((ev, "pregame"))
        elif morning_open and start.astimezone(CENTRAL).date() == local.date() and (eid, "morning") not in done:
            out.append((ev, "morning"))
    # Pre-game pulls first: they're the graded lines.
    return sorted(out, key=lambda x: (x[1] != "pregame", x[0]["commence_time"]))


def parse_event_props(body: dict, captured_at: str, minutes_before: int, pull_type: str = "pregame") -> list[dict]:
    rows = []
    for bk in (body or {}).get("bookmakers") or []:
        for m in bk.get("markets") or []:
            for o in m.get("outcomes") or []:
                rows.append({
                    "captured_at": captured_at,
                    "event_id": body.get("id"),
                    "commence_utc": body.get("commence_time"),
                    "minutes_before": minutes_before,
                    "home_team": body.get("home_team"),
                    "away_team": body.get("away_team"),
                    "book": bk.get("key"),
                    "market": m.get("key"),
                    "player": o.get("description"),
                    "side": o.get("name"),
                    "point": o.get("point"),
                    "price": o.get("price"),
                    "market_updated": m.get("last_update"),
                    "pull_type": pull_type,
                })
    return rows


PROBE_EVERY = timedelta(days=7)


def probe_markets(data_dir: Path, events: list[dict], keys: list[tuple[str, str]],
                  remaining: dict, now: datetime) -> str:
    """Weekly (1 credit): which markets DK/FD actually post for the next game within 3 h of tip.
    Saved to data/markets_probe.json so new markets can be evaluated before paying to pull them."""
    path = data_dir / "markets_probe.json"
    try:
        last = parse_iso(json.loads(path.read_text())["probed_at"])
        if now - last < PROBE_EVERY:
            return "not_due"
    except Exception:
        pass
    soon = [e for e in events if now < parse_iso(e["commence_time"]) <= now + timedelta(hours=3)]
    if not soon:
        return "no_game_near_tip"
    ev = min(soon, key=lambda e: e["commence_time"])
    lab = max(remaining, key=lambda k: remaining[k] or 0)
    if (remaining.get(lab) or 0) < 1:
        return "no_credits"
    code, body, h = _get(f"{BASE}/events/{ev['id']}/markets",
                         {"apiKey": dict(keys)[lab], "bookmakers": ",".join(BOOKS), "dateFormat": "iso"})
    _, rem = _credits(h)
    if rem is not None:
        remaining[lab] = rem
    if code != 200:
        return f"HTTP {code}"
    books = {b.get("key"): sorted(m.get("key") for m in b.get("markets") or []) for b in (body or {}).get("bookmakers") or []}
    path.write_text(json.dumps({"probed_at": iso(now), "event": f"{ev.get('away_team')} @ {ev.get('home_team')}",
                                "commence_utc": ev.get("commence_time"), "books": books}, indent=1))
    return "ok"


def _days_left(now: datetime) -> float:
    first_next = (now.replace(day=1) + timedelta(days=32)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return max(1.0, (first_next - now).total_seconds() / 86400)


def budget(total_remaining: int | None, now: datetime, pull_type: str) -> list[str] | None:
    """Markets to request (core only), or None to skip.
    Pre-game core is always pulled. Morning core is pulled only if the credits left afterwards
    still cover every pre-game pull through the end of the month (assumes monthly reset)."""
    if total_remaining is None or pull_type == "pregame":
        return list(CORE)
    pre_core = len(CORE) * GAMES_PER_DAY_EST * _days_left(now)
    if total_remaining - GUARD_RESERVE - len(CORE) >= pre_core:
        return list(CORE)
    return None


def run(data_dir: Path, keys: list[tuple[str, str]], now: datetime | None = None) -> dict:
    """One capture pass. Returns a summary for run.json."""
    now = now or utcnow()
    summary: dict[str, Any] = {"keys": len(keys), "credits": {}, "pulled": [], "errors": []}
    if not keys:
        summary["status"] = "no_key"
        return summary

    # 1) Free events call per key: upcoming games + each key's remaining credits.
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
    if events is None:
        summary["status"] = "failed"
        return summary

    try:
        summary["markets_probe"] = probe_markets(data_dir, events, keys, remaining, now)
    except Exception as e:
        summary["errors"].append(f"markets probe: {type(e).__name__}")

    migrate_columns(data_dir / "prop_captures.csv", CAPTURE_FIELDS)
    migrate_columns(data_dir / "pull_log.csv", PULL_FIELDS)
    done, empty_logged = done_pulls(data_dir)
    games = plan(events, done, now)
    summary["due"] = len(games)
    summary["pregame_pulled"] = False
    log_rows, cap_rows = [], []

    # 2) Pull each due game with the key that has the most credits left.
    for ev, ptype in games:
        start = parse_iso(ev["commence_time"])
        mins = int((start - now).total_seconds() // 60)
        matchup = f"{ev.get('away_team')} @ {ev.get('home_team')}"
        total = None if any(v is None for v in remaining.values()) else sum(v for v in remaining.values())
        markets = budget(total, now, ptype)
        if markets is None:
            if (ev["id"], ptype) not in empty_logged:
                log_rows.append({"at": iso(utcnow()), "event_id": ev["id"], "matchup": matchup, "commence_utc": ev["commence_time"],
                                 "minutes_before": mins, "status": "skipped", "rows": 0, "pull_type": ptype,
                                 "note": "credits reserved for pre-game pulls"})
                empty_logged.add((ev["id"], ptype))
            summary["pulled"].append({"matchup": matchup, "type": ptype, "status": "skipped", "rows": 0})
            continue
        cost = len(markets)
        tried: set[str] = set()
        status, note, rows, last, rem_after, used = "failed", "", [], None, None, ""
        while True:
            cands = [(rem, lab) for lab, rem in remaining.items()
                     if lab not in tried and (rem is None or rem - RESERVE >= cost)]
            if not cands:
                note = note or "no key with enough credits left"
                status = "no_credits" if status == "failed" and not note.startswith("HTTP") else status
                break
            _, lab = max(cands, key=lambda c: -1 if c[0] is None else c[0])
            tried.add(lab)
            key = dict(keys)[lab]
            captured = iso(utcnow())
            code, body, h = _get(f"{BASE}/events/{ev['id']}/odds", {
                "apiKey": key, "bookmakers": ",".join(BOOKS), "markets": ",".join(markets),
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
            if code in (401, 429):           # key rejected or out of credits: try the next key
                remaining[lab] = 0
                continue
            break                            # other errors: retry on the next scheduled run
        mk = sorted({r["market"] for r in rows})
        # An empty answer (props not posted yet) is free and retried next run; log it once.
        if status != "empty" or (ev["id"], ptype) not in empty_logged:
            log_rows.append({"at": iso(utcnow()), "event_id": ev["id"], "matchup": matchup,
                             "commence_utc": ev["commence_time"], "minutes_before": mins, "status": status,
                             "markets": ",".join(mk), "rows": len(rows), "credits_last": last,
                             "credits_remaining": rem_after, "key": used, "note": note, "pull_type": ptype})
            if status == "empty":
                empty_logged.add((ev["id"], ptype))
        cap_rows.extend(rows)
        if ptype == "pregame" and status == "ok":
            summary["pregame_pulled"] = True
        summary["pulled"].append({"matchup": matchup, "type": ptype, "status": status, "rows": len(rows), "markets": len(mk)})
        log.info("props %-8s %-45s %s (%d rows, %s min before tip)", ptype, matchup, status, len(rows), mins)

    _append_csv(data_dir / "prop_captures.csv", CAPTURE_FIELDS, cap_rows)
    _append_csv(data_dir / "pull_log.csv", PULL_FIELDS, log_rows)
    summary["credits"] = remaining
    failed = [p for p in summary["pulled"] if p["status"] == "failed"]
    summary["status"] = "failed" if failed else "ok"
    return summary
