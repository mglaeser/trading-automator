"""Common exchange abstraction.

Everything the trading engine needs from an exchange is expressed here, so
Binance and eToro (and future exchanges) are interchangeable. This replaces
the old Selenium page-scraping layer (login, captcha solving, DOM parsing).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class ExchangeError(RuntimeError):
    """Raised for any exchange API failure."""


@dataclass
class Balance:
    """One asset position, valued in the quote asset.

    Mirrors the old Nexo dashboard row: amount_nativ / amount_fiat / percentage.
    """

    asset: str
    amount: float                 # native units (was amount_nativ)
    quote_value: float            # value in quote asset (was amount_fiat)
    percentage: float = 0.0      # share of total portfolio value

    def to_dict(self):
        return {
            "asset": self.asset,
            "amount": self.amount,
            "quote_value": round(self.quote_value, 2),
            "percentage": round(self.percentage, 2),
        }


@dataclass
class SwapResult:
    from_asset: str
    to_asset: str
    amount: float                 # native units of from_asset
    quote_value: float
    dry_run: bool
    orders: list = field(default_factory=list)

    def to_dict(self):
        return {
            "from_asset": self.from_asset,
            "to_asset": self.to_asset,
            "amount": self.amount,
            "quote_value": round(self.quote_value, 2),
            "dry_run": self.dry_run,
            "orders": self.orders,
        }


def add_percentages(balances):
    """Fill in the portfolio share of each balance (was
    add_native_amount_percentages)."""
    total = sum(b.quote_value for b in balances)
    for b in balances:
        b.percentage = (b.quote_value / total * 100.0) if total else 0.0
    return balances


class ExchangeClient(ABC):
    """Interface every exchange adapter implements."""

    name = "abstract"

    def __init__(self, quote_asset="USDT", dry_run=True):
        self.quote_asset = quote_asset
        self.dry_run = dry_run

    # -- account ----------------------------------------------------------

    @abstractmethod
    def test_connection(self):
        """Return a short human-readable string on success, raise on failure."""

    @abstractmethod
    def get_balances(self, min_quote_value=0.01):
        """Return list[Balance] for all assets above the given quote value,
        with percentages filled in."""

    # -- market data ------------------------------------------------------

    @abstractmethod
    def get_price(self, asset, quote=None):
        """Price of one unit of ``asset`` in ``quote`` (default: quote_asset)."""

    # -- trading ----------------------------------------------------------

    @abstractmethod
    def swap(self, from_asset, to_asset, amount):
        """Convert ``amount`` native units of from_asset into to_asset.

        Replaces the old Nexo swap page automation. Returns SwapResult.
        Implementations must honour ``self.dry_run``.
        """

    # -- credit (optional; was the Nexo loan) -------------------------------

    def get_loan_balance(self):
        """Outstanding borrowed amount in quote asset. 0.0 when unsupported."""
        return 0.0

    def repay_loan(self, asset, amount=None):
        """Repay an outstanding loan with ``asset`` (None = repay maximum).

        Raises ExchangeError when the exchange has no credit facility.
        """
        raise ExchangeError(f"{self.name} does not support loan repayment")
