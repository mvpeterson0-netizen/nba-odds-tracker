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


def api_key() -> str | None:
    key = os.environ.get("ODDS_API_KEY", "").strip()
    return key or None


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


def parse_odds(raw: Any) -> list[dict]:
    """Flatten to one row per game x bookmaker x market x outcome."""
    rows = []
    for ev in raw or []:
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
                    })
    return rows
