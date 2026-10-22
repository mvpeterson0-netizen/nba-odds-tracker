"""Pre-game NBA player prop capture from The Odds API (v4), spread across several keys.

Each run:
  1. Calls the free /events endpoint with every key — this lists upcoming games and
     reports each key's remaining credits without spending any.
  2. For each game tipping off within PULL_WINDOW that has no successful pre-game
     capture yet, pulls DraftKings + FanDuel props for CORE markets in one call
     (cost = markets returned x 1 region, so at most 4 credits per game).
  3. Appends every price to data/prop_captures.csv and every attempt to
     data/pull_log.csv. Both files are append-only: captured lines are irreplaceable.

Nothing is pulled at or after tip-off.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from .odds import KEY_VARS

log = logging.getLogger(__name__)

BASE = "https://api.the-odds-api.com/v4/sports/basketball_nba"
CORE = ["player_points", "player_rebounds", "player_assists", "player_threes"]
BOOKS = ["draftkings", "fanduel"]
PULL_WINDOW = timedelta(hours=3, minutes=30)   # pull once a game is this close to tip
RESERVE = 0                                    # credits to leave untouched on each key

CAPTURE_FIELDS = ["captured_at", "event_id", "commence_utc", "minutes_before", "home_team", "away_team",
                  "book", "market", "player", "side", "point", "price", "market_updated"]
PULL_FIELDS = ["at", "event_id", "matchup", "commence_utc", "minutes_before", "status", "markets",
               "rows", "credits_last", "credits_remaining", "key", "note"]


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


def captured_events(data_dir: Path) -> set[str]:
    """Events with a successful pre-game pull already logged."""
    return {r["event_id"] for r in _read_csv(data_dir / "pull_log.csv")
            if r.get("status") == "ok" and r.get("event_id")}


def due_games(events: list[dict], done: set[str], now: datetime) -> list[dict]:
    out = []
    for ev in events:
        try:
            start = parse_iso(ev["commence_time"])
        except (KeyError, ValueError):
            continue
        if ev.get("id") in done:
            continue
        if now < start <= now + PULL_WINDOW:
            out.append(ev)
    return sorted(out, key=lambda e: e["commence_time"])


def parse_event_props(body: dict, captured_at: str, minutes_before: int) -> list[dict]:
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
                })
    return rows


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

    done = captured_events(data_dir)
    games = due_games(events, done, now)
    summary["due"] = len(games)
    log_rows, cap_rows = [], []

    # 2) Pull each due game with the key that has the most credits left.
    for ev in games:
        start = parse_iso(ev["commence_time"])
        mins = int((start - now).total_seconds() // 60)
        matchup = f"{ev.get('away_team')} @ {ev.get('home_team')}"
        cost = len(CORE)
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
                "apiKey": key, "bookmakers": ",".join(BOOKS), "markets": ",".join(CORE),
                "oddsFormat": "american", "dateFormat": "iso"})
            last, rem_after = _credits(h)
            if rem_after is not None:
                remaining[lab] = rem_after
            used = lab
            if code == 200:
                rows = parse_event_props(body, captured, mins)
                status = "ok" if rows else "empty"
                note = "" if rows else "no props posted yet"
                break
            note = f"HTTP {code or h.get('error')}"
            if code in (401, 429):           # key rejected or out of credits: try the next key
                remaining[lab] = 0
                continue
            break                            # other errors: retry on the next scheduled run
        mk = sorted({r["market"] for r in rows})
        log_rows.append({"at": iso(utcnow()), "event_id": ev["id"], "matchup": matchup,
                         "commence_utc": ev["commence_time"], "minutes_before": mins, "status": status,
                         "markets": ",".join(mk), "rows": len(rows), "credits_last": last,
                         "credits_remaining": rem_after, "key": used, "note": note})
        cap_rows.extend(rows)
        summary["pulled"].append({"matchup": matchup, "status": status, "rows": len(rows)})
        log.info("props %-45s %s (%d rows, %s min before tip)", matchup, status, len(rows), mins)

    _append_csv(data_dir / "prop_captures.csv", CAPTURE_FIELDS, cap_rows)
    _append_csv(data_dir / "pull_log.csv", PULL_FIELDS, log_rows)
    summary["credits"] = remaining
    failed = [p for p in summary["pulled"] if p["status"] == "failed"]
    summary["status"] = "failed" if failed else "ok"
    return summary
