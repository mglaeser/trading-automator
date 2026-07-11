import pytest
from fastapi.testclient import TestClient

from src.settings import MASK
from src.web.app import create_app


@pytest.fixture
def client(engine):
    return TestClient(create_app(engine))


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["dry_run"] is True


def test_status_and_index(client):
    assert client.get("/api/status").status_code == 200
    page = client.get("/")
    assert page.status_code == 200 and "Trading Automator" in page.text


def test_config_masking(client, settings):
    settings.update({"binance": {"api_key": "k", "api_secret": "s"}})
    assert client.get("/api/config").json()["binance"]["api_key"] == MASK

    # full masked round-trip must not corrupt the stored secrets
    cfg = client.get("/api/config").json()
    assert client.put("/api/config", json=cfg).status_code == 200
    assert settings.get("binance.api_key") == "k"


def test_autostart_on_credential_save(client, engine, settings, monkeypatch):
    monkeypatch.setenv("AUTOSTART", "true")
    monkeypatch.setattr(engine, "_initial_pass", lambda: None)
    assert engine.state.engine_running is False
    r = client.put("/api/config",
                   json={"binance": {"api_key": "k", "api_secret": "s"}})
    assert r.status_code == 200
    assert engine.state.engine_running is True
    engine.stop()


def test_autostart_respects_explicit_stop(client, engine, settings, monkeypatch):
    monkeypatch.setenv("AUTOSTART", "true")
    monkeypatch.setattr(engine, "_initial_pass", lambda: None)
    settings.update({"binance": {"api_key": "k", "api_secret": "s"}})
    engine.start()
    engine.stop()  # explicit stop persists runtime.engine_enabled = false

    # a later config save must NOT resurrect the engine
    r = client.put("/api/config", json={"trading": {"min_trade_value": 11}})
    assert r.status_code == 200
    assert engine.state.engine_running is False


def test_unknown_job_404(client):
    assert client.post("/api/run/nonsense").status_code == 404


def test_manual_job_runs(client, engine):
    r = client.post("/api/run/refresh")
    assert r.status_code == 200 and r.json()["started"] == "refresh"
