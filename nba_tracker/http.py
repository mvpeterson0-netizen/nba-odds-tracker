"""Small HTTP helper with retries and backoff."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    # ESPN's public endpoints sometimes reject requests without a browser-like UA.
    "User-Agent": "Mozilla/5.0 (compatible; nba-odds-tracker/0.1)",
    "Accept": "application/json",
}


class FetchError(RuntimeError):
    """Raised when a request keeps failing after all retries."""


class PermanentFetchError(FetchError):
    """A 4xx response (other than 429) — retrying won't help."""


def get_json(
    url: str,
    params: dict[str, Any] | None = None,
    *,
    retries: int = 3,
    timeout: float = 20.0,
    backoff: float = 2.0,
    session: requests.Session | None = None,
) -> tuple[Any, requests.structures.CaseInsensitiveDict]:
    """GET a URL and return (parsed_json, response_headers).

    Retries on network errors, 429 and 5xx. 4xx other than 429 fail immediately.
    """
    sess = session or requests.Session()
    secrets = [str(v) for k, v in (params or {}).items() if "key" in k.lower() and v]

    def redact(err: object) -> str:
        msg = str(err)
        for sec in secrets:
            msg = msg.replace(sec, "***")
        return msg

    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = sess.get(url, params=params, headers=DEFAULT_HEADERS, timeout=timeout)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise FetchError(f"HTTP {resp.status_code} from {url}")
            if resp.status_code >= 400:
                # Not retryable (bad key, bad path, etc.). Don't echo the body:
                # it can contain the request URL, which may include an API key.
                raise PermanentFetchError(f"HTTP {resp.status_code} from {url}")
            return resp.json(), resp.headers
        except PermanentFetchError:
            raise
        except (FetchError, requests.RequestException, ValueError) as e:
            last_err = e
        if attempt < retries:
            wait = backoff ** attempt
            log.warning("Attempt %d/%d failed for %s (%s); retrying in %.0fs",
                        attempt, retries, url, redact(last_err), wait)
            time.sleep(wait)
    raise FetchError(f"Giving up on {url}: {redact(last_err)}")
