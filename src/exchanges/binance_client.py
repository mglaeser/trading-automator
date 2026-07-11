"""Binance spot + cross-margin adapter.

Implements the ExchangeClient interface with plain signed REST calls
(HMAC-SHA256), no heavyweight SDK required.

Endpoints used:
  GET  /api/v3/account            balances
  GET  /api/v3/ticker/price       prices (bulk)
  GET  /api/v3/exchangeInfo       symbols + lot-size filters
  POST /api/v3/order              market orders (swaps)
  GET  /sapi/v1/margin/account    outstanding margin loans
  POST /sapi/v1/margin/repay      loan repayment (was the Nexo "repay")
"""

import hashlib
import hmac
import logging
import math
import time
from urllib.parse import urlencode

import requests

from .base import Balance, ExchangeClient, ExchangeError, SwapResult, add_percentages

log = logging.getLogger(__name__)

STABLE_ALIASES = {"USDT", "USDC", "FDUSD", "TUSD", "BUSD"}


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
            raise ExchangeError(f"Binance request failed: {exc}") from exc
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
        if not step:
            return quantity
        precision = max(0, int(round(-math.log10(step))))
        return math.floor(quantity / step) * step if precision == 0 else round(
            math.floor(quantity / step) * step, precision
        )

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
            params["quantity"] = f"{qty:.8f}".rstrip("0").rstrip(".")
        else:
            params["quoteOrderQty"] = f"{quote_qty:.8f}".rstrip("0").rstrip(".")

        if self.dry_run:
            log.info("[DRY RUN] Binance order: %s", params)
            return {"dry_run": True, **params}
        return self._request("POST", "/api/v3/order", params=params, signed=True)

    def swap(self, from_asset, to_asset, amount):
        """Market-convert from_asset -> to_asset.

        Uses a direct trading pair when one exists, otherwise routes through
        the quote asset in two legs (e.g. PAXG -> USDT -> BNB).
        """
        if from_asset == to_asset:
            raise ExchangeError("swap: from and to asset are identical")

        quote_value = amount * self.get_price(from_asset)
        orders = []

        direct = self._find_symbol(from_asset, to_asset)
        reverse = self._find_symbol(to_asset, from_asset)
        if direct:  # SELL base for quote
            orders.append(self._market_order(direct, "SELL", quantity=amount))
        elif reverse:  # BUY base spending quote
            orders.append(self._market_order(reverse, "BUY", quote_qty=amount))
        else:
            # two legs through the configured quote asset
            leg1 = self._find_symbol(from_asset, self.quote_asset)
            leg2 = self._find_symbol(to_asset, self.quote_asset)
            if not leg1 or not leg2:
                raise ExchangeError(f"No trade route {from_asset} -> {to_asset}")
            orders.append(self._market_order(leg1, "SELL", quantity=amount))
            orders.append(self._market_order(leg2, "BUY", quote_qty=quote_value * 0.999))

        log.info("Swap %s %s -> %s (~%.2f %s)%s",
                 amount, from_asset, to_asset, quote_value, self.quote_asset,
                 " [DRY RUN]" if self.dry_run else "")
        return SwapResult(from_asset, to_asset, amount, quote_value,
                          self.dry_run, orders)

    # -- margin loan (replaces the Nexo loan repayment) ----------------------

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
        params = {"asset": asset, "amount": f"{repay:.8f}"}
        if self.dry_run:
            log.info("[DRY RUN] Binance margin repay: %s", params)
            return {"repaid": repay, "asset": asset, "dry_run": True}
        result = self._request("POST", "/sapi/v1/margin/repay", params=params, signed=True)
        return {"repaid": repay, "asset": asset, "tranId": result.get("tranId")}
