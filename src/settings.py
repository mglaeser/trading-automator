"""Central configuration store.

Configuration lives in ``config/config.json`` (gitignored) and can be edited
through the web UI. Precedence:

  1. Values saved through the UI (persisted in the config file) always win.
  2. Environment variables only *bootstrap* keys the file does not define yet
     -- so a stale ``.env`` can never silently revert a decision made in the
     UI (e.g. flip dry-run back off after a container restart).
  3. Built-in defaults fill the rest.

Secrets are never returned to the UI in clear text -- they are masked, and a
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

# Subtrees that are replaced wholesale instead of deep-merged: the UI always
# submits the complete document for these, and a merge would make it
# impossible to ever delete an entry (e.g. remove an asset from the universe).
REPLACE_PATHS = {"trading.assets"}

DEFAULTS = {
    "exchange": "binance",  # binance | etoro
    "dry_run": True,
    "runtime": {
        # Persisted engine switch: an explicit stop in the UI survives
        # container restarts; AUTOSTART only applies while this is true.
        "engine_enabled": True,
    },
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
        # keep this asset at a fixed share of the portfolio. Adjustments are
        # clamped to [anchor_swap_min, anchor_swap_max] per cycle, so large
        # deviations converge incrementally instead of moving big amounts.
        "anchor_asset": "BNB",
        "anchor_target_percent": 10.3,
        "anchor_swap_min": 2.5,
        "anchor_swap_max": 15.0,
        # Fiat-inflow split (was handle_euro_balance): when the quote balance
        # GREW by an amount inside this window since the end of the previous
        # rebalance cycle, a slice of the inflow buys the anchor asset. Only
        # the delta counts -- a standing cash reserve never triggers it.
        "inflow_min": 300.0,
        "inflow_max": 750.0,
        "inflow_anchor_ratio": 0.103,
        # Rebalancing behaviour
        "reserve_percent": 0.70,      # share always kept in the quote asset when bullish
        "rebalance_delta": 0.05,      # only act when allocation is off by more than this
        "min_trade_value": 10.0,      # skip trades below this quote value
        "dust_threshold": 10.0,       # sweep balances below this quote value
        "analysis_interval": "30m",
        # How long cached TA/LLM responses stay valid in dry-run (seconds).
        "cache_max_age": 1800,
        # Universe of tradeable assets (mirrors the old crypto_dict).
        # "symbol"/"screener_exchange" feed TradingView TA; "crypto" marks
        # assets that get sold in a bearish market; "preferred" biases the
        # pairwise LLM comparison. Assets NOT listed here are never touched.
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
        # Randomised base intervals in minutes, [min, max] per job and period.
        # Changes apply from the next scheduling of each job.
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
        # Sentiment-driven cadence for the rebalance job: after each market
        # evaluation the engine overrides the base interval with these until
        # the sentiment changes again.
        "sentiment_rebalance": {
            "bullish": [8, 13],
            "bearish": [45, 75],
            "neutral": [30, 45],
        },
    },
    "web": {
        "host": "0.0.0.0",
        "port": 8000,
    },
}

# Environment variable -> dotted config path (bootstrap only, see module doc)
ENV_OVERRIDES = {
    "EXCHANGE": "exchange",
    "DRY_RUN": "dry_run",
    "BINANCE_API_KEY": "binance.api_key",
    "BINANCE_API_SECRET": "binance.api_secret",
    "ETORO_API_KEY": "etoro.api_key",
    "ETORO_USER_KEY": "etoro.user_key",
    "ANTHROPIC_API_KEY": "llm.anthropic_api_key",
    "OPENAI_API_KEY": "llm.openai_api_key",
    "SMS_ENABLED": "sms.enabled",
    "SMS_AUTH_TOKEN": "sms.auth_token",
    "SMS_RECIPIENT": "sms.recipient",
    "WEB_HOST": "web.host",
    "WEB_PORT": "web.port",
}


def exchange_configured(settings):
    """True when the selected exchange has credentials to work with."""
    exchange = str(settings.get("exchange", "binance")).lower()
    if exchange == "binance":
        return bool(settings.get("binance.api_key")
                    and settings.get("binance.api_secret"))
    if exchange == "etoro":
        return bool(settings.get("etoro.api_key")
                    and settings.get("etoro.user_key"))
    return False


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


def _deep_merge(base, override, prefix=""):
    """Merge ``override`` into ``base``; REPLACE_PATHS subtrees are swapped
    wholesale so entries can actually be deleted through the UI."""
    for key, value in override.items():
        dotted = f"{prefix}{key}"
        if (dotted not in REPLACE_PATHS
                and isinstance(value, dict) and isinstance(base.get(key), dict)):
            _deep_merge(base[key], value, dotted + ".")
        else:
            base[key] = value
    return base


def _leaf_paths(data, prefix=""):
    paths = set()
    for key, value in data.items():
        dotted = f"{prefix}{key}"
        if isinstance(value, dict) and dotted not in REPLACE_PATHS:
            paths |= _leaf_paths(value, dotted + ".")
        else:
            paths.add(dotted)
    return paths


def _coerce(value, template):
    """Coerce an incoming value to the shape of the default it replaces.

    Raises TypeError/ValueError on values that cannot be made to fit (the
    caller drops those keys, keeping the stored value)."""
    if isinstance(template, bool):
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "t", "yes", "y", "on")
        return bool(value)
    if isinstance(template, int) and not isinstance(template, bool):
        return int(value)
    if isinstance(template, float):
        return float(value)
    if isinstance(template, list):
        # e.g. schedule intervals: must be a list of numbers, same length
        if not isinstance(value, list):
            raise TypeError(f"expected a list, got {type(value).__name__}")
        if template and all(isinstance(t, (int, float)) for t in template):
            coerced = [float(v) for v in value]
            if len(template) and len(coerced) != len(template):
                raise ValueError(f"expected {len(template)} numbers")
            return coerced
        return value
    return value


class Settings:
    """Thread-safe configuration with JSON persistence."""

    def __init__(self, path=CONFIG_PATH):
        self._path = Path(path)
        self._lock = threading.RLock()
        self._data = copy.deepcopy(DEFAULTS)
        file_keys = self._load_file()
        self._apply_env(skip=file_keys)

    # -- persistence ------------------------------------------------------

    def _load_file(self):
        """Merge the config file in; return the set of leaf paths it defines."""
        if not self._path.exists():
            return set()
        try:
            stored = json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"Could not read {self._path}: {exc}") from exc
        _deep_merge(self._data, stored)
        return _leaf_paths(stored)

    def _apply_env(self, skip=()):
        """Environment variables bootstrap keys the file does not define."""
        for env_name, dotted in ENV_OVERRIDES.items():
            raw = os.getenv(env_name)
            if raw is None or raw == "" or dotted in skip:
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

        Masked secret values are dropped so an untouched password field never
        overwrites the stored secret; values that fail type coercion are
        dropped so the stored value survives."""

        def scrub(node, prefix=""):
            for key in list(node.keys()):
                dotted = f"{prefix}{key}"
                value = node[key]
                if isinstance(value, dict) and dotted not in REPLACE_PATHS:
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
