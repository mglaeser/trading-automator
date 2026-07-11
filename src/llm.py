"""LLM evaluation client (was llm.py).

Primary provider is Anthropic; on failure it falls back to OpenAI for
30 minutes before retrying the primary. Clients are created lazily from the
current settings, so keys entered in the web UI take effect without restart.
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


def _parse_json(text):
    text = re.sub(r"```json\s*|\s*```", "", text).strip()
    return json.loads(text)


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
            except Exception as exc:
                log.warning("Anthropic request failed (%s), falling back to OpenAI", exc)
                self._last_primary_failure = time.time()
        return self._openai_completion(prompt)

    # -- high-level evaluations ------------------------------------------------

    def crypto_swap_evaluation(self, asset_a, asset_b, analysis, preferred,
                               use_cache=False):
        prompt = swap_analysis_prompt(asset_a, asset_b, preferred, analysis)
        try:
            raw = cached_response(
                f"{asset_a}_{asset_b}_swap_eval",
                lambda: self.create_completion(prompt),
                enabled=use_cache,
            )
            result = _parse_json(raw)
            log.info("%s evaluated %s/%s: %s (%.2f)", self.current_provider,
                     asset_a, asset_b, result["action"], result["confidence"])
            return result
        except Exception as exc:
            log.error("crypto_swap_evaluation failed for %s/%s: %s",
                      asset_a, asset_b, exc)
            return {"error": str(exc), "assets": [asset_a, asset_b]}

    def market_evaluation(self, statements, buyable_crypto, use_cache=False):
        prompt = market_evaluation_prompt("".join(statements), buyable_crypto)
        try:
            raw = cached_response(
                "market_evaluation",
                lambda: self.create_completion(prompt),
                enabled=use_cache,
            )
            result = _parse_json(raw)
            if not isinstance(result, dict) or "recommendation" not in result:
                raise ValueError(f"Unexpected result format: {result}")
            log.info("Market evaluation: %s -- %s",
                     result["recommendation"], result.get("reason"))
            return result
        except Exception as exc:
            log.error("market_evaluation failed: %s", exc)
            return {"error": str(exc)}
