"""How many Odds API credits college basketball has used.

    python -m cbb_tracker.credits [--since 2026-11-02] [--until 2026-11-05] [--data data/cbb]

Counts only what the college pipeline spent, from its own logs:
  pull_log.csv   player-points pulls (credits_last = what the API charged for that call)
  lines_log.csv  bulk spreads/totals calls
credit_log.csv (every key's balance, college and NBA alike) is shown for context: the drop in the total balance
over the window is everything that came out of the keys, so (balance drop - college) is roughly the NBA's share.
Dates are Central-time days; --until is inclusive.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from nba_tracker.props import CENTRAL, parse_iso


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _day(s: str) -> date:
    return parse_iso(s).astimezone(CENTRAL).date()


def _n(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def summarize(data_dir: Path, since: date, until: date) -> dict:
    props = [r for r in _rows(data_dir / "pull_log.csv") if since <= _day(r["at"]) <= until]
    lines = [r for r in _rows(data_dir / "lines_log.csv") if since <= _day(r["at"]) <= until]
    by_day: dict[str, dict] = defaultdict(lambda: {"props": 0.0, "lines": 0.0, "prop_pulls": 0, "line_pulls": 0})
    kinds: dict[str, dict] = defaultdict(lambda: {"calls": 0, "credits": 0.0})
    for r in props:
        if r.get("status") in ("skipped", "no_credits"):
            continue
        d, c = _day(r["at"]).isoformat(), _n(r.get("credits_last"))
        by_day[d]["props"] += c
        by_day[d]["prop_pulls"] += 1
        k = kinds[f"player points, {r.get('pull_type') or 'pregame'}"]
        k["calls"] += 1
        k["credits"] += c
    for r in lines:
        if r.get("status") in ("skipped", "no_credits"):
            continue
        d, c = _day(r["at"]).isoformat(), _n(r.get("credits_last"))
        by_day[d]["lines"] += c
        by_day[d]["line_pulls"] += 1
        k = kinds[f"spreads+totals, {r.get('pull_type')}"]
        k["calls"] += 1
        k["credits"] += c
    bal = [r for r in _rows(data_dir / "credit_log.csv") if since <= _day(r["at"]) <= until]
    drop = None
    if len(bal) >= 2:
        cols = [c for c in bal[0] if c != "at"]
        drop = sum(_n(bal[0][c]) - _n(bal[-1][c]) for c in cols)
    return {"since": since.isoformat(), "until": until.isoformat(), "by_day": dict(sorted(by_day.items())),
            "kinds": dict(kinds), "props": sum(v["props"] for v in by_day.values()), "lines": sum(v["lines"] for v in by_day.values()),
            "balance_first": bal[0] if bal else None, "balance_last": bal[-1] if bal else None, "balance_drop": drop,
            "empty_props": sum(1 for r in props if r.get("status") == "empty"),
            "skipped": sum(1 for r in props + lines if r.get("status") == "skipped")}


def render(s: dict) -> str:
    out = [f"College basketball credits, {s['since']} to {s['until']} (Central days)", ""]
    out.append(f"{'day':<12}{'props':>8}{'lines':>8}{'total':>8}   pulls (props / lines)")
    for d, v in s["by_day"].items():
        out.append(f"{d:<12}{v['props']:>8.0f}{v['lines']:>8.0f}{v['props'] + v['lines']:>8.0f}   {v['prop_pulls']} / {v['line_pulls']}")
    n = len(s["by_day"]) or 1
    total = s["props"] + s["lines"]
    out += ["", f"Player points: {s['props']:.0f}   Spreads+totals: {s['lines']:.0f}   Total: {total:.0f}   "
                f"(about {total / n:.1f}/day over {len(s['by_day'])} active days, ~{total / n * 30:.0f}/month)", ""]
    for k, v in sorted(s["kinds"].items()):
        out.append(f"  {k:<32}{v['calls']:>4} calls  {v['credits']:>6.0f} credits")
    out.append(f"\nEmpty prop answers (free): {s['empty_props']}   Skipped to protect NBA credits: {s['skipped']}")
    if s["balance_drop"] is not None:
        b0, b1 = s["balance_first"], s["balance_last"]
        out.append(f"All keys, first to last balance snapshot: {b0['at']} -> {b1['at']}, down {s['balance_drop']:.0f} credits "
                   f"(everything, NBA included; the rest after college's {total:.0f} is roughly the NBA's).")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/cbb")
    ap.add_argument("--since", default="2026-11-02")
    ap.add_argument("--until", default=None)
    a = ap.parse_args(argv)
    since = date.fromisoformat(a.since)
    until = date.fromisoformat(a.until) if a.until else datetime.now(CENTRAL).date()
    print(render(summarize(Path(a.data), since, until)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
