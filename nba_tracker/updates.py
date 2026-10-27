"""Player updates for the notes icon on the Board and player pages (ported from Stix).

Writes:
  data/espn_news.json       ESPN headlines tagged with a player (overwritten each run; not an archive)
  data/updates_seen.json    when Dime FIRST saw each update item (drives the red "new" icon)
  data/latest/updates.json  per-player update items, read by the site

Item kinds (all from data Dime already collects, plus one ESPN news request per run):
  ESPN       ESPN's player status note from the league injury feed (status, injury, one-line comment)
  ESPN news  ESPN headlines tagged with that player; last 7 days, newest first, at most 3
  Roster     now on a different team's ESPN roster than in his last box score (trade / signing)
  Role       from his team's most recent game only, needing 4+ games played: minutes differ from his
             prior average by 10+, or he started after coming off the bench in every prior game (or
             the reverse)

ESPN's endpoints are public but unofficial and undocumented (no key, no SLA); they can change or be
blocked at any time, and Disney's Terms of Use (which cover ESPN) limit use to personal,
noncommercial use and bar automated access. Michael accepted those risks for Stix on 2026-10-25.
A news failure is logged and the previous file kept; it never stops a run.

"New": an item counts as new for 24 h after Dime first saw it (Dime's detection time, not the
source's date). Items that already existed the first time this ran have a blank time, so they never
show as new. Seen-times are kept only for items still live, so an item that disappears and later
comes back counts as new again.
"""

from __future__ import annotations

import csv
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import espn
from .build import norm_name

log = logging.getLogger(__name__)

NEWS_DAYS = 7         # headlines older than this are left out
NEWS_MAX = 3          # at most this many headlines per player
ROLE_MIN_GAMES = 4    # games played (including the latest) before role changes are flagged
ROLE_MINUTES = 10.0   # minutes in the latest game vs his prior average


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def refresh_news(data_dir: Path, now: datetime | None = None) -> str:
    """One request for league news. On failure the previous file is kept. Returns "ok" or "failed"."""
    now = now or datetime.now(timezone.utc)
    try:
        news = espn.parse_news(espn.fetch_news())
    except Exception as e:
        log.warning("espn news skipped, keeping the previous file: %s", e)
        return "failed"
    (data_dir / "espn_news.json").write_text(
        json.dumps({"fetched_at": _iso(now), "news": news}, separators=(",", ":")) + "\n", encoding="utf-8")
    log.info("espn news         headlines for %d players", len(news))
    return "ok"


def _short_date(d: str | None) -> str:
    try:
        x = datetime.fromisoformat(str(d)[:10])
        return f"{x:%b} {x.day}"
    except ValueError:
        return str(d or "")


def build(data_dir: Path, now: datetime | None = None) -> dict:
    """Build every player's update items, record first-seen times, write data/latest/updates.json."""
    now = now or datetime.now(timezone.utc)
    seen_path = data_dir / "updates_seen.json"
    seen = _json(seen_path, None)
    first_run = not isinstance(seen, dict)
    seen = seen if isinstance(seen, dict) else {}
    items: dict[str, list[dict]] = defaultdict(list)

    def add(aid: str, key: str, kind: str, text: str, src: str, at: str = "", url: str = "") -> None:
        k = f"{aid}|{key}"
        if k not in seen:
            seen[k] = "" if first_run else _iso(now)
        it = {"k": key, "kind": kind, "text": text, "src": src, "t": seen[k]}
        if at:
            it["at"] = at        # the source's own date for this item
        if url and str(url).startswith("https://"):
            it["url"] = url
        items[aid].append(it)

    # ---- box scores: per-player game logs and each team's most recent final game
    logs: dict[str, list[dict]] = defaultdict(list)
    team_last: dict[str, tuple[str, str]] = {}            # team -> (start, game_id)
    names: dict[tuple[str, str], str] = {}                 # (norm name, team) -> athlete id
    any_team: dict[str, set] = defaultdict(set)            # norm name -> athlete ids
    box_path = data_dir / "player_games.csv"
    rows = []
    if box_path.exists():
        with box_path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    seen_rows = set()
    for r in sorted(rows, key=lambda r: r.get("start_utc") or ""):
        aid, gid = r.get("athlete_id"), r.get("game_id")
        if not aid or not gid or (gid, aid) in seen_rows:
            continue
        seen_rows.add((gid, aid))
        logs[aid].append(r)
        tm = r.get("team") or ""
        if tm and (r.get("start_utc") or "") >= team_last.get(tm, ("", ""))[0]:
            team_last[tm] = (r.get("start_utc") or "", gid)
        names[(norm_name(r.get("player")), tm)] = aid
        any_team[norm_name(r.get("player"))].add(aid)
    rosters = _json(data_dir / "rosters.json", {}) or {}
    for abbr, ro in rosters.items():
        for a in ro.get("players") or []:
            if a.get("id") and a.get("name"):
                names[(norm_name(a["name"]), abbr)] = str(a["id"])
                any_team[norm_name(a["name"])].add(str(a["id"]))

    def match(row: dict) -> str | None:
        if row.get("player_id"):
            return str(row["player_id"])
        nn = norm_name(row.get("player"))
        aid = names.get((nn, row.get("team_abbr") or ""))
        if aid:
            return aid
        cands = any_team.get(nn) or set()
        return next(iter(cands)) if len(cands) == 1 else None

    # ---- ESPN status notes (league injury feed, already pulled each run)
    inj = _json(data_dir / "latest" / "injuries.json", {}) or {}
    for row in inj.get("rows") or []:
        aid = match(row)
        if not aid or not (row.get("status") or row.get("comment")):
            continue
        head = (row.get("status") or "") + (f" ({row['injury']})" if row.get("injury") else "")
        text = head + (": " if head and row.get("comment") else "") + (row.get("comment") or "")
        add(aid, f"espn|status|{row.get('updated')}|{row.get('status')}", "ESPN", text, "ESPN player note",
            at=row.get("updated") or "", url=row.get("url") or f"https://www.espn.com/nba/player/_/id/{aid}")

    # ---- ESPN headlines tagged with the player
    news = (_json(data_dir / "espn_news.json", {}) or {}).get("news") or {}
    cutoff = _iso(now - timedelta(days=NEWS_DAYS))
    for aid, arts in news.items():
        recent = sorted((a for a in arts if (a.get("date") or "") >= cutoff and a.get("url")),
                        key=lambda a: a.get("date") or "", reverse=True)[:NEWS_MAX]
        for a in recent:
            add(str(aid), f"espn|news|{a['url']}", "ESPN news", a.get("headline") or "", "ESPN headline",
                at=a.get("date") or "", url=a["url"])

    # ---- roster moves: on a different team's roster than in his last box score
    for abbr, ro in rosters.items():
        for a in ro.get("players") or []:
            aid = str(a.get("id") or "")
            last = logs.get(aid, [])[-1:] or None
            if not last:
                continue
            last = last[0]
            old = last.get("team") or ""
            if old and old != abbr and (ro.get("date") or "") >= (last.get("game_date") or ""):
                add(aid, f"roster|{abbr}", "Roster",
                    f"Now on the {abbr} roster (last played for {old}, {_short_date(last.get('game_date'))})",
                    "ESPN team roster", at=ro.get("date") or "")

    # ---- role changes, only from his team's most recent game
    for aid, lg in logs.items():
        last = lg[-1]
        if last.get("played") != "True" or team_last.get(last.get("team") or "", ("", ""))[1] != last.get("game_id"):
            continue
        played = [r for r in lg if r.get("played") == "True"]
        if len(played) < ROLE_MIN_GAMES:
            continue
        prior = played[:-1]
        when = f"{_short_date(last.get('game_date'))} {'vs' if last.get('home_away') == 'home' else '@'} {last.get('opp') or ''}".strip()
        mins = [m for m in (_f(r.get("min")) for r in prior) if m is not None]
        lm = _f(last.get("min"))
        if lm is not None and len(mins) >= ROLE_MIN_GAMES - 1:
            avg = sum(mins) / len(mins)
            if abs(lm - avg) >= ROLE_MINUTES:
                add(aid, f"role|{last['game_id']}|min", "Role",
                    f"{when}: played {round(lm)} min (prior average {round(avg)})", "ESPN box score")
        starts = {r.get("starter") == "True" for r in prior}
        now_start = last.get("starter") == "True"
        if len(starts) == 1 and now_start not in starts:
            add(aid, f"role|{last['game_id']}|start", "Role",
                f"{when}: " + ("started" if now_start else "came off the bench") +
                f" after {'coming off the bench' if now_start else 'starting'} in his prior {len(prior)} games played",
                "ESPN box score")

    # keep seen-times only for live items so the file stays small
    live = {f"{aid}|{it['k']}" for aid, its in items.items() for it in its}
    seen_path.write_text(json.dumps({k: v for k, v in sorted(seen.items()) if k in live}, indent=0) + "\n",
                         encoding="utf-8")
    out = {}
    for aid, its in items.items():
        # ESPN items first (newest first by ESPN's own date), then the rest (newest first seen)
        its.sort(key=lambda x: x["t"] or "", reverse=True)
        its.sort(key=lambda x: x.get("at") or "", reverse=True)
        out[aid] = [{k: v for k, v in it.items() if k != "k"} for it in its]
    payload = {"fetched_at": now.isoformat(timespec="seconds"), "source": "espn",
               "news_fetched_at": (_json(data_dir / "espn_news.json", {}) or {}).get("fetched_at"),
               "first_run": first_run, "count": len(out), "players": out}
    (data_dir / "latest").mkdir(parents=True, exist_ok=True)
    (data_dir / "latest" / "updates.json").write_text(json.dumps(payload, separators=(",", ":")) + "\n",
                                                       encoding="utf-8")
    log.info("updates           %d players%s", len(out), " (first run: existing items not marked new)" if first_run else "")
    return payload
