"""C-01 core application security: the state-changing API must not be reachable
unauthenticated once the UI is exposed beyond loopback.

Two controls:
  - assert_safe_binding refuses to start on a non-loopback bind without a token
    (the dangerous exposure becomes unrepresentable, not merely discouraged).
  - when web.auth_token is set, every state-changing route requires a bearer
    token; reads and the container healthcheck stay open. With no token
    (loopback default) behaviour is unchanged.
"""
import pytest
from fastapi.testclient import TestClient

from src.main import assert_safe_binding
from src.web.app import create_app

# -- bind-safety guard ---------------------------------------------------------

def test_non_loopback_bind_without_token_refused():
    with pytest.raises(RuntimeError):
        assert_safe_binding("0.0.0.0", "")


def test_non_loopback_bind_with_token_ok():
    assert assert_safe_binding("0.0.0.0", "a-real-token") is None


def test_non_loopback_bind_with_insecure_override_ok():
    # the container's escape hatch: 0.0.0.0 allowed when exposure is restricted
    # at the platform layer (podman publishes only to 127.0.0.1)
    assert assert_safe_binding("0.0.0.0", "", allow_insecure=True) is None


def test_loopback_bind_without_token_ok():
    assert assert_safe_binding("127.0.0.1", "") is None
    assert assert_safe_binding("localhost", "") is None


# -- API token on state-changing routes ----------------------------------------

def test_mutating_route_requires_token_when_set(engine, settings):
    settings.update({"web": {"auth_token": "secret-token"}})
    c = TestClient(create_app(engine))
    # no header -> 401
    assert c.put("/api/config", json={"trading": {"min_trade_value": 11}}).status_code == 401
    assert c.post("/api/engine/start").status_code == 401
    # correct bearer -> allowed
    r = c.put("/api/config", json={"trading": {"min_trade_value": 11}},
              headers={"Authorization": "Bearer secret-token"})
    assert r.status_code == 200


def test_reads_and_health_open_even_with_token(engine, settings):
    settings.update({"web": {"auth_token": "secret-token"}})
    c = TestClient(create_app(engine))
    assert c.get("/api/health").status_code == 200      # container healthcheck must work
    assert c.get("/api/status").status_code == 200


def test_no_auth_required_when_token_unset(engine, settings):
    c = TestClient(create_app(engine))                   # loopback default, no token
    assert c.put("/api/config", json={"trading": {"min_trade_value": 11}}).status_code == 200
