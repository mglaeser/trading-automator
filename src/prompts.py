"""LLM prompt templates (was trader_config.py, minus the hardcoded keys)."""


def swap_analysis_prompt(asset_a, asset_b, asset_preferred, analysis):
    preferred_text = (
        f"If {asset_preferred} is a stronger buy, set the confidence to 1.0."
        if asset_preferred
        else ""
    )
    return f"""### Instructions
Analyze the potential actions for {asset_a} and {asset_b} based on their technical analyses. Consider selling, buying, or holding these assets.

### Rules
1. Evaluate the strength of each asset based on the provided analysis.
2. Determine the best action: sell one to buy the other, buy both, sell both, or hold both.
3. {preferred_text}

### Format
Respond ONLY in this JSON format:
{{
    "action": "sell_buy" or "buy" or "sell" or "hold",
    "assets": ["{asset_a}", "{asset_b}"],
    "reason": "40-word detailed analysis here",
    "confidence": 0.0 to 1.0
}}

### Action Explanations
- "sell_buy": Sell the first asset in "assets" list and buy the second
- "buy": Buy both assets
- "sell": Sell both assets
- "hold": Hold both assets

### Context
{asset_a} Analysis: {analysis[asset_a]}
{asset_b} Analysis: {analysis[asset_b]}

### Task
Determine the best action based on the provided analyses. Ensure your response follows the exact JSON format specified above.
"""


def market_evaluation_prompt(market_statements, buyable_crypto):
    options = '" or "'.join(map(str, buyable_crypto))
    return f"""### Instructions
Carefully analyze the market statements below and determine the overall crypto market sentiment.

### Rules
1. Count trends favoring buying crypto (bullish indicators).
2. Count trends favoring selling crypto (bearish indicators).
3. Compare the counts:
   - More buy trends and indicators = bullish
   - More sell trends and indicators = bearish
   - Relatively slow, neither up nor down indicators = neutral
4. Select an outstanding crypto that has overall very high, very bullish indicators.

### Format
Respond ONLY in this JSON format:
{{
    "recommendation": "neutral" or "bullish" or "bearish",
    "reason": "15-word analysis here",
    "bullish_crypto": "none" or "{options}"
}}

### Context
{market_statements}

### Task
Determine the overall market sentiment based on the above rules and context. Focus solely on buying or selling crypto trends.
"""
