"""eToro adapter.

eToro exposes a REST API through its developer portal
(https://api-portal.etoro.com). Authentication uses a subscription key plus a
user key issued for your account. Unlike Binance, eToro is position-based
(you open/close positions against an instrument) rather than wallet-based,
so this adapter translates the engine's asset/swap model onto positions:

  get_balances  -> cash (credit) + aggregated open crypto positions
  swap x -> quote  -> close position(s) in x for the requested amount
  swap quote -> x  -> open a position in x
  swap x -> y      -> close x, then open y (two steps, settled in cash)

eToro has no loan facility, so the repay job becomes a no-op on this
exchange. Endpoint paths follow the public API portal; adjust ``base_url``
in the settings if eToro migrates versions.
"""

import logging
import uuid

import requests

from .base import Balance, ExchangeClient, ExchangeError, SwapResult, add_percentages

log = logging.getLogger(__name__)


class EToroClient(ExchangeClient):
    name = "etoro"

    def __init__(self, api_key, user_key, base_url="https://api.etoro.com",
                 quote_asset="USDT", dry_run=True, timeout=20):
        super().__init__(quote_asset=quote_asset, dry_run=dry_run)
        self.api_key = api_key
        self.user_key = user_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._instruments = None  # symbol -> instrument metadata

    # -- low level ---------------------------------------------------------

    def _headers(self):
        if not self.api_key:
            raise ExchangeError("eToro API key not configured")
        return {
            "Ocp-Apim-Subscription-Key": self.api_key,
            "X-USER-KEY": self.user_key,
            "X-REQUEST-ID": str(uuid.uuid4()),
            "Content-Type": "application/json",
        }

    def _request(self, method, path, params=None, json_body=None):
        try:
            resp = self._session.request(
                method,
                f"{self.base_url}{path}",
                params=params,
                json=json_body,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ExchangeError(f"eToro request failed: {exc}") from exc
        if resp.status_code >= 400:
            raise ExchangeError(f"eToro {path} -> {resp.status_code}: {resp.text[:300]}")
        if not resp.text:
            return {}
        return resp.json()

    # -- instruments ---------------------------------------------------------

    def _instrument_map(self):
        """Map ticker (e.g. 'BTC') -> instrument metadata."""
        if self._instruments is None:
            data = self._request(
                "GET", "/Metadata/V1/Instruments", params={"InstrumentTypeID": 10}
            )  # 10 = crypto
            items = data if isinstance(data, list) else data.get("InstrumentDisplayDatas", [])
            self._instruments = {}
            for item in items:
                ticker = (item.get("SymbolFull") or item.get("Ticker") or "").upper()
                if ticker:
                    self._instruments[ticker] = item
        return self._instruments

    def _instrument_id(self, asset):
        info = self._instrument_map().get(asset.upper())
        if not info:
            raise ExchangeError(f"eToro: no instrument found for '{asset}'")
        return info.get("InstrumentID") or info.get("InstrumentId")

    # -- ExchangeClient ------------------------------------------------------

    def test_connection(self):
        info = self._request("GET", "/API/User/V1/Info")
        username = info.get("Username") or info.get("username") or "account"
        return f"eToro OK (user: {username})"

    def get_price(self, asset, quote=None):
        quote = quote or self.quote_asset
        if asset == quote:
            return 1.0
        if asset in ("USDT", "USDC", "USD") and quote in ("USDT", "USDC", "USD"):
            return 1.0
        instrument_id = self._instrument_id(asset)
        data = self._request(
            "GET", "/Marketdata/V1/Rates", params={"InstrumentIDs": instrument_id}
        )
        rates = data if isinstance(data, list) else data.get("Rates", [])
        if not rates:
            raise ExchangeError(f"eToro: no rate for {asset}")
        rate = rates[0]
        bid, ask = float(rate.get("Bid", 0)), float(rate.get("Ask", 0))
        price = (bid + ask) / 2 if bid and ask else bid or ask
        if not price:
            raise ExchangeError(f"eToro: empty rate for {asset}")
        return price  # eToro rates are USD; treated 1:1 against USD-stables

    def get_balances(self, min_quote_value=0.01):
        # Cash balance
        credit = self._request("GET", "/API/User/V1/Credit")
        cash = float(credit.get("Credit", credit.get("credit", 0)) or 0)

        # Open positions, aggregated per instrument
        portfolio = self._request("GET", "/API/User/V1/Portfolio")
        positions = portfolio.get("Positions", portfolio.get("positions", []) or [])
        by_id = {v.get("InstrumentID") or v.get("InstrumentId"): k
                 for k, v in self._instrument_map().items()}

        totals = {}
        for pos in positions:
            iid = pos.get("InstrumentID") or pos.get("InstrumentId")
            asset = by_id.get(iid, f"ID{iid}")
            units = float(pos.get("Units", pos.get("units", 0)) or 0)
            totals[asset] = totals.get(asset, 0.0) + units

        balances = []
        if cash >= min_quote_value:
            balances.append(Balance(self.quote_asset, cash, cash))
        for asset, units in totals.items():
            try:
                value = units * self.get_price(asset)
            except ExchangeError:
                continue
            if value >= min_quote_value:
                balances.append(Balance(asset, units, value))
        balances.sort(key=lambda b: b.quote_value, reverse=True)
        return add_percentages(balances)

    # -- position helpers ------------------------------------------------------

    def _open_position(self, asset, quote_amount):
        payload = {
            "InstrumentID": self._instrument_id(asset),
            "IsBuy": True,
            "Leverage": 1,
            "Amount": round(quote_amount, 2),
        }
        if self.dry_run:
            log.info("[DRY RUN] eToro open position: %s", payload)
            return {"dry_run": True, **payload}
        return self._request("POST", "/API/User/V1/Positions", json_body=payload)

    def _close_positions(self, asset, units_to_close):
        """Free ~units_to_close units of ``asset`` by closing whole positions.

        eToro's API can only close entire positions, so the request is
        approximated: positions are closed smallest-first to minimise
        overshoot, and any significant overshoot is bought back immediately
        so the net position change tracks the requested amount.
        """
        portfolio = self._request("GET", "/API/User/V1/Portfolio")
        positions = portfolio.get("Positions", portfolio.get("positions", []) or [])
        target_id = self._instrument_id(asset)

        matching = []
        for pos in positions:
            iid = pos.get("InstrumentID") or pos.get("InstrumentId")
            if iid != target_id:
                continue
            units = float(pos.get("Units", pos.get("units", 0)) or 0)
            pos_id = pos.get("PositionID") or pos.get("PositionId")
            matching.append((units, pos_id))
        if not matching:
            raise ExchangeError(f"eToro: no open positions in {asset} to close")
        matching.sort()  # smallest first -> minimal overshoot

        results, closed = [], 0.0
        for units, pos_id in matching:
            if closed >= units_to_close:
                break
            if self.dry_run:
                log.info("[DRY RUN] eToro close position %s (%s units %s)",
                         pos_id, units, asset)
                results.append({"dry_run": True, "position": pos_id})
            else:
                results.append(self._request(
                    "DELETE", f"/API/User/V1/Positions/{pos_id}"
                ))
            closed += units

        # Buy back a material overshoot (whole-position granularity).
        excess = closed - units_to_close
        if excess > 0:
            excess_value = excess * self.get_price(asset)
            if excess_value >= 10.0:
                log.info("eToro: closed %.6f units over target, re-buying "
                         "%.2f %s worth of %s", excess, excess_value,
                         self.quote_asset, asset)
                results.append(self._open_position(asset, excess_value))
        return results

    def swap(self, from_asset, to_asset, amount):
        quote_value = amount * self.get_price(from_asset)
        orders = []
        if from_asset == self.quote_asset:
            orders.append(self._open_position(to_asset, amount))
        elif to_asset == self.quote_asset:
            orders.extend(self._close_positions(from_asset, amount))
        else:
            orders.extend(self._close_positions(from_asset, amount))
            orders.append(self._open_position(to_asset, quote_value))

        log.info("Swap %s %s -> %s (~%.2f %s)%s",
                 amount, from_asset, to_asset, quote_value, self.quote_asset,
                 " [DRY RUN]" if self.dry_run else "")
        return SwapResult(from_asset, to_asset, amount, quote_value,
                          self.dry_run, orders)
