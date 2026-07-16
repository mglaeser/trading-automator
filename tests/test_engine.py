import time

from src.engine import asset_distribution_from_recommendation, round_down


def test_distribution_scoring():
    recs = [
        {"action": "sell_buy", "assets": ["PAXG", "BTC"], "confidence": 1.0},
        {"action": "buy", "assets": ["BTC", "BNB"], "confidence": 0.8},
        {"action": "sell", "assets": ["PAXG", "AAVE"], "confidence": 0.5},
        {"error": "boom"},  # errored pair must be ignored
    ]
    dist = dict(asset_distribution_from_recommendation(recs, 0.7))
    assert dist["PAXG"] == 0.0 and dist["AAVE"] == 0.0
    assert abs(sum(dist.values()) - 0.3) < 1e-6
    assert dist["BTC"] > dist["BNB"] > 0
    assert round_down(10.239) == 10.23


def test_distribution_all_hold_returns_zeros():
    recs = [{"action": "hold", "assets": ["BTC", "BNB"], "confidence": 0.9}]
    dist = asset_distribution_from_recommendation(recs, 0.7)
    assert dist and all(pct == 0.0 for _, pct in dist)


def test_anchor_target_buys_deficit(engine, fake_client_factory, settings):
    settings.update({"trading": {"anchor_asset": "BNB", "anchor_swap_max": 100.0}})
    fake = fake_client_factory([("USDT", 950.0, 950.0), ("BNB", 0.1, 50.0)])
    assert engine.maintain_anchor_target(fake) is True
    frm, to, amount = fake.swaps[0]
    assert (frm, to) == ("USDT", "BNB")
    assert abs(amount - 53.0) < 0.5  # 10.3% of 1000 minus held 50


def test_anchor_target_caps_large_swaps(engine, fake_client_factory, settings):
    settings.update({"trading": {"anchor_asset": "BNB", "anchor_swap_max": 15.0}})
    # deficit is ~53 -> must be capped to 15, not skipped
    fake = fake_client_factory([("USDT", 950.0, 950.0), ("BNB", 0.1, 50.0)])
    assert engine.maintain_anchor_target(fake) is True
    assert fake.swaps[0][2] == 15.0


def test_inflow_split_requires_baseline(engine, fake_client_factory):
    # no baseline yet: a standing 500 USDT reserve must NOT look like a deposit
    fake = fake_client_factory([("USDT", 500.0, 500.0)])
    assert engine.handle_inflow_split(fake) is False
    assert fake.swaps == []


def test_inflow_split_fires_on_delta_only(engine, fake_client_factory, settings):
    settings.update({"trading": {"anchor_asset": "BNB"}})
    engine._last_cycle_quote = 200.0  # post-cycle baseline

    # +100 since baseline: below the 300 minimum -> nothing
    fake = fake_client_factory([("USDT", 300.0, 300.0)])
    assert engine.handle_inflow_split(fake) is False

    # +500 since baseline: inside the window -> anchor slice bought
    fake = fake_client_factory([("USDT", 700.0, 700.0)])
    assert engine.handle_inflow_split(fake) is True
    frm, to, amount = fake.swaps[0]
    assert (frm, to) == ("USDT", "BNB")
    assert abs(amount - 500 * 0.103) < 0.02


def test_swap_to_target_sells_before_buys_and_funds_them(engine, fake_client_factory):
    fake = fake_client_factory([("USDT", 400.0, 400.0), ("BTC", 0.01, 600.0)])
    engine.swap_to_target(fake, fake.get_balances(), [("USDT", 0.7), ("BNB", 0.3)])
    kinds = [(f, t) for f, t, _ in fake.swaps]
    assert ("BTC", "USDT") in kinds and ("USDT", "BNB") in kinds
    assert kinds.index(("BTC", "USDT")) < kinds.index(("USDT", "BNB"))


def test_swap_to_target_clamps_buys_to_available_quote(engine, fake_client_factory):
    # PAXG is within the delta threshold (no funding sell happens); the BNB
    # buy wants 60 USDT but only 20 are available -> clamped to 20.
    fake = fake_client_factory([("USDT", 20.0, 20.0), ("PAXG", 0.4, 980.0)])
    engine.swap_to_target(fake, fake.get_balances(),
                          [("PAXG", 0.94), ("BNB", 0.06)])
    assert fake.swaps == [("USDT", "BNB", 20.0)]


def test_swap_to_target_ignores_unconfigured_assets(engine, fake_client_factory):
    # AIRDROP is not in the configured universe -> never sold
    fake = fake_client_factory([("USDT", 500.0, 500.0), ("AIRDROP", 10.0, 500.0)])
    engine.swap_to_target(fake, fake.get_balances(), [("USDT", 1.0)])
    assert all(f != "AIRDROP" for f, _, _ in fake.swaps)


def test_sell_all_only_configured_crypto(engine, fake_client_factory):
    fake = fake_client_factory([
        ("USDT", 100.0, 100.0),
        ("BTC", 0.01, 600.0),      # configured crypto -> sold
        ("BNB", 1.0, 50.0),        # configured crypto -> sold
        ("AIRDROP", 5.0, 300.0),   # unconfigured -> kept
    ])
    engine.sell_all_crypto(fake)
    sold = {f for f, _, _ in fake.swaps}
    assert sold == {"BTC", "BNB"}


def test_jobs_never_queue(engine, fake_client_factory, monkeypatch):
    import threading

    started = threading.Event()
    release = threading.Event()

    def slow_job():
        started.set()
        release.wait(5)

    t = threading.Thread(target=lambda: engine._run_job("slow", slow_job))
    t.start()
    started.wait(5)
    # second trigger while the first runs: must skip, not block
    before = time.time()
    engine._run_job("second", lambda: None)
    assert time.time() - before < 1.0
    events = engine.state.to_dict()["events"]
    assert any("skipped" in e["message"] for e in events)
    release.set()
    t.join()


def test_engine_start_stop_idempotent_and_persisted(engine, settings, monkeypatch):
    # avoid the initial pass touching a real exchange
    monkeypatch.setattr(engine, "_initial_pass", lambda: None)
    engine.start()
    engine.start()  # idempotent
    assert engine.state.engine_running is True
    assert settings.get("runtime.engine_enabled") is True
    engine.stop()
    engine.stop()
    assert engine.state.engine_running is False
    assert settings.get("runtime.engine_enabled") is False
    assert engine.scheduler.is_running is False
