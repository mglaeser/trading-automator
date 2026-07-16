"""Binance spot + cross-margin adapter.

Implements the ExchangeClient interface with plain signed REST calls
(HMAC-SHA256), no heavyweight SDK required.

Endpoints used:
  GET  /api/v3/account              balances
  GET  /api/v3/ticker/price         prices (bulk)
  GET  /api/v3/exchangeInfo         symbols + lot-size/notional filters
  POST /api/v3/order                market orders (swaps)
  GET  /sapi/v1/margin/account      outstanding margin loans
  POST /sapi/v1/margin/borrow-repay margin loan repayment

Safety properties:
  - LOT_SIZE quantities are quantised with Decimal arithmetic (never
    oversells due to float drift).
  - Every order leg is checked against the pair's minimum notional BEFORE
    anything is placed, so a two-leg swap can never half-execute on a
    too-small second leg.
  - Live sells are clamped to the actual free balance.
  - Error messages never contain signed request URLs (the HMAC signature
    and full query stay in debug logs only).
"""

import hashlib
import hmac
import logging
import time
from decimal import ROUND_DOWN, Decimal
from urllib.parse import urlencode

import requests

from .base import Balance, ExchangeClient, ExchangeError, SwapResult, add_percentages

log = logging.getLogger(__name__)

STABLE_ALIASES = {"USDT", "USDC", "FDUSD", "TUSD", "BUSD"}


def _fmt_qty(value):
    """Format a quantity for the API without scientific notation."""
    return f"{value:.8f}".rstrip("0").rstrip(".")


class BinanceClient(ExchangeClient):
    name = "binance"

    def __init__(self, api_key, api_secret, base_url="https://api.binance.com",
                 quote_asset="USDT", dry_run=True, recv_window=5000, timeout=15):
        super().__init__(quote_asset=quote_asset, dry_run=dry_run)
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.recv_window = recv_window
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"X-MBX-APIKEY": api_key})
        self._symbols = None          # cache of exchangeInfo
        self._symbols_fetched = 0.0
        self._unpriced_warned = set()  # assets we already warned about

    # -- low level ---------------------------------------------------------

    def _request(self, method, path, params=None, signed=False):
        params = dict(params or {})
        if signed:
            if not self.api_key or not self.api_secret:
                raise ExchangeError("Binance API key/secret not configured")
            params["timestamp"] = int(time.time() * 1000)
            params["recvWindow"] = self.recv_window
            query = urlencode(params, doseq=True)
            params["signature"] = hmac.new(
                self.api_secret.encode(), query.encode(), hashlib.sha256
            ).hexdigest()
        try:
            resp = self._session.request(
                method, f"{self.base_url}{path}", params=params, timeout=self.timeout
            )
        except requests.RequestException as exc:
            # Transport exceptions embed the full URL -- for signed requests
            # that includes the query and its signature. Keep the detail in
            # debug logs; surface only the sanitised summary.
            log.debug("Binance transport error on %s %s: %s", method, path, exc)
            raise ExchangeError(
                f"Binance {method} {path} failed: {type(exc).__name__}"
            ) from exc
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("msg", resp.text)
            except ValueError:
                detail = resp.text
            raise ExchangeError(f"Binance {path} -> {resp.status_code}: {detail}")
        return resp.json()

    # -- symbols / filters ---------------------------------------------------

    def _exchange_info(self):
        # refresh symbol cache at most every 6 hours
        if self._symbols is None or time.time() - self._symbols_fetched > 6 * 3600:
            data = self._request("GET", "/api/v3/exchangeInfo")
            self._symbols = {}
            for sym in data.get("symbols", []):
                if sym.get("status") != "TRADING":
                    continue
                filters = {f["filterType"]: f for f in sym.get("filters", [])}
                self._symbols[(sym["baseAsset"], sym["quoteAsset"])] = {
                    "symbol": sym["symbol"],
                    "base": sym["baseAsset"],
                    "quote": sym["quoteAsset"],
                    "step": float(filters.get("LOT_SIZE", {}).get("stepSize", 0) or 0),
                    "min_notional": float(
                        filters.get("NOTIONAL", {}).get("minNotional", 0)
                        or filters.get("MIN_NOTIONAL", {}).get("minNotional", 0)
                        or 0
                    ),
                }
            self._symbols_fetched = time.time()
        return self._symbols

    def _find_symbol(self, base, quote):
        return self._exchange_info().get((base, quote))

    @staticmethod
    def _round_step(quantity, step):
        """Quantise down to the pair's LOT_SIZE step (Decimal: exact)."""
        if not step:
            return quantity
        q, s = Decimal(str(quantity)), Decimal(str(step))
        return float((q / s).to_integral_value(rounding=ROUND_DOWN) * s)

    @staticmethod
    def _check_notional(info, notional):
        """Fail fast when an order would violate the pair's minimum value."""
        minimum = info.get("min_notional") or 0.0
        if minimum and notional < minimum:
            raise ExchangeError(
                f"{info['symbol']}: order value {notional:.2f} {info['quote']} "
                f"is below the exchange minimum of {minimum:g}"
            )

    def _free_balance(self, asset):
        acct = self._request("GET", "/api/v3/account", signed=True)
        for entry in acct.get("balances", []):
            if entry["asset"] == asset:
                return float(entry["free"])
        return 0.0

    # -- ExchangeClient ------------------------------------------------------

    def test_connection(self):
        self._request("GET", "/api/v3/ping")
        acct = self._request("GET", "/api/v3/account", signed=True)
        perms = ",".join(acct.get("permissions", [])) or "unknown"
        return f"Binance OK (account permissions: {perms})"

    def _price_map(self):
        tickers = self._request("GET", "/api/v3/ticker/price")
        return {t["symbol"]: float(t["price"]) for t in tickers}

    def get_price(self, asset, quote=None):
        quote = quote or self.quote_asset
        if asset == quote or (asset in STABLE_ALIASES and quote in STABLE_ALIASES):
            return 1.0
        prices = self._price_map()
        if asset + quote in prices:
            return prices[asset + quote]
        if quote + asset in prices and prices[quote + asset]:
            return 1.0 / prices[quote + asset]
        # route via USDT
        if asset + "USDT" in prices and quote + "USDT" in prices and prices[quote + "USDT"]:
            return prices[asset + "USDT"] / prices[quote + "USDT"]
        raise ExchangeError(f"No price route for {asset}/{quote}")

    def get_balances(self, min_quote_value=0.01):
        acct = self._request("GET", "/api/v3/account", signed=True)
        prices = self._price_map()

        def value_of(asset, amount):
            if asset == self.quote_asset:
                return amount
            sym = asset + self.quote_asset
            rev = self.quote_asset + asset
            if sym in prices:
                return amount * prices[sym]
            if rev in prices and prices[rev]:
                return amount / prices[rev]
            if asset + "USDT" in prices and self.quote_asset + "USDT" in prices:
                return amount * prices[asset + "USDT"] / prices[self.quote_asset + "USDT"]
            if asset not in self._unpriced_warned:
                self._unpriced_warned.add(asset)
                log.warning("get_balances: no price route for %s (amount %s), "
                            "excluding it from the portfolio value", asset, amount)
            return 0.0

        balances = []
        for entry in acct.get("balances", []):
            amount = float(entry["free"]) + float(entry["locked"])
            if amount <= 0:
                continue
            quote_value = value_of(entry["asset"], amount)
            if quote_value >= min_quote_value:
                balances.append(Balance(entry["asset"], amount, quote_value))
        balances.sort(key=lambda b: b.quote_value, reverse=True)
        return add_percentages(balances)

    def _market_order(self, symbol_info, side, quantity=None, quote_qty=None):
        params = {"symbol": symbol_info["symbol"], "side": side, "type": "MARKET"}
        if quantity is not None:
            qty = self._round_step(quantity, symbol_info["step"])
            if qty <= 0:
                raise ExchangeError(
                    f"Quantity {quantity} rounds to zero for {symbol_info['symbol']}"
                )
            params["quantity"] = _fmt_qty(qty)
        else:
            params["quoteOrderQty"] = _fmt_qty(quote_qty)

        if self.dry_run:
            log.info("[DRY RUN] Binance order: %s", params)
            return {"dry_run": True, **params}
        return self._request("POST", "/api/v3/order", params=params, signed=True)

    def swap(self, from_asset, to_asset, amount):
        """Market-convert from_asset -> to_asset.

        Uses a direct trading pair when one exists, otherwise routes through
        the quote asset in two legs (e.g. PAXG -> USDT -> BNB). Both legs are
        validated against the exchange minimums before any order is placed.
        """
        if from_asset == to_asset:
            raise ExchangeError("swap: from and to asset are identical")

        if not self.dry_run:
            # Never try to sell more than is actually free (fees/rounding
            # can make the engine's view slightly optimistic).
            free = self._free_balance(from_asset)
            if free <= 0:
                raise ExchangeError(f"No free {from_asset} balance to swap")
            amount = min(amount, free)

        quote_value = amount * self.get_price(from_asset)
        orders = []

        direct = self._find_symbol(from_asset, to_asset)
        reverse = self._find_symbol(to_asset, from_asset)
        if direct:  # SELL base for quote
            self._check_notional(direct, amount * self.get_price(from_asset, to_asset))
            orders.append(self._market_order(direct, "SELL", quantity=amount))
        elif reverse:  # BUY base spending quote
            self._check_notional(reverse, amount)
            orders.append(self._market_order(reverse, "BUY", quote_qty=amount))
        else:
            # two legs through the configured quote asset; the buy leg gets a
            # small haircut for the sell leg's fee
            leg1 = self._find_symbol(from_asset, self.quote_asset)
            leg2 = self._find_symbol(to_asset, self.quote_asset)
            if not leg1 or not leg2:
                raise ExchangeError(f"No trade route {from_asset} -> {to_asset}")
            buy_value = quote_value * 0.999
            self._check_notional(leg1, quote_value)
            self._check_notional(leg2, buy_value)
            orders.append(self._market_order(leg1, "SELL", quantity=amount))
            orders.append(self._market_order(leg2, "BUY", quote_qty=buy_value))

        log.info("Swap %s %s -> %s (~%.2f %s)%s",
                 amount, from_asset, to_asset, quote_value, self.quote_asset,
                 " [DRY RUN]" if self.dry_run else "")
        return SwapResult(from_asset, to_asset, amount, quote_value,
                          self.dry_run, orders)

    # -- margin loan ---------------------------------------------------------

    def get_loan_balance(self):
        try:
            margin = self._request("GET", "/sapi/v1/margin/account", signed=True)
        except ExchangeError as exc:
            # margin not enabled on this account -> treat as "no loan"
            log.debug("Margin account unavailable: %s", exc)
            return 0.0
        total = 0.0
        for entry in margin.get("userAssets", []):
            borrowed = float(entry.get("borrowed", 0)) + float(entry.get("interest", 0))
            if borrowed <= 0:
                continue
            total += borrowed * (1.0 if entry["asset"] == self.quote_asset
                                 else self.get_price(entry["asset"]))
        return total

    def repay_loan(self, asset, amount=None):
        margin = self._request("GET", "/sapi/v1/margin/account", signed=True)
        entry = next((e for e in margin.get("userAssets", [])
                      if e["asset"] == asset), None)
        if entry is None:
            raise ExchangeError(f"No margin position for {asset}")
        borrowed = float(entry.get("borrowed", 0)) + float(entry.get("interest", 0))
        free = float(entry.get("free", 0))
        repay = min(borrowed, free) if amount is None else min(amount, borrowed, free)
        if repay <= 0:
            return {"repaid": 0.0, "asset": asset}
        params = {
            "asset": asset,
            "amount": f"{repay:.8f}",
            "isIsolated": "FALSE",
            "type": "REPAY",  # unified borrow-repay endpoint
        }
        if self.dry_run:
            log.info("[DRY RUN] Binance margin repay: %s", params)
            return {"repaid": repay, "asset": asset, "dry_run": True}
        result = self._request("POST", "/sapi/v1/margin/borrow-repay",
                               params=params, signed=True)
        return {"repaid": repay, "asset": asset, "tranId": result.get("tranId")}
