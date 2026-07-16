"""FastAPI application: configuration + monitoring UI and JSON API."""

import contextlib
import logging
import os
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from ..exchanges import ExchangeError, create_client
from ..settings import exchange_configured

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

JOBS = {"refresh", "rebalance", "repay", "sweep"}


def create_app(engine):
    app = FastAPI(title="Trading Automator", version="2.0.0")
    settings = engine.settings

    # -- UI ----------------------------------------------------------------

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    # -- health (container healthcheck) -------------------------------------

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "engine_running": engine.state.engine_running,
            "dry_run": settings.get("dry_run", True),
        }

    # -- status --------------------------------------------------------------

    @app.get("/api/status")
    def status():
        return {
            "state": engine.state.to_dict(),
            "scheduler": engine.scheduler.summary(),
            "dry_run": settings.get("dry_run", True),
            "exchange": settings.get("exchange"),
            "quote_asset": settings.get("trading.quote_asset"),
            "llm_provider": engine.llm.current_provider,
        }

    # -- configuration ----------------------------------------------------------

    @app.get("/api/config")
    def get_config():
        return settings.masked()

    @app.put("/api/config")
    def put_config(payload: dict):
        try:
            settings.update(payload)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, f"Invalid configuration: {exc}") from exc
        engine.state.log("Configuration updated via web UI")

        # In autostart deployments (podman) the engine comes up on its own as
        # soon as usable exchange credentials exist -- but never against an
        # explicit stop (runtime.engine_enabled persists that decision).
        autostart = os.getenv("AUTOSTART", "").strip().lower() in ("1", "true", "yes")
        if (autostart
                and not engine.state.engine_running
                and settings.get("runtime.engine_enabled", True)
                and exchange_configured(settings)):
            engine.state.log("Exchange credentials configured -- starting engine automatically")
            engine.start()

        return settings.masked()

    # -- engine control -----------------------------------------------------------

    @app.post("/api/engine/start")
    def engine_start():
        engine.start()
        return {"running": True}

    @app.post("/api/engine/stop")
    def engine_stop():
        engine.stop()
        return {"running": False}

    @app.post("/api/run/{job}")
    def run_job(job: str):
        if job not in JOBS:
            raise HTTPException(404, f"Unknown job '{job}' (one of {sorted(JOBS)})")
        target = {
            "refresh": engine.refresh,
            "rebalance": engine.rebalance,
            "repay": engine.repay,
            "sweep": engine.sweep_small_balances,
        }[job]

        def runner():
            # Job errors are recorded in engine.state by _run_job; nothing to do here.
            with contextlib.suppress(Exception):
                target()

        threading.Thread(target=runner, daemon=True, name=f"manual-{job}").start()
        return {"started": job}

    # -- connectivity test ------------------------------------------------------------

    @app.post("/api/test-connection")
    def test_connection():
        try:
            client = create_client(settings)
            message = client.test_connection()
            engine.state.log(f"Connection test: {message}")
            return {"ok": True, "message": message}
        except ExchangeError as exc:
            return JSONResponse(status_code=502,
                                content={"ok": False, "message": str(exc)})
        except Exception as exc:  # noqa: BLE001 -- API boundary: unexpected errors become a 500
            return JSONResponse(status_code=500,
                                content={"ok": False, "message": str(exc)})

    return app
