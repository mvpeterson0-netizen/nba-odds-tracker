"""Power 4 game lines (spread and total) from The Odds API, in bulk.

One call to /odds returns every upcoming game for the sport, so it costs markets x regions (2 spreads+totals x 1 US
region = 2 credits) however many games come back. We keep only the Power 4 games matched on ESPN.

  8 AM   first run at or after 8:00 AM Central on a day with Power 4 games (retried about hourly until some line posts)
  1 hour first run within ~70 minutes of a game's tip; one call serves every game inside that window

data/cbb/line_captures.csv  every price captured (append-only)
data/cbb/lines_log.csv      every call, with credits used and left (append-only)
data/cbb/lines_state.json   what has been captured already
Credits are shared with the NBA; this never spends credits the NBA pre-game pulls need.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from nba_tracker.props import (BOOKS, CENTRAL, MORNING_AT, PREGAME_WINDOW, _append_csv, _credits, choose_key, iso, parse_iso,
                               utcnow)

log = logging.getLogger(__name__)

MARKETS = ["spreads", "totals"]
RETRY_EMPTY = timedelta(minutes=55)
LINE_FIELDS = ["captured_at", "event_id", "commence_utc", "minutes_before", "home_team", "away_team", "book", "market",
               "name", "point", "price", "pull_type"]
LOG_FIELDS = ["at", "pull_type", "events", "p4_games", "rows", "status", "credits_last", "credits_remaining", "key", "note"]


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def due(p4_events: list[tuple[dict, dict]], state: dict, now: datetime) -> tuple[bool, set[str]]:
    """(morning pull due, event ids due a pre-game capture)."""
    local = now.astimezone(CENTRAL)
    upcoming = [(ev, parse_iso(ev["commence_time"])) for ev, _ in p4_events]
    upcoming = [(ev, t) for ev, t in upcoming if t > now]
    today = [t for _, t in upcoming if t.astimezone(CENTRAL).date() == local.date()]
    morning = bool(today) and local.time() >= MORNING_AT and state.get("morning_date") != local.date().isoformat()
    if morning and state.get("morning_try"):
        morning = now - parse_iso(state["morning_try"]) >= RETRY_EMPTY
    pre = {ev["id"] for ev, t in upcoming if t - now <= PREGAME_WINDOW and ev["id"] not in set(state.get("pregame", []))}
    return morning, pre


def parse_rows(events: list[dict], targets: dict[str, str], captured_at: str, now: datetime) -> list[dict]:
    rows = []
    for ev in events or []:
        ptype = targets.get(ev.get("id"))
        if not ptype:
            continue
        mins = int((parse_iso(ev["commence_time"]) - now).total_seconds() // 60)
        for bk in ev.get("bookmakers") or []:
            for m in bk.get("markets") or []:
                for o in m.get("outcomes") or []:
                    rows.append({"captured_at": captured_at, "event_id": ev["id"], "commence_utc": ev["commence_time"],
                                 "minutes_before": mins, "home_team": ev.get("home_team"), "away_team": ev.get("away_team"),
                                 "book": bk.get("key"), "market": m.get("key"), "name": o.get("name"),
                                 "point": o.get("point"), "price": o.get("price"), "pull_type": ptype})
    return rows


def run(data_dir: Path, keys: list[tuple[str, str]], p4_events: list[tuple[dict, dict]], remaining: dict, now: datetime) -> dict:
    from . import props as P          # late import (props imports this module); _get is looked up on props so one patch covers both
    BASE, credits_ok, _get = P.BASE, P.credits_ok, P._get

    path = data_dir / "lines_state.json"
    state = _load(path)
    live = {ev["id"] for ev, _ in p4_events}
    state["pregame"] = [e for e in state.get("pregame", []) if e in live]
    morning, pre = due(p4_events, state, now)
    out: dict[str, Any] = {"status": "not_due", "morning_due": morning, "pregame_due": len(pre)}
    if not morning and not pre:
        path.write_text(json.dumps(state))
        return out
    ptype = "morning" if morning else "pregame"
    cost = len(MARKETS)
    total = None if any(v is None for v in remaining.values()) else sum(v for v in remaining.values())
    if not credits_ok(total, now, "pregame", cost):
        out["status"] = "skipped"
        _append_csv(data_dir / "lines_log.csv", LOG_FIELDS, [{"at": iso(utcnow()), "pull_type": ptype, "events": 0, "p4_games": len(p4_events),
                                                              "rows": 0, "status": "skipped", "note": "credits reserved for NBA pre-game pulls"}])
        return out
    tried: set[str] = set()
    body, last, rem_after, used, note = None, None, None, "", ""
    while True:
        lab = choose_key(remaining, cost, tried)
        if lab is None:
            note = note or "no key with enough credits left"
            break
        tried.add(lab)
        code, resp, h = _get(f"{BASE}/odds", {"apiKey": dict(keys)[lab], "bookmakers": ",".join(BOOKS), "markets": ",".join(MARKETS),
                                              "oddsFormat": "american", "dateFormat": "iso"})
        last, rem_after = _credits(h)
        if rem_after is not None:
            remaining[lab] = rem_after
        used = lab
        if code == 200 and isinstance(resp, list):
            body = resp
            break
        note = f"HTTP {code or h.get('error')}"
        if code in (401, 429):
            remaining[lab] = 0
            continue
        break
    now_s = iso(utcnow())
    rows: list[dict] = []
    if body is not None:
        targets = {eid: "pregame" for eid in pre}
        if morning:
            targets.update({ev["id"]: "morning" for ev, _ in p4_events if ev["id"] not in targets})
        rows = parse_rows(body, targets, now_s, now)
        got = {r["event_id"] for r in rows}
        if morning:
            if rows:
                state["morning_date"] = now.astimezone(CENTRAL).date().isoformat()
                state.pop("morning_try", None)
            else:
                state["morning_try"] = iso(now)
                note = "no lines posted yet"
        state["pregame"] = sorted(set(state["pregame"]) | (pre & got))
        _append_csv(data_dir / "line_captures.csv", LINE_FIELDS, rows)
    status = "ok" if rows else ("empty" if body is not None else ("no_credits" if note.startswith("no key") else "failed"))
    _append_csv(data_dir / "lines_log.csv", LOG_FIELDS, [{
        "at": now_s, "pull_type": ptype, "events": len(body or []), "p4_games": len({r["event_id"] for r in rows}), "rows": len(rows),
        "status": status, "credits_last": last, "credits_remaining": rem_after, "key": used, "note": note}])
    path.write_text(json.dumps(state))
    out.update({"status": status, "pull_type": ptype, "rows": len(rows), "credits_last": last})
    log.info("cbb lines %-8s %s (%d rows, %s credits)", ptype, status, len(rows), last)
    return out
