"""Entrypoint: web UI + trading engine.

Run with:  python -m src.main
The engine does NOT auto-trade on startup -- open the web UI, configure your
API keys and press "Start engine". Set AUTOSTART=true to start it headless.
"""

import logging
import os

import uvicorn

from .engine import TradingEngine
from .settings import Settings
from .web.app import create_app

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


def main():
    settings = Settings()
    engine = TradingEngine(settings)
    app = create_app(engine)

    if os.getenv("AUTOSTART", "").strip().lower() in ("1", "true", "yes"):
        log.info("AUTOSTART set -- starting trading engine")
        engine.start()

    host = settings.get("web.host", "0.0.0.0")
    port = int(settings.get("web.port", 8000))
    log.info("Web UI available on http://%s:%s (dry_run=%s)",
             host, port, settings.get("dry_run", True))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
