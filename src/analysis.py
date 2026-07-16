"""Technical analysis via TradingView.

Fetches indicators for every configured asset, derives refined metrics
(momentum, volatility, trend strength, Fibonacci levels) and a simple
rule-based recommendation that feeds the LLM evaluation.
"""

import logging

from tradingview_ta import TA_Handler

from .cache import cached_response

log = logging.getLogger(__name__)


def calculate_fibonacci_levels(high, low):
    diff = high - low
    return {
        "0": low,
        "0.236": low + 0.236 * diff,
        "0.382": low + 0.382 * diff,
        "0.5": low + 0.5 * diff,
        "0.618": low + 0.618 * diff,
        "0.786": low + 0.786 * diff,
        "1": high,
    }


def get_recommendation(analysis):
    rsi = analysis["RSI"]
    macd_hist = analysis["MACD"]["Histogram"]
    stoch_k = analysis["Stochastic"]["K"]
    trend_strength = analysis["Trend_Strength"]

    if rsi > 70 and macd_hist < 0 and stoch_k > 80:
        return "Strong Sell"
    if rsi < 30 and macd_hist > 0 and stoch_k < 20:
        return "Strong Buy"
    if trend_strength > 0:
        return "Buy"
    if trend_strength < 0:
        return "Sell"
    return "Neutral"


def _refine(indicators, symbol, screener_exchange, interval):
    rsi = indicators["RSI"]
    macd = indicators["MACD.macd"]
    macd_signal = indicators["MACD.signal"]
    bb_upper = indicators["BB.upper"]
    bb_lower = indicators["BB.lower"]
    stoch_k = indicators["Stoch.K"]
    stoch_d = indicators["Stoch.D"]
    close = indicators["close"]
    obv = indicators.get("OBV")

    macd_diff = macd - macd_signal
    sign = 1 if macd_diff > 0 else -1 if macd_diff < 0 else 0

    refined = {
        "RSI": rsi,
        "MACD": {"MACD": macd, "Signal": macd_signal, "Histogram": macd_diff},
        "Bollinger_Bands": {
            "Upper": bb_upper,
            "Lower": bb_lower,
            "Volatility_Index": (bb_upper - bb_lower) / close if close else 0.0,
        },
        "Stochastic": {"K": stoch_k, "D": stoch_d},
        "OBV": obv,
        "Combined_Momentum": (rsi + stoch_k) / 2,
        "Trend_Strength": sign * (abs(macd_diff) + (obv or 0)),
        "Close": close,
        "Fibonacci_Levels": calculate_fibonacci_levels(
            indicators["high"], indicators["low"]
        ),
        "metadata": {
            "symbol": symbol,
            "exchange": screener_exchange,
            "interval": interval,
        },
    }
    refined["Recommendation"] = get_recommendation(refined)
    return refined


def get_crypto_analysis(assets, interval="30m", use_cache=False,
                        cache_max_age=1800):
    """Analyse every asset in the configured universe.

    ``assets`` is the settings dict: {ticker: {symbol, screener_exchange, ...}}.
    Returns {ticker: refined_analysis}; failed tickers are omitted (the
    engine refuses to trade when any buyable asset is missing).
    """
    results = {}
    for ticker, details in assets.items():
        try:
            handler = TA_Handler(
                symbol=details["symbol"],
                screener="crypto",
                exchange=details["screener_exchange"],
                interval=interval,
            )
            analysis = cached_response(
                f"{details['symbol']}_analysis",
                lambda h=handler: h.get_analysis().indicators,
                enabled=use_cache,
                max_age=cache_max_age,
            )
            results[ticker] = _refine(
                analysis, details["symbol"], details["screener_exchange"], interval
            )
            log.info("Refined analysis for %s completed", ticker)
        except Exception as exc:  # noqa: BLE001 -- one bad ticker must not kill the run (logged)
            log.warning("Error analysing %s: %s", ticker, exc)
    return results


def generate_swap_summaries(recommendations):
    templates = {
        "sell_buy": "Sell {0} to buy {1}",
        "buy": "Buy {0} and {1}",
        "sell": "Sell {0} and {1}",
        "hold": "Hold {0} and {1}",
    }
    summaries = []
    for rec in recommendations:
        if "error" in rec:
            continue
        head = templates.get(rec["action"], "Unknown action for {0} and {1}")
        summaries.append(
            f"{head.format(*rec['assets'])} ({rec['confidence']:.2f}):\n"
            f"{rec['reason']}\n\n"
        )
    return summaries


def evaluate_crypto_analysis(analytics, assets, llm_client, use_cache=False,
                            cache_max_age=1800):
    """Pairwise LLM comparison of all crypto assets (upper triangle)."""
    recommendations = []
    tickers = [t for t in assets if t in analytics]
    for i, asset_a in enumerate(tickers):
        for asset_b in tickers[i + 1:]:
            # missing "crypto" defaults to True, consistent with get_buyable_cryptos
            if not (assets[asset_a].get("crypto", True)
                    and assets[asset_b].get("crypto", True)):
                continue

            a_pref = assets[asset_a].get("preferred", False)
            b_pref = assets[asset_b].get("preferred", False)
            preferred = None
            if a_pref != b_pref:
                preferred = asset_a if a_pref else asset_b

            log.info("Comparing %s vs %s", asset_a, asset_b)
            result = llm_client.crypto_swap_evaluation(
                asset_a, asset_b, analytics, preferred,
                use_cache=use_cache, cache_max_age=cache_max_age,
            )
            recommendations.append(result)
    return recommendations, generate_swap_summaries(recommendations)


def get_buyable_cryptos(assets):
    return [ticker for ticker, spec in assets.items() if spec.get("crypto", True)]
