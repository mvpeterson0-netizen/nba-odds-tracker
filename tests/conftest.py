import sys
from pathlib import Path

# Make the package importable without installing it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


import pytest


@pytest.fixture(autouse=True)
def _no_link_backfill(monkeypatch):
    """The one-time link catch-up makes extra odds calls; tests that want it switch it on."""
    from nba_tracker import props
    monkeypatch.setattr(props, "LINKS_BACKFILL", False)
