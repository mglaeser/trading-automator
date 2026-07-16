import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.exchanges.base import (  # noqa: E402
    Balance,
    ExchangeClient,
    SwapResult,
    add_percentages,
)
from src.settings import Settings  # noqa: E402
from src.state import EngineState  # noqa: E402


class FakeClient(ExchangeClient):
    """In-memory exchange used by the engine tests. Prices are implied by
    the (asset, amount, quote_value) triples it is seeded with."""

    name = "fake"

    def __init__(self, balances, quote_asset="USDT", loan=0.0):
        super().__init__(quote_asset=quote_asset, dry_run=True)
        self._balances = list(balances)
        self._loan = loan
        self.swaps = []

    def test_connection(self):
        return "fake OK"

    def get_balances(self, min_quote_value=0.01):
        return add_percentages(
            [Balance(a, amt, val) for a, amt, val in self._balances]
        )

    def get_price(self, asset, quote=None):
        for a, amt, val in self._balances:
            if a == asset and amt:
                return val / amt
        return 1.0

    def swap(self, from_asset, to_asset, amount):
        self.swaps.append((from_asset, to_asset, amount))
        return SwapResult(from_asset, to_asset, amount,
                          amount * self.get_price(from_asset), True, [])

    def get_loan_balance(self):
        return self._loan


@pytest.fixture
def settings(tmp_path, monkeypatch):
    # Isolate from any real environment/config
    for var in ("EXCHANGE", "DRY_RUN", "BINANCE_API_KEY", "BINANCE_API_SECRET",
                "ETORO_API_KEY", "ETORO_USER_KEY", "ANTHROPIC_API_KEY",
                "OPENAI_API_KEY", "SMS_ENABLED", "SMS_AUTH_TOKEN",
                "SMS_RECIPIENT", "WEB_HOST", "WEB_PORT", "AUTOSTART"):
        monkeypatch.delenv(var, raising=False)
    return Settings(path=tmp_path / "config.json")


@pytest.fixture
def engine(settings, monkeypatch):
    # Cache dir must not leak between tests / into the repo
    import src.cache as cache
    monkeypatch.setattr(cache, "CACHE_DIR",
                        type(cache.CACHE_DIR)(tempfile.mkdtemp()))
    from src.engine import TradingEngine
    return TradingEngine(settings, EngineState())


@pytest.fixture
def fake_client_factory():
    return FakeClient
