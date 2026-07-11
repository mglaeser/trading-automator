"""Trading engine: all portfolio handlers plus orchestration.

Ports every behaviour of the old Selenium implementation onto the exchange
API layer:

  old (Nexo/Selenium)             ->  new (Binance / eToro API)
  ------------------------------------------------------------------
  refresh / extract balances      ->  refresh()
  handle_nexo_loyalty (10.3%)     ->  maintain_anchor_target()
  handle_euro_balance             ->  handle_inflow_split()
  handle_repay_loan               ->  repay() (Binance margin)
  handle_wallet_distribution      ->  rebalance() (TA + LLM pipeline)
  handle_swap_to_percent          ->  swap_to_target()
  handle_sell_all_crypto          ->  sell_all_crypto()
  handle_small_balances           ->  sweep_small_balances()
"""

import logging
import threading
import time

from .analysis import evaluate_crypto_analysis, get_buyable_cryptos, get_crypto_analysis
from .exchanges import ExchangeError, create_client
from .llm import LLMClient
from .notifications import send_sms_alert
from .scheduler import Scheduler
from .state import EngineState

log = logging.getLogger(__name__)


def round_down(number, decimals=2):
    factor = 10 ** decimals
    return int(number * factor) / factor


def asset_distribution_from_recommendation(recommendations, allocated_percentage=0.0):
    """Convert pairwise LLM recommendations into portfolio weights.

    Identical scoring to the old implementation: sell_buy shifts one point of
    confidence from the first to the second asset; buy/sell add/subtract for
    both; hold is neutral. Negative scores clamp to zero and the rest is
    normalised into (1 - allocated_percentage).
    """
    if not 0 <= allocated_percentage < 1:
        raise ValueError("allocated_percentage must be between 0 and 1")

    scores = {}
    for rec in recommendations:
        if "error" in rec:
            continue
        action, assets, confidence = rec["action"], rec["assets"], rec["confidence"]
        if action == "sell_buy":
            scores[assets[0]] = scores.get(assets[0], 0) - confidence
            scores[assets[1]] = scores.get(assets[1], 0) + confidence
        elif action == "sell":
            for asset in assets:
                scores[asset] = scores.get(asset, 0) - confidence
        elif action == "buy":
            for asset in assets:
                scores[asset] = scores.get(asset, 0) + confidence
        else:  # hold
            for asset in assets:
                scores.setdefault(asset, 0)

    scores = {k: max(0.0, v) for k, v in scores.items()}
    total = sum(scores.values())
    if total <= 0:
        return [(asset, 0.0) for asset in scores]
    budget = 1.0 - allocated_percentage
    return [(asset, round(score / total * budget, 4))
            for asset, score in scores.items()]


class TradingEngine:
    def __init__(self, settings, state=None):
        self.settings = settings
        self.state = state or EngineState()
        self.llm = LLMClient(settings)
        self.scheduler = Scheduler(settings)
        self.scheduler.add_job("refresh", self.refresh)
        self.scheduler.add_job("rebalance", self.rebalance)
        self.scheduler.add_job("repay", self.repay)
        self._job_lock = threading.Lock()

    # -- helpers ---------------------------------------------------------------

    @property
    def dry_run(self):
        return self.settings.get("dry_run", True)

    def _client(self):
        return create_client(self.settings, dry_run=self.dry_run)

    def _trading(self, key, default=None):
        return self.settings.get(f"trading.{key}", default)

    def _run_job(self, name, fn):
        """Serialise jobs and surface errors to the UI + SMS."""
        with self._job_lock:
            self.state.set(current_job=name)
            try:
                fn()
                self.state.set(current_job=None, last_error=None)
            except Exception as exc:
                log.exception("Job '%s' failed", name)
                self.state.set(current_job=None, last_error=f"{name}: {exc}")
                self.state.log(f"{name} failed: {exc}", level="error")
                if name == "rebalance":
                    send_sms_alert(self.settings,
                                   f"Trading automator: {name} failed: {exc}")
                raise

    def _swap(self, client, from_asset, to_asset, amount):
        result = client.swap(from_asset, to_asset, amount)
        self.state.record_swap(result)
        self.state.log(
            f"Swap {result.amount:.6f} {from_asset} -> {to_asset} "
            f"(~{result.quote_value:.2f} {client.quote_asset})"
            + (" [dry run]" if result.dry_run else ""),
            level="trade",
        )
        return result

    @staticmethod
    def _balance_map(balances):
        return {b.asset: b for b in balances}

    # -- jobs (scheduled entry points) ------------------------------------------

    def refresh(self):
        self._run_job("refresh", self._refresh)

    def rebalance(self):
        self._run_job("rebalance", self._rebalance)

    def repay(self):
        self._run_job("repay", self._repay)

    # -- refresh -----------------------------------------------------------------

    def _refresh(self):
        client = self._client()
        balances = client.get_balances()
        loan = client.get_loan_balance()
        self.state.set(
            balances=[b.to_dict() for b in balances],
            total_value=sum(b.quote_value for b in balances),
            loan_balance=loan,
            last_refresh=time.time(),
        )
        self.state.log(
            f"Balances refreshed: {len(balances)} assets, "
            f"total {sum(b.quote_value for b in balances):.2f} {client.quote_asset}"
        )
        return balances

    # -- anchor asset target (was NEXO loyalty level) ------------------------------

    def maintain_anchor_target(self, client=None, balances=None):
        client = client or self._client()
        balances = balances if balances is not None else client.get_balances()
        anchor = self._trading("anchor_asset")
        target = float(self._trading("anchor_target_percent", 10.3))
        swap_min = float(self._trading("anchor_swap_min", 2.5))
        swap_max = float(self._trading("anchor_swap_max", 15.0))
        quote = self._trading("quote_asset", "USDT")
        if not anchor or anchor == quote:
            return False

        by_asset = self._balance_map(balances)
        anchor_bal = by_asset.get(anchor)
        quote_bal = by_asset.get(quote)
        current = anchor_bal.percentage if anchor_bal else 0.0

        if current > target:
            # sell down the surplus
            surplus_native = anchor_bal.amount / current * (current - target)
            amount_quote = surplus_native / anchor_bal.amount * anchor_bal.quote_value
            direction = (anchor, quote, surplus_native)
        else:
            deficit_quote = 0.0
            if quote_bal:
                non_anchor = 100.0 - current
                deficit_quote = quote_bal.quote_value / non_anchor * (target - current)
            amount_quote = deficit_quote
            direction = (quote, anchor, deficit_quote)

        amount_quote = round_down(abs(amount_quote))
        self.state.log(
            f"Anchor {anchor}: {current:.2f}% (target {target:.2f}%), "
            f"adjustment {amount_quote:.2f} {quote}"
        )
        if amount_quote > swap_max:
            self.state.log(f"Anchor swap too large ({amount_quote:.2f}), skipped",
                           level="warning")
            return False
        if amount_quote <= swap_min:
            self.state.log("Anchor swap below minimum, skipped")
            return False

        from_asset, to_asset, amount = direction
        self._swap(client, from_asset, to_asset, amount)
        return True

    # -- fiat inflow split (was handle_euro_balance) ---------------------------------

    def handle_inflow_split(self, client=None, balances=None):
        client = client or self._client()
        balances = balances if balances is not None else client.get_balances()
        quote = self._trading("quote_asset", "USDT")
        low = float(self._trading("inflow_min", 300.0))
        high = float(self._trading("inflow_max", 750.0))
        ratio = float(self._trading("inflow_anchor_ratio", 0.103))
        anchor = self._trading("anchor_asset")

        quote_bal = self._balance_map(balances).get(quote)
        if not quote_bal or not (low < quote_bal.quote_value < high):
            return False

        anchor_amount = round_down(quote_bal.quote_value * ratio)
        self.state.log(
            f"Inflow split: {quote_bal.quote_value:.2f} {quote} in window "
            f"[{low}, {high}], buying {anchor_amount:.2f} {quote} of {anchor}"
        )
        if anchor and anchor_amount > 1:
            self._swap(client, quote, anchor, anchor_amount)
            return True
        return False

    # -- loan repayment (was Nexo repay; Binance margin) ------------------------------

    def _repay(self):
        client = self._client()
        loan = client.get_loan_balance()
        self.state.set(loan_balance=loan)
        if loan <= 0:
            self.state.log("No outstanding loan")
            return

        repay_asset = self._trading("quote_asset", "USDT")
        self.state.log(f"Repaying loan of {loan:.2f} with {repay_asset}")
        try:
            result = client.repay_loan(repay_asset)
        except ExchangeError as exc:
            self.state.log(f"Loan repayment unavailable: {exc}", level="warning")
            return

        remaining = client.get_loan_balance()
        self.state.set(loan_balance=remaining)
        if result.get("repaid", 0) > 0:
            self.state.log(
                f"Repaid {result['repaid']:.2f} {repay_asset}, "
                f"remaining loan {remaining:.2f}", level="trade",
            )
            send_sms_alert(
                self.settings,
                f"Trading automator: loan repayment of {result['repaid']:.2f} "
                f"{repay_asset} executed, remaining {remaining:.2f}",
            )

    # -- LLM-driven rebalancing (was handle_wallet_distribution) -----------------------

    def _rebalance(self):
        assets = self._trading("assets", {})
        interval = self._trading("analysis_interval", "30m")
        quote = self._trading("quote_asset", "USDT")
        reserve = float(self._trading("reserve_percent", 0.70))
        use_cache = self.dry_run

        client = self._client()
        balances = client.get_balances()

        # Housekeeping handlers run before the market analysis
        self.handle_inflow_split(client, balances)
        self.maintain_anchor_target(client, balances)

        self.state.log("Fetching TradingView analysis "
                       f"for {', '.join(assets)} ({interval})")
        analytics = get_crypto_analysis(assets, interval=interval, use_cache=use_cache)
        if not analytics:
            raise RuntimeError("No technical analysis available")

        recommendations, summaries = evaluate_crypto_analysis(
            analytics, assets, self.llm
        )
        evaluation = self.llm.market_evaluation(
            summaries, get_buyable_cryptos(assets), use_cache=use_cache
        )
        if "error" in evaluation:
            raise RuntimeError(f"Market evaluation failed: {evaluation['error']}")

        self.state.set(
            recommendations=recommendations,
            market_evaluation={**evaluation, "ts": time.time()},
        )
        sentiment = evaluation["recommendation"]
        self.state.log(f"Market sentiment: {sentiment} -- {evaluation.get('reason')}")

        balances = client.get_balances()  # re-read after housekeeping swaps

        if sentiment == "bearish":
            self.state.log("Bearish market: selling all crypto, slowing schedule")
            self.sell_all_crypto(client, balances)
            self.scheduler.update_interval("rebalance", [45, 75])
            self.state.set(target_distribution=[(quote, 1.0)])

        elif sentiment == "bullish":
            self.state.log("Bullish market: rebalancing, tightening schedule")
            self.scheduler.update_interval("rebalance", [8, 13])
            distribution = asset_distribution_from_recommendation(
                recommendations, reserve
            )
            distribution.append((quote, reserve))
            self.state.set(target_distribution=distribution)
            self.swap_to_target(client, balances, distribution)

        else:  # neutral
            anchor = self._trading("anchor_asset")
            self.state.log(f"Neutral market: mostly {quote}, some {anchor}")
            self.scheduler.update_interval("rebalance", [30, 45])
            distribution = [(quote, 0.9), (anchor, 0.1)] if anchor else [(quote, 1.0)]
            self.state.set(target_distribution=distribution)
            self.swap_to_target(client, balances, distribution)

        self.state.set(last_rebalance=time.time())
        self._refresh()

    # -- rebalance to target weights (was handle_swap_to_percent) ----------------------

    def swap_to_target(self, client, balances, target_distribution):
        quote = self._trading("quote_asset", "USDT")
        delta_threshold = float(self._trading("rebalance_delta", 0.05))
        min_trade = float(self._trading("min_trade_value", 10.0))

        by_asset = self._balance_map(balances)
        total = sum(b.quote_value for b in balances)
        if total <= 0:
            self.state.log("Portfolio empty, nothing to rebalance", level="warning")
            return False

        targets = dict(target_distribution)
        target_sum = sum(targets.values())
        if abs(target_sum - 1.0) > 0.01:
            self.state.log(
                f"Target percentages sum to {target_sum:.2%}, normalising",
                level="warning",
            )
            targets = {a: p / target_sum for a, p in targets.items()}

        adjustments = {}
        for asset, target_pct in targets.items():
            current_value = by_asset[asset].quote_value if asset in by_asset else 0.0
            current_pct = current_value / total
            diff_value = total * target_pct - current_value
            if (abs(current_pct - target_pct) > delta_threshold
                    or (target_pct == 0 and current_value > min_trade)):
                adjustments[asset] = diff_value
        # assets held but absent from the target get sold completely
        for asset, bal in by_asset.items():
            if asset not in targets and asset != quote and bal.quote_value > min_trade:
                adjustments[asset] = -bal.quote_value

        swapped = False
        # sells first so the quote balance is funded for the buys
        for asset, diff in sorted(adjustments.items(), key=lambda kv: kv[1]):
            if asset == quote or abs(diff) < min_trade:
                continue
            if diff < 0:
                bal = by_asset[asset]
                native = bal.amount * min(1.0, -diff / bal.quote_value)
                self._swap(client, asset, quote, native)
            else:
                self._swap(client, quote, asset, diff)
            swapped = True

        self.state.log("Rebalance " + ("executed" if swapped else
                                       "not needed (all targets within threshold)"))
        return swapped

    # -- bearish liquidation (was handle_sell_all_crypto) --------------------------------

    def sell_all_crypto(self, client=None, balances=None):
        client = client or self._client()
        balances = balances if balances is not None else client.get_balances()
        quote = self._trading("quote_asset", "USDT")
        assets = self._trading("assets", {})
        min_trade = float(self._trading("min_trade_value", 10.0))

        swapped = False
        for bal in balances:
            if bal.asset == quote:
                continue
            spec = assets.get(bal.asset)
            if spec is not None and not spec.get("crypto", True):
                continue  # stables/fiat proxies stay
            if bal.quote_value <= min_trade:
                continue
            self._swap(client, bal.asset, quote, bal.amount)
            swapped = True
        if not swapped:
            self.state.log("No crypto positions to liquidate")
        return swapped

    # -- dust sweep (was handle_small_balances) --------------------------------------------

    def sweep_small_balances(self):
        def _sweep():
            client = self._client()
            quote = self._trading("quote_asset", "USDT")
            threshold = float(self._trading("dust_threshold", 10.0))
            swapped = False
            for bal in client.get_balances():
                if bal.asset == quote:
                    continue
                if 1.0 < bal.quote_value < threshold:
                    self._swap(client, bal.asset, quote, bal.amount)
                    swapped = True
            if not swapped:
                self.state.log("No small balances to sweep")

        self._run_job("sweep", _sweep)

    # -- lifecycle -----------------------------------------------------------------------

    def start(self):
        if self.state.engine_running:
            return
        self.state.set(engine_running=True)
        self.state.log(
            "Engine started"
            + (" in DRY RUN mode (no orders will be sent)" if self.dry_run else "")
        )
        self.scheduler.start()
        # initial pass in the background so the API call returns immediately
        threading.Thread(target=self._initial_pass, daemon=True).start()

    def _initial_pass(self):
        try:
            self.refresh()
            self.rebalance()
        except Exception:
            pass  # already logged/surfaced by _run_job

    def stop(self):
        self.scheduler.stop()
        self.state.set(engine_running=False)
        self.state.log("Engine stopped")
