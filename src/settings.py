"""Central configuration store.

Configuration lives in ``config/config.json`` (gitignored) and can be edited
through the web UI. Environment variables override file values on startup so
the app also works fully headless / containerised.

Secrets are never returned to the UI in clear text -- they are masked and a
masked value sent back by the UI is ignored on save.
"""

import copy
import json
import os
import threading
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

CONFIG_PATH = Path(os.getenv("CONFIG_PATH", "config/config.json"))

MASK = "••••••••"

# Dotted paths of fields that must be masked in API responses.
SECRET_PATHS = {
    "binance.api_key",
    "binance.api_secret",
    "etoro.api_key",
    "etoro.user_key",
    "llm.anthropic_api_key",
    "llm.openai_api_key",
    "sms.auth_token",
}

DEFAULTS = {
    "exchange": "binance",  # binance | etoro
    "dry_run": True,
    "binance": {
        "api_key": "",
        "api_secret": "",
        "base_url": "https://api.binance.com",
    },
    "etoro": {
        "api_key": "",
        "user_key": "",
        "base_url": "https://api.etoro.com",
    },
    "llm": {
        "anthropic_api_key": "",
        "anthropic_model": "claude-sonnet-5",
        "openai_api_key": "",
        "openai_model": "gpt-4o-mini",
    },
    "sms": {
        "enabled": False,
        "auth_token": "",
        "sms_id": "s0",
        "recipient": "",
    },
    "trading": {
        # Quote/stable asset used as the intermediate for all swaps and as the
        # "cash" position (was USDT on Nexo).
        "quote_asset": "USDT",
        # Anchor asset target: generalisation of the old NEXO loyalty level --
        # keep this asset at a fixed share of the portfolio.
        "anchor_asset": "BNB",
        "anchor_target_percent": 10.3,
        "anchor_swap_min": 2.5,
        "anchor_swap_max": 15.0,
        # Fiat-inflow split (was handle_euro_balance): when the quote balance
        # is inside this window, split part of it into the anchor asset.
        "inflow_min": 300.0,
        "inflow_max": 750.0,
        "inflow_anchor_ratio": 0.103,
        # Rebalancing behaviour
        "reserve_percent": 0.70,      # share always kept in the quote asset when bullish
        "rebalance_delta": 0.05,      # only act when allocation is off by more than this
        "min_trade_value": 10.0,      # skip trades below this quote value
        "dust_threshold": 10.0,       # sweep balances below this quote value
        "analysis_interval": "30m",
        # Universe of tradeable assets (mirrors the old crypto_dict).
        # "symbol"/"screener_exchange" feed TradingView TA; "crypto" marks
        # assets that get sold in a bearish market; "preferred" biases the
        # pairwise LLM comparison.
        "assets": {
            "BTC":  {"symbol": "BTCUSD",  "screener_exchange": "BINANCE", "preferred": False, "crypto": True},
            "ETH":  {"symbol": "ETHUSD",  "screener_exchange": "BINANCE", "preferred": False, "crypto": True},
            "PAXG": {"symbol": "PAXGUSD", "screener_exchange": "BINANCE", "preferred": True,  "crypto": True},
            "BNB":  {"symbol": "BNBUSD",  "screener_exchange": "BINANCE", "preferred": True,  "crypto": True},
            "AAVE": {"symbol": "AAVEUSD", "screener_exchange": "BINANCE", "preferred": True,  "crypto": True},
            "USDT": {"symbol": "USDTEUR", "screener_exchange": "COINBASE", "preferred": True, "crypto": False},
        },
    },
    "schedule": {
        # Location used for the day/night switch (sunrise/sunset).
        "latitude": 52.52,
        "longitude": 13.405,
        "timezone": "Europe/Berlin",
        # Randomised intervals in minutes, [min, max] per job and period.
        "daytime": {
            "refresh": [30, 45],
            "rebalance": [10, 15],
            "repay": [300, 360],
        },
        "nighttime": {
            "refresh": [20, 40],
            "rebalance": [20, 40],
            "repay": [720, 900],
        },
    },
    "web": {
        "host": "0.0.0.0",
        "port": 8000,
    },
}

# Environment variable -> dotted config path
ENV_OVERRIDES = {
    "EXCHANGE": "exchange",
    "DRY_RUN": "dry_run",
    "BINANCE_API_KEY": "binance.api_key",
    "BINANCE_API_SECRET": "binance.api_secret",
    "ETORO_API_KEY": "etoro.api_key",
    "ETORO_USER_KEY": "etoro.user_key",
    "ANTHROPIC_API_KEY": "llm.anthropic_api_key",
    "OPENAI_API_KEY": "llm.openai_api_key",
    "SMS_AUTH_TOKEN": "sms.auth_token",
    "SMS_RECIPIENT": "sms.recipient",
    "WEB_HOST": "web.host",
    "WEB_PORT": "web.port",
}


def _get_path(data, dotted):
    node = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _set_path(data, dotted, value):
    parts = dotted.split(".")
    node = data
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _deep_merge(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _coerce(value, template):
    """Coerce an incoming value to the type of the default it replaces."""
    if isinstance(template, bool):
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "t", "yes", "y", "on")
        return bool(value)
    if isinstance(template, int) and not isinstance(template, bool):
        return int(value)
    if isinstance(template, float):
        return float(value)
    return value


class Settings:
    """Thread-safe configuration with JSON persistence."""

    def __init__(self, path=CONFIG_PATH):
        self._path = Path(path)
        self._lock = threading.RLock()
        self._data = copy.deepcopy(DEFAULTS)
        self._load_file()
        self._apply_env()

    # -- persistence ------------------------------------------------------

    def _load_file(self):
        if self._path.exists():
            try:
                stored = json.loads(self._path.read_text())
                _deep_merge(self._data, stored)
            except (json.JSONDecodeError, OSError) as exc:
                raise RuntimeError(f"Could not read {self._path}: {exc}") from exc

    def _apply_env(self):
        for env_name, dotted in ENV_OVERRIDES.items():
            raw = os.getenv(env_name)
            if raw is None or raw == "":
                continue
            template = _get_path(DEFAULTS, dotted)
            _set_path(self._data, dotted, _coerce(raw, template))

    def save(self):
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._data, indent=2))

    # -- access -----------------------------------------------------------

    def get(self, dotted, default=None):
        with self._lock:
            value = _get_path(self._data, dotted)
            return copy.deepcopy(value) if value is not None else default

    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self._data)

    def masked(self):
        """Snapshot safe to send to the browser (secrets replaced by MASK)."""
        data = self.snapshot()
        for dotted in SECRET_PATHS:
            current = _get_path(data, dotted)
            if current:
                _set_path(data, dotted, MASK)
        return data

    def update(self, incoming):
        """Deep-merge a (possibly partial) config coming from the UI.

        Masked secret values are dropped so an untouched password field does
        not overwrite the stored secret.
        """

        def scrub(node, prefix=""):
            for key in list(node.keys()):
                dotted = f"{prefix}{key}"
                value = node[key]
                if isinstance(value, dict):
                    scrub(value, dotted + ".")
                elif dotted in SECRET_PATHS and value == MASK:
                    del node[key]
                else:
                    template = _get_path(DEFAULTS, dotted)
                    if template is not None and not isinstance(template, dict):
                        try:
                            node[key] = _coerce(value, template)
                        except (TypeError, ValueError):
                            del node[key]

        incoming = copy.deepcopy(incoming)
        scrub(incoming)
        with self._lock:
            _deep_merge(self._data, incoming)
            self.save()
