from src.settings import MASK, Settings, exchange_configured


def test_secret_masking_roundtrip(settings):
    settings.update({"binance": {"api_key": "real-key", "api_secret": "real-secret"}})
    masked = settings.masked()
    assert masked["binance"]["api_key"] == MASK

    # a masked value sent back must not overwrite the stored secret
    settings.update({"binance": {"api_key": MASK}})
    assert settings.get("binance.api_key") == "real-key"


def test_persistence(settings):
    settings.update({"trading": {"min_trade_value": 12}})
    reloaded = Settings(path=settings._path)
    assert reloaded.get("trading.min_trade_value") == 12.0


def test_env_bootstraps_but_file_wins(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setenv("DRY_RUN", "false")
    s = Settings(path=path)
    assert s.get("dry_run") is False  # env bootstraps the fresh config

    # the user flips dry-run on in the UI; the file now defines the key
    s.update({"dry_run": True})

    # a restart with the stale env var must NOT revert the UI decision
    s2 = Settings(path=path)
    assert s2.get("dry_run") is True


def test_assets_are_replaced_not_merged(settings):
    assert "AAVE" in settings.get("trading.assets")
    new_universe = {"BTC": {"symbol": "BTCUSD", "screener_exchange": "BINANCE",
                            "preferred": False, "crypto": True}}
    settings.update({"trading": {"assets": new_universe}})
    assert list(settings.get("trading.assets")) == ["BTC"]  # AAVE etc. gone


def test_interval_coercion_rejects_garbage(settings):
    before = settings.get("schedule.daytime.refresh")
    settings.update({"schedule": {"daytime": {"refresh": "30-45"}}})  # string
    assert settings.get("schedule.daytime.refresh") == before  # dropped
    settings.update({"schedule": {"daytime": {"refresh": [10, 20]}}})
    assert settings.get("schedule.daytime.refresh") == [10.0, 20.0]


def test_exchange_configured_case_insensitive(settings):
    settings.update({"exchange": "Binance",
                     "binance": {"api_key": "k", "api_secret": "s"}})
    assert exchange_configured(settings) is True


def test_bool_coercion_from_strings(settings):
    settings.update({"dry_run": "false"})
    assert settings.get("dry_run") is False
    settings.update({"sms": {"enabled": "true"}})
    assert settings.get("sms.enabled") is True
