"""Entrypoint: web UI + trading engine.

Run with:  python -m src.main
The engine does NOT auto-trade on startup -- open the web UI, configure your
API keys and press "Start engine". Set AUTOSTART=true to start it headless.
"""

import logging
import os

import uvicorn

from .engine import TradingEngine
from .settings import Settings, exchange_configured
from .web.app import create_app

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

_LOOPBACK = {"127.0.0.1", "localhost", "::1", "::ffff:127.0.0.1"}


def assert_safe_binding(
    host: str, auth_token: str | None, allow_insecure: bool = False
) -> None:
    """Refuse to expose the no-auth API beyond loopback (C-01).

    Binding to a non-loopback address without an API token would put the
    state-changing API (config, engine control, trade triggers) on the network
    unauthenticated. That exposure is made unrepresentable: the app will not
    start. Set web.auth_token / WEB_AUTH_TOKEN, or bind to loopback.

    ``allow_insecure`` (ALLOW_INSECURE_BIND=true) is the explicit escape hatch
    the container sets: inside podman the app binds 0.0.0.0 but the port is
    published only on 127.0.0.1, so the exposure is restricted at the platform
    layer. Naming it "insecure" is deliberate -- it is only safe behind
    loopback port-publishing or an authenticated reverse proxy.
    """
    if str(host) not in _LOOPBACK and not auth_token and not allow_insecure:
        raise RuntimeError(
            f"Refusing to bind the UI to {host!r} without an API token: the "
            "state-changing API has no other authentication. Set web.auth_token "
            "(or WEB_AUTH_TOKEN), bind to 127.0.0.1, or (only behind loopback "
            "port-publishing / an authenticated proxy) set ALLOW_INSECURE_BIND=true."
        )


def main() -> None:
    settings = Settings()
    engine = TradingEngine(settings)
    app = create_app(engine)

    if os.getenv("AUTOSTART", "").strip().lower() in ("1", "true", "yes"):
        if not settings.get("runtime.engine_enabled", True):
            log.info("AUTOSTART set but the engine was explicitly stopped in "
                     "the web UI; press Start there to re-enable it")
        elif exchange_configured(settings):
            log.info("AUTOSTART set -- starting trading engine")
            engine.start()
        else:
            log.info("AUTOSTART set but no exchange credentials configured yet; "
                     "the engine starts automatically once they are saved in "
                     "the web UI")

    host = settings.get("web.host", "0.0.0.0")
    port = int(settings.get("web.port", 8000))
    assert_safe_binding(
        host, settings.get("web.auth_token"),
        allow_insecure=os.getenv("ALLOW_INSECURE_BIND", "").strip().lower()
        in ("1", "true", "yes"),
    )
    log.info("Web UI available on http://%s:%s (dry_run=%s, auth=%s)",
             host, port, settings.get("dry_run", True),
             "on" if settings.get("web.auth_token") else "off (loopback only)")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
