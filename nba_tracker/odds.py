"""Sportsbook odds from The Odds API (v4).

Needs an API key in the ODDS_API_KEY environment variable (a GitHub Actions
secret in CI). Without a key this module does nothing, so the stats pipeline
runs fine before the key is added.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from .http import get_json

log = logging.getLogger(__name__)

ODDS_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds"
DEFAULT_MARKETS = "h2h,spreads,totals"


KEY_VARS = ["ODDS_API_KEY"] + [f"ODDS_API_KEY_{i}" for i in range(2, 7)] + ["ODDS_API_KEY_20K"]


def api_key() -> str | None:
    """First non-empty key among ODDS_API_KEY, ODDS_API_KEY_2 … _6."""
    for var in KEY_VARS:
        key = os.environ.get(var, "").strip()
        if key:
            return key
    return None


def fetch_odds(key: str, *, regions: str = "us", markets: str = DEFAULT_MARKETS) -> tuple[Any, dict]:
    """Return (events, quota_info). Each call costs quota (markets x regions)."""
    data, headers = get_json(ODDS_URL, {
        "apiKey": key,
        "regions": regions,
        "markets": markets,
        "oddsFormat": "american",
        "dateFormat": "iso",
    })
    quota = {
        "requests_remaining": headers.get("x-requests-remaining"),
        "requests_used": headers.get("x-requests-used"),
        "last_call_cost": headers.get("x-requests-last"),
    }
    return data, quota


def parse_odds(raw: Any, fetched_at: str | None = None) -> list[dict]:
    """Flatten to one row per game x bookmaker x market x outcome.

    The API also returns games already in progress; those rows get in_play=True so
    live prices are never mistaken for pre-game lines.
    """
    rows = []
    for ev in raw or []:
        start = ev.get("commence_time")
        in_play = bool(fetched_at and start and start <= fetched_at)
        for book in ev.get("bookmakers") or []:
            for market in book.get("markets") or []:
                for out in market.get("outcomes") or []:
                    rows.append({
                        "event_id": ev.get("id"),
                        "commence_utc": ev.get("commence_time"),
                        "home_team": ev.get("home_team"),
                        "away_team": ev.get("away_team"),
                        "book": book.get("key"),
                        "market": market.get("key"),
                        "market_updated": market.get("last_update"),
                        "outcome": out.get("name"),
                        "price": out.get("price"),
                        "point": out.get("point"),
                        "in_play": in_play,
                    })
    return rows


LOG_FIELDS = ["fetched_at", "event_id", "commence_utc", "in_play", "home_team", "away_team",
              "book", "market", "market_updated", "outcome", "price", "point"]


def append_log(path, rows: list[dict], fetched_at: str) -> int:
    """Append every pulled price to a monthly CSV so no line is ever overwritten."""
    import csv
    from pathlib import Path

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({**r, "fetched_at": fetched_at})
    return len(rows)
