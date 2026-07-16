from typing import TYPE_CHECKING

from .base import Balance, ExchangeClient, ExchangeError
from .binance_client import BinanceClient
from .etoro_client import EToroClient

if TYPE_CHECKING:
    from ..settings import Settings


def create_client(settings: "Settings", dry_run: bool | None = None) -> ExchangeClient:
    """Build the exchange client selected in settings."""
    name = settings.get("exchange", "binance").lower()
    if dry_run is None:
        dry_run = settings.get("dry_run", True)

    if name == "binance":
        cfg = settings.get("binance", {})
        return BinanceClient(
            api_key=cfg.get("api_key", ""),
            api_secret=cfg.get("api_secret", ""),
            base_url=cfg.get("base_url", "https://api.binance.com"),
            quote_asset=settings.get("trading.quote_asset", "USDT"),
            dry_run=dry_run,
        )
    if name == "etoro":
        cfg = settings.get("etoro", {})
        return EToroClient(
            api_key=cfg.get("api_key", ""),
            user_key=cfg.get("user_key", ""),
            base_url=cfg.get("base_url", "https://api.etoro.com"),
            quote_asset=settings.get("trading.quote_asset", "USDT"),
            dry_run=dry_run,
        )
    raise ExchangeError(f"Unknown exchange '{name}' (expected 'binance' or 'etoro')")


__all__ = [
    "Balance",
    "ExchangeClient",
    "ExchangeError",
    "BinanceClient",
    "EToroClient",
    "create_client",
]
