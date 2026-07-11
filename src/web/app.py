"""FastAPI application: configuration + monitoring UI and JSON API."""

import logging
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from ..exchanges import ExchangeError, create_client

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
            raise HTTPException(400, f"Invalid configuration: {exc}")
        engine.state.log("Configuration updated via web UI")
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
            try:
                target()
            except Exception:
                pass  # surfaced via engine state

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
        except Exception as exc:
            return JSONResponse(status_code=500,
                                content={"ok": False, "message": str(exc)})

    return app
