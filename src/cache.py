"""Response cache for expensive external calls.

When enabled (dry-run mode), analysis and LLM responses are cached to JSON
files so repeated development runs do not burn API quota. Entries expire
after ``max_age`` seconds so long-running dry-run sessions still track the
market instead of replaying the first cycle forever.
"""

import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

CACHE_DIR = Path(os.getenv("CACHE_DIR", "artifacts/cache"))
DEFAULT_MAX_AGE = 1800  # seconds


def cached_response(
    name: str,
    callback: Callable[[], Any],
    enabled: bool = False,
    max_age: float = DEFAULT_MAX_AGE,
) -> Any:
    """Run ``callback`` and cache its JSON-serialisable result under ``name``.

    With ``enabled`` False the callback always runs (the result is still
    written for later inspection). With True, a cache entry younger than
    ``max_age`` seconds short-circuits the call.
    """
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    path = CACHE_DIR / f"{safe}.json"

    if enabled and path.exists():
        try:
            if time.time() - path.stat().st_mtime < max_age:
                with path.open() as fp:
                    result = json.load(fp)
                log.info("Loaded from cache: %s", path.name)
                return result
            log.debug("Cache entry expired: %s", path.name)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Ignoring broken cache file %s: %s", path, exc)

    result = callback()

    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with path.open("w") as fp:
            json.dump(result, fp, default=str)
    except (TypeError, OSError) as exc:
        log.debug("Result for %s not cached: %s", name, exc)

    return result
