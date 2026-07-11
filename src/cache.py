"""Response cache for expensive external calls (was responseIO).

When enabled (dry-run/debug mode), analysis and LLM responses are cached to
JSON files so repeated development runs do not burn API quota.
"""

import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

CACHE_DIR = Path(os.getenv("CACHE_DIR", "artifacts/cache"))


def cached_response(name, callback, enabled=False):
    """Run ``callback`` and cache its JSON-serialisable result under ``name``.

    With ``enabled`` False the callback always runs (result is still written
    for later inspection). With True, an existing cache entry short-circuits
    the call.
    """
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    path = CACHE_DIR / f"{safe}.json"

    if enabled and path.exists():
        try:
            with path.open() as fp:
                result = json.load(fp)
            log.info("Loaded from cache: %s", path.name)
            return result
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
