"""Trading engine: all portfolio handlers plus orchestration.

Each scheduled cycle the engine reads balances, keeps the anchor asset at
its target share, splits fresh quote-asset inflows, repays outstanding
margin loans, and rebalances the portfolio from a TradingView + LLM
pipeline. A dust sweep is available on demand.

Safety invariants:
  - Only assets in the configured universe are ever bought or sold; an
    airdropped or unknown asset on the account is never touched.
  - The market rebalance opens no sentiment trades when technical analysis
    is missing for any buyable asset, when every pairwise LLM evaluation
    failed, or when the market evaluation itself failed. Independent
    housekeeping (inflow split, anchor maintenance) runs before the market
    analysis and is unaffected by that abort.
  - Every trade passes _swap, which enforces a blast-radius cap: a swap above
    max_swap_value is clamped down; a swap that would breach the rolling 24h
    daily_trade_cap is refused and auto-halts the engine (persisted).
  - Buys are always funded: sells execute first and buys are clamped to
    the actually available quote balance.
  - A degenerate "bullish but nothing scored positive" signal keeps the
    current allocation instead of liquidating everything.
  - Jobs never queue up: whatever job is running, a second trigger is
    skipped with a log line instead of piling onto a lock.
"""

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .analysis import evaluate_crypto_analysis, get_buyable_cryptos, get_crypto_analysis
from .exchanges import ExchangeError, create_client
from .exchanges.base import Balance, ExchangeClient, SwapResult
from .llm import LLMClient
from .notifications import send_sms_alert
from .scheduler import Scheduler
from .state import EngineState

if TYPE_CHECKING:
    from .settings import Settings

log = logging.getLogger(__name__)


def round_down(number: float, decimals: int = 2) -> float:
    factor = 10 ** decimals
    return int(number * factor) / factor


def asset_distribution_from_recommendation(
    recommendations: list[dict[str, Any]], allocated_percentage: float = 0.0
) -> list[tuple[str, float]]:
    """Convert pairwise LLM recommendations into portfolio weights.

    Scoring: sell_buy shifts one point of confidence from the first to the
    second asset; buy/sell add/subtract for both; hold is neutral. Negative
    scores clamp to zero and the rest is normalised into
    (1 - allocated_percentage). May legitimately return all-zero weights
    (all hold / net negative) -- callers must handle that.
    """
    if not 0 <= allocated_percentage < 1:
        raise ValueError("allocated_percentage must be between 0 and 1")

    scores: dict[str, float] = {}
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
    def __init__(self, settings: "Settings", state: EngineState | None = None) -> None:
        self.settings = settings
        self.state = state or EngineState()
        self.llm = LLMClient(settings)
        self.scheduler = Scheduler(settings)
        self.scheduler.add_job("refresh", lambda: self.refresh(scheduled=True))
        self.scheduler.add_job("rebalance", lambda: self.rebalance(scheduled=True))
        self.scheduler.add_job("repay", lambda: self.repay(scheduled=True))
        self._job_lock = threading.Lock()        # one job at a time, no queueing
        self._lifecycle_lock = threading.Lock()  # serialises start()/stop()
        # Quote balance at the end of the previous rebalance cycle; baseline
        # for inflow detection. None until the first cycle completes, so the
        # engine's own cash reserve can never be mistaken for a deposit.
        self._last_cycle_quote: float | None = None
        # Rolling record of (timestamp, executed quote value) for the trading cap.
        self._trade_window: deque[tuple[float, float]] = deque()

    # -- helpers ---------------------------------------------------------------

    @property
    def dry_run(self) -> bool:
        return bool(self.settings.get("dry_run", True))

    def _client(self) -> ExchangeClient:
        return create_client(self.settings, dry_run=self.dry_run)

    def _trading(self, key: str, default: Any = None) -> Any:
        return self.settings.get(f"trading.{key}", default)

    def _run_job(self, name: str, fn: Callable[[], Any], scheduled: bool = False) -> None:
        """Run one job; concurrent triggers are skipped, never queued."""
        if scheduled and not self.state.engine_running:
            log.info("Scheduled job '%s' skipped: engine stopped", name)
            return
        if not self._job_lock.acquire(blocking=False):
            self.state.log(
                f"{name} skipped: '{self.state.current_job}' is still running",
                level="warning",
            )
            return
        try:
            self.state.set(current_job=name)
            fn()
            self.state.set(current_job=None, last_error=None)
        except Exception as exc:
            log.exception("Job '%s' failed", name)
            self.state.set(current_job=None, last_error=f"{name}: {exc}")
            self.state.log(f"{name} failed: {exc}", level="error")
            if name == "rebalance":
                send_sms_alert(self.settings,
                               f"Trading automator: {name} failed: {exc}")
        finally:
            self._job_lock.release()

    def _traded_last_24h(self) -> float:
        cutoff = time.time() - 24 * 3600
        while self._trade_window and self._trade_window[0][0] < cutoff:
            self._trade_window.popleft()
        return sum(v for _, v in self._trade_window)

    def _halt(self, reason: str) -> None:
        """Trip the kill switch automatically: stop trading now, persist the
        stop so a restart does not resurrect the engine, and shut the scheduler
        down off-thread (a scheduled job runs on the scheduler thread, so it
        must not join itself)."""
        with self._lifecycle_lock:
            already_stopped = not self.state.engine_running
            self.state.set(engine_running=False)
            self.settings.update({"runtime": {"engine_enabled": False}})
        if already_stopped:
            return
        self.state.log(f"AUTO-HALT: {reason}. Engine stopped; press Start to resume.",
                       level="error")
        send_sms_alert(self.settings, f"Trading automator AUTO-HALT: {reason}")
        threading.Thread(target=self.scheduler.stop, daemon=True,
                         name="auto-halt").start()

    def _swap(
        self, client: ExchangeClient, from_asset: str, to_asset: str, amount: float
    ) -> SwapResult:
        # Blast-radius cap at the single trade chokepoint (A-11/A-34/A-35/B-08).
        max_swap = float(self._trading("max_swap_value", 0.0) or 0.0)
        daily_cap = float(self._trading("daily_trade_cap", 0.0) or 0.0)
        quote = self._trading("quote_asset", "USDT")
        if max_swap > 0 or daily_cap > 0:
            est_value = amount * client.get_price(from_asset)
            if max_swap > 0 and est_value > max_swap:
                amount *= max_swap / est_value           # clamp down, never up
                est_value = max_swap
                self.state.log(
                    f"Swap clamped to the per-swap ceiling of {max_swap:.2f} {quote}",
                    level="warning",
                )
            if daily_cap > 0 and self._traded_last_24h() + est_value > daily_cap:
                self._halt(
                    f"daily trade cap of {daily_cap:.2f} {quote} would be exceeded "
                    f"(already {self._traded_last_24h():.2f} in 24h)"
                )
                raise ExchangeError("daily trade cap reached; engine halted")

        result = client.swap(from_asset, to_asset, amount)
        self._trade_window.append((time.time(), result.quote_value))
        self.state.record_swap(result)
        self.state.log(
            f"Swap {result.amount:.6f} {from_asset} -> {to_asset} "
            f"(~{result.quote_value:.2f} {client.quote_asset})"
            + (" [dry run]" if result.dry_run else ""),
            level="trade",
        )
        return result

    @staticmethod
    def _balance_map(balances: list[Balance]) -> dict[str, Balance]:
        return {b.asset: b for b in balances}

    # -- jobs (public entry points; also used by the web UI) ---------------------

    def refresh(self, scheduled: bool = False) -> None:
        self._run_job("refresh", self._refresh, scheduled=scheduled)

    def rebalance(self, scheduled: bool = False) -> None:
        self._run_job("rebalance", self._rebalance, scheduled=scheduled)

    def repay(self, scheduled: bool = False) -> None:
        self._run_job("repay", self._repay, scheduled=scheduled)

    def sweep_small_balances(self) -> None:
        self._run_job("sweep", self._sweep)

    # -- refresh -----------------------------------------------------------------

    def _refresh(self) -> list[Balance]:
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

    # -- anchor asset target ---------------------------------------------------------

    def maintain_anchor_target(
        self, client: ExchangeClient | None = None, balances: list[Balance] | None = None
    ) -> bool:
        """Keep the anchor asset at its target portfolio share.

        The per-cycle adjustment is clamped to [anchor_swap_min,
        anchor_swap_max]: below the minimum nothing happens (avoids fee
        churn), above the maximum the swap is capped so large deviations
        converge over several cycles instead of moving big amounts at once.
        """
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
        total = sum(b.quote_value for b in balances)
        if total <= 0:
            return False
        anchor_bal = by_asset.get(anchor)
        quote_bal = by_asset.get(quote)
        current = anchor_bal.percentage if anchor_bal else 0.0

        # True deviation in quote terms, from the whole portfolio value.
        diff_quote = total * (target - current) / 100.0

        if diff_quote < 0 and anchor_bal:        # sell surplus anchor
            amount_quote = -diff_quote
        elif diff_quote > 0:                     # buy anchor with quote
            available = quote_bal.quote_value if quote_bal else 0.0
            amount_quote = min(diff_quote, available)
        else:
            return False

        amount_quote = round_down(amount_quote)
        self.state.log(
            f"Anchor {anchor}: {current:.2f}% (target {target:.2f}%), "
            f"adjustment {amount_quote:.2f} {quote}"
        )
        if amount_quote <= swap_min:
            self.state.log("Anchor swap below minimum, skipped")
            return False
        if amount_quote > swap_max:
            self.state.log(
                f"Anchor swap capped at {swap_max:.2f} (converging incrementally)"
            )
            amount_quote = swap_max

        if diff_quote < 0:
            assert anchor_bal is not None  # diff_quote<0 reaches here only with a position
            native = anchor_bal.amount * (amount_quote / anchor_bal.quote_value)
            self._swap(client, anchor, quote, native)
        else:
            self._swap(client, quote, anchor, amount_quote)
        return True

    # -- fiat inflow split -----------------------------------------------------------

    def handle_inflow_split(
        self, client: ExchangeClient | None = None, balances: list[Balance] | None = None
    ) -> bool:
        """Buy a slice of the anchor asset from a fresh quote-asset deposit.

        Only the *increase* of the quote balance since the end of the last
        rebalance cycle counts as an inflow -- the engine's own cash reserve
        or liquidation proceeds (quote cash is also the working reserve) can
        never trigger this.
        """
        client = client or self._client()
        balances = balances if balances is not None else client.get_balances()
        quote = self._trading("quote_asset", "USDT")
        low = float(self._trading("inflow_min", 300.0))
        high = float(self._trading("inflow_max", 750.0))
        ratio = float(self._trading("inflow_anchor_ratio", 0.103))
        anchor = self._trading("anchor_asset")

        quote_bal = self._balance_map(balances).get(quote)
        if not quote_bal or self._last_cycle_quote is None:
            return False  # no baseline yet: never misfire on first cycle

        inflow = quote_bal.quote_value - self._last_cycle_quote
        if not (low < inflow < high):
            return False

        anchor_amount = round_down(inflow * ratio)
        self.state.log(
            f"Inflow detected: +{inflow:.2f} {quote} since last cycle, "
            f"buying {anchor_amount:.2f} {quote} of {anchor}"
        )
        if anchor and anchor_amount > 1:
            self._swap(client, quote, anchor, anchor_amount)
            return True
        return False

    # -- loan repayment (Binance margin) ---------------------------------------------

    def _repay(self) -> None:
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

    # -- LLM-driven rebalancing ------------------------------------------------------

    def _sentiment_interval(self, sentiment: str) -> list[int]:
        window = self.settings.get(f"schedule.sentiment_rebalance.{sentiment}")
        defaults = {"bullish": [8, 13], "bearish": [45, 75], "neutral": [30, 45]}
        return window if isinstance(window, list) and len(window) == 2 \
            else defaults[sentiment]

    def _rebalance(self) -> None:
        assets = self._trading("assets", {})
        interval = self._trading("analysis_interval", "30m")
        quote = self._trading("quote_asset", "USDT")
        reserve = float(self._trading("reserve_percent", 0.70))
        use_cache = self.dry_run
        cache_max_age = int(self._trading("cache_max_age", 1800))

        client = self._client()
        balances = client.get_balances()

        # Housekeeping handlers run before the market analysis; each swap
        # invalidates the snapshot, so re-read when one actually traded.
        if self.handle_inflow_split(client, balances):
            balances = client.get_balances()
        if self.maintain_anchor_target(client, balances):
            balances = client.get_balances()

        self.state.log("Fetching TradingView analysis "
                       f"for {', '.join(assets)} ({interval})")
        analytics = get_crypto_analysis(assets, interval=interval,
                                        use_cache=use_cache,
                                        cache_max_age=cache_max_age)
        buyable = get_buyable_cryptos(assets)
        missing = [t for t in buyable if t not in analytics]
        if missing:
            raise RuntimeError(
                f"Technical analysis missing for {', '.join(missing)}; "
                "refusing to trade on partial data"
            )

        recommendations, summaries = evaluate_crypto_analysis(
            analytics, assets, self.llm,
            use_cache=use_cache, cache_max_age=cache_max_age,
        )
        if recommendations and not any("error" not in r for r in recommendations):
            raise RuntimeError(
                f"All {len(recommendations)} pairwise LLM evaluations failed; "
                "refusing to trade without signals"
            )

        evaluation = self.llm.market_evaluation(
            summaries, buyable, use_cache=use_cache, cache_max_age=cache_max_age
        )
        if "error" in evaluation:
            raise RuntimeError(f"Market evaluation failed: {evaluation['error']}")

        self.state.set(
            recommendations=recommendations,
            market_evaluation={**evaluation, "ts": time.time()},
        )
        sentiment = evaluation["recommendation"]  # validated by LLMClient
        self.state.log(f"Market sentiment: {sentiment} -- {evaluation.get('reason')}")
        self.scheduler.set_override("rebalance", self._sentiment_interval(sentiment))

        if sentiment == "bearish":
            self.state.log("Bearish market: selling all crypto, slowing schedule")
            self.sell_all_crypto(client, balances)
            self.state.set(target_distribution=[(quote, 1.0)])

        elif sentiment == "bullish":
            distribution = asset_distribution_from_recommendation(
                recommendations, reserve
            )
            if not any(pct > 0 for _, pct in distribution):
                # All-hold / all-negative scores: doing "something" here would
                # mean liquidating the whole portfolio on a bullish signal.
                self.state.log(
                    "Bullish sentiment but no asset scored positive; "
                    "keeping the current allocation", level="warning",
                )
            else:
                self.state.log("Bullish market: rebalancing to LLM weights")
                distribution.append((quote, reserve))
                self.state.set(target_distribution=distribution)
                self.swap_to_target(client, balances, distribution)

        else:  # neutral
            anchor = self._trading("anchor_asset")
            self.state.log(f"Neutral market: mostly {quote}, some {anchor}")
            distribution = [(quote, 0.9), (anchor, 0.1)] if anchor else [(quote, 1.0)]
            self.state.set(target_distribution=distribution)
            self.swap_to_target(client, balances, distribution)

        self.state.set(last_rebalance=time.time())

        # Record the post-cycle quote balance as the inflow baseline: the
        # engine's own trades can never look like a deposit.
        final_balances = self._refresh()
        final_quote = self._balance_map(final_balances).get(quote)
        self._last_cycle_quote = final_quote.quote_value if final_quote else 0.0

    # -- rebalance to target weights -------------------------------------------------

    def swap_to_target(
        self,
        client: ExchangeClient,
        balances: list[Balance],
        target_distribution: list[tuple[str, float]],
    ) -> bool:
        """Move the portfolio towards the target weights.

        Sells run first and their (fee-discounted) proceeds fund the buys;
        buys are clamped to the tracked available quote balance so a partial
        failure can never overdraw. Only configured assets are touched.
        """
        quote = self._trading("quote_asset", "USDT")
        assets = self._trading("assets", {})
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

        adjustments: dict[str, float] = {}
        for asset, target_pct in targets.items():
            current_value = by_asset[asset].quote_value if asset in by_asset else 0.0
            current_pct = current_value / total
            diff_value = total * target_pct - current_value
            if (abs(current_pct - target_pct) > delta_threshold
                    or (target_pct == 0 and current_value > min_trade)):
                adjustments[asset] = diff_value
        # configured assets held but absent from the target get sold completely
        for asset, bal in by_asset.items():
            if (asset not in targets and asset != quote and asset in assets
                    and bal.quote_value > min_trade):
                adjustments[asset] = -bal.quote_value

        quote_bal = by_asset.get(quote)
        available = quote_bal.quote_value if quote_bal else 0.0
        swapped = False
        # sells first so the quote balance is funded for the buys
        for asset, diff in sorted(adjustments.items(), key=lambda kv: kv[1]):
            if asset == quote or abs(diff) < min_trade:
                continue
            if diff < 0:
                bal = by_asset[asset]
                native = bal.amount * min(1.0, -diff / bal.quote_value)
                self._swap(client, asset, quote, native)
                available += -diff * 0.999  # proceeds minus fee haircut
            else:
                spend = min(diff, round_down(available))
                if spend < min_trade:
                    self.state.log(
                        f"Buy of {asset} skipped: only {available:.2f} {quote} "
                        "available", level="warning",
                    )
                    continue
                self._swap(client, quote, asset, spend)
                available -= spend
            swapped = True

        self.state.log("Rebalance " + ("executed" if swapped else
                                       "not needed (all targets within threshold)"))
        return swapped

    # -- bearish liquidation ---------------------------------------------------------

    def sell_all_crypto(
        self, client: ExchangeClient | None = None, balances: list[Balance] | None = None
    ) -> bool:
        """Liquidate all *configured* crypto assets into the quote asset.

        Assets not in the configured universe (airdrops, staking rewards,
        manually held positions) are deliberately left untouched.
        """
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
            if spec is None or not spec.get("crypto", True):
                continue  # unconfigured assets and stables stay
            if bal.quote_value <= min_trade:
                continue
            self._swap(client, bal.asset, quote, bal.amount)
            swapped = True
        if not swapped:
            self.state.log("No crypto positions to liquidate")
        return swapped

    # -- dust sweep ------------------------------------------------------------------

    def _sweep(self) -> None:
        client = self._client()
        quote = self._trading("quote_asset", "USDT")
        assets = self._trading("assets", {})
        threshold = float(self._trading("dust_threshold", 10.0))
        swapped = failed = 0
        for bal in client.get_balances():
            if bal.asset == quote or bal.asset not in assets:
                continue
            if 1.0 < bal.quote_value < threshold:
                try:
                    self._swap(client, bal.asset, quote, bal.amount)
                    swapped += 1
                except ExchangeError as exc:
                    # e.g. below the pair's minimum notional -- skip, not abort
                    failed += 1
                    self.state.log(f"Dust sweep of {bal.asset} skipped: {exc}",
                                   level="warning")
        if not swapped and not failed:
            self.state.log("No small balances to sweep")

    # -- lifecycle -----------------------------------------------------------------------

    def start(self) -> None:
        with self._lifecycle_lock:
            if self.state.engine_running:
                return
            self.state.set(engine_running=True)
            # Persist the decision so an explicit stop survives restarts.
            self.settings.update({"runtime": {"engine_enabled": True}})
            self.state.log(
                "Engine started"
                + (" in DRY RUN mode (no orders will be sent)" if self.dry_run else "")
            )
            self.scheduler.start()
        # initial pass in the background so the API call returns immediately
        threading.Thread(target=self._initial_pass, daemon=True,
                         name="initial-pass").start()

    def _initial_pass(self) -> None:
        # errors are logged and surfaced by _run_job
        self.refresh(scheduled=True)
        self.rebalance(scheduled=True)

    def stop(self) -> None:
        with self._lifecycle_lock:
            if not self.state.engine_running:
                return
            self.state.set(engine_running=False)  # stops queued scheduled jobs
            self.settings.update({"runtime": {"engine_enabled": False}})
            self.scheduler.stop()
            self.state.log("Engine stopped")
