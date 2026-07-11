"""LLM evaluation client.

Primary provider is Anthropic; when it fails AND the OpenAI fallback
succeeds, the client stays on OpenAI for 30 minutes before retrying the
primary. Clients are created lazily from the current settings, so keys
entered in the web UI take effect without restart.

Every LLM response is schema-validated before it can influence a trade;
malformed responses become explicit ``{"error": ...}`` results which the
engine treats as "no signal".
"""

import json
import logging
import re
import time

from .cache import cached_response
from .prompts import market_evaluation_prompt, swap_analysis_prompt

log = logging.getLogger(__name__)

SYSTEM_PROMPT = "You are a crypto finance expert responding in JSON."
FALLBACK_COOLDOWN = 1800  # seconds on the fallback provider after a failure

VALID_ACTIONS = ("sell_buy", "buy", "sell", "hold")
VALID_SENTIMENTS = ("bullish", "bearish", "neutral")


def _parse_json(text):
    """Extract a JSON object from an LLM response, tolerating code fences
    and surrounding prose."""
    text = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


class LLMClient:
    def __init__(self, settings):
        self._settings = settings
        self._last_primary_failure = 0.0

    # -- providers -----------------------------------------------------------

    def _anthropic_completion(self, prompt):
        import anthropic

        cfg = self._settings.get("llm", {})
        if not cfg.get("anthropic_api_key"):
            raise RuntimeError("Anthropic API key not configured")
        client = anthropic.Anthropic(api_key=cfg["anthropic_api_key"])
        response = client.messages.create(
            model=cfg.get("anthropic_model", "claude-sonnet-5"),
            max_tokens=1000,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def _openai_completion(self, prompt):
        import openai

        cfg = self._settings.get("llm", {})
        if not cfg.get("openai_api_key"):
            raise RuntimeError("OpenAI API key not configured")
        client = openai.OpenAI(api_key=cfg["openai_api_key"])
        response = client.chat.completions.create(
            model=cfg.get("openai_model", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content

    @property
    def current_provider(self):
        if time.time() - self._last_primary_failure < FALLBACK_COOLDOWN:
            return "openai"
        return "anthropic"

    def create_completion(self, prompt):
        if self.current_provider == "anthropic":
            try:
                return self._anthropic_completion(prompt)
            except Exception as primary_exc:
                log.warning("Anthropic request failed (%s), trying OpenAI",
                            primary_exc)
                try:
                    result = self._openai_completion(prompt)
                except Exception as fallback_exc:
                    # Don't enter the cooldown when the fallback is unusable
                    # (e.g. no OpenAI key) -- keep retrying the primary and
                    # surface both errors.
                    raise RuntimeError(
                        f"Anthropic failed ({primary_exc}); "
                        f"OpenAI fallback failed ({fallback_exc})"
                    ) from fallback_exc
                self._last_primary_failure = time.time()
                return result
        return self._openai_completion(prompt)

    # -- high-level evaluations ------------------------------------------------

    def crypto_swap_evaluation(self, asset_a, asset_b, analysis, preferred,
                               use_cache=False, cache_max_age=1800):
        prompt = swap_analysis_prompt(asset_a, asset_b, preferred, analysis)
        try:
            raw = cached_response(
                f"{asset_a}_{asset_b}_swap_eval",
                lambda: self.create_completion(prompt),
                enabled=use_cache,
                max_age=cache_max_age,
            )
            parsed = _parse_json(raw)

            # Strict schema validation: anything off becomes a no-signal error.
            action = parsed.get("action")
            assets = parsed.get("assets")
            if action not in VALID_ACTIONS:
                raise ValueError(f"invalid action {action!r}")
            if (not isinstance(assets, list) or len(assets) != 2
                    or set(assets) != {asset_a, asset_b}):
                raise ValueError(f"invalid assets {assets!r}")
            confidence = min(1.0, max(0.0, float(parsed.get("confidence", 0.0))))
            result = {
                "action": action,
                "assets": [str(a) for a in assets],
                "reason": str(parsed.get("reason", "")),
                "confidence": confidence,
            }
            log.info("%s evaluated %s/%s: %s (%.2f)", self.current_provider,
                     asset_a, asset_b, action, confidence)
            return result
        except Exception as exc:
            log.error("crypto_swap_evaluation failed for %s/%s: %s",
                      asset_a, asset_b, exc)
            return {"error": str(exc), "assets": [asset_a, asset_b]}

    def market_evaluation(self, statements, buyable_crypto, use_cache=False,
                          cache_max_age=1800):
        prompt = market_evaluation_prompt("".join(statements), buyable_crypto)
        try:
            raw = cached_response(
                "market_evaluation",
                lambda: self.create_completion(prompt),
                enabled=use_cache,
                max_age=cache_max_age,
            )
            parsed = _parse_json(raw)
            if not isinstance(parsed, dict):
                raise ValueError(f"unexpected result format: {parsed!r}")
            sentiment = str(parsed.get("recommendation", "")).strip().lower()
            if sentiment not in VALID_SENTIMENTS:
                raise ValueError(f"invalid sentiment {sentiment!r}")
            result = {
                "recommendation": sentiment,
                "reason": str(parsed.get("reason", "")),
                "bullish_crypto": str(parsed.get("bullish_crypto", "none")),
            }
            log.info("Market evaluation: %s -- %s", sentiment, result["reason"])
            return result
        except Exception as exc:
            log.error("market_evaluation failed: %s", exc)
            return {"error": str(exc)}
