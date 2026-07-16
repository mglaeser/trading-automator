"""Blast-radius cap on the irreversible money-moving capability (A-11/A-34/A-35/B-08/B-26).

Every trade passes through engine._swap, the single chokepoint. Two deterministic
limits are enforced there:
  - max_swap_value: a single swap worth more than this is clamped down (never up).
  - daily_trade_cap: when a swap would push the rolling 24h traded quote value over
    the cap, the swap is refused AND the engine auto-halts (the kill switch fires
    itself) -- latching off until the operator presses Start.
A cap of 0 disables that limit. These apply in dry-run too, so the behaviour is
previewed before real money can move.
"""
import pytest


def test_swap_clamps_to_per_swap_ceiling(engine, fake_client_factory, settings):
    settings.update({"trading": {"max_swap_value": 100.0, "daily_trade_cap": 0.0}})
    fake = fake_client_factory([("BTC", 1.0, 500.0)])  # price 500/BTC
    engine._swap(fake, "BTC", "USDT", 1.0)             # 1 BTC = 500, over the 100 ceiling
    f, t, amt = fake.swaps[0]
    assert (f, t) == ("BTC", "USDT")
    assert abs(amt - 0.2) < 1e-6                        # clamped to 100-worth = 0.2 BTC


def test_swap_ceiling_does_not_raise_small_swaps(engine, fake_client_factory, settings):
    settings.update({"trading": {"max_swap_value": 1000.0, "daily_trade_cap": 0.0}})
    fake = fake_client_factory([("BTC", 1.0, 500.0)])
    engine._swap(fake, "BTC", "USDT", 1.0)             # 500 < 1000: untouched
    assert fake.swaps[0][2] == 1.0


def test_daily_cap_refuses_and_halts_engine(engine, fake_client_factory, settings, monkeypatch):
    monkeypatch.setattr(engine, "_initial_pass", lambda: None)
    settings.update({"binance": {"api_key": "k", "api_secret": "s"},
                     "trading": {"max_swap_value": 1000.0, "daily_trade_cap": 150.0}})
    engine.start()
    assert engine.state.engine_running is True
    fake = fake_client_factory([("BTC", 1.0, 100.0)])  # price 100

    engine._swap(fake, "BTC", "USDT", 1.0)             # +100, under the 150 cap
    assert len(fake.swaps) == 1

    with pytest.raises(Exception):                      # +100 -> 200 > 150: refuse
        engine._swap(fake, "BTC", "USDT", 1.0)
    assert len(fake.swaps) == 1                          # the second trade never executed
    assert engine.state.engine_running is False         # engine auto-halted itself
    assert settings.get("runtime.engine_enabled") is False  # halt persisted across restart


def test_caps_disabled_when_zero(engine, fake_client_factory, settings):
    settings.update({"trading": {"max_swap_value": 0.0, "daily_trade_cap": 0.0}})
    fake = fake_client_factory([("BTC", 1.0, 100000.0)])  # a huge swap
    engine._swap(fake, "BTC", "USDT", 1.0)
    assert fake.swaps[0][2] == 1.0                        # not clamped when disabled
