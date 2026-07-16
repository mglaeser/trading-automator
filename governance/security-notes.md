# Security notes (Track C design-time analysis)

Consolidated design-time artifacts the Track C checks require. Kept in version control;
re-validated on the re-run triggers in `audit/08-standing-regime.md`.

## Threat model (C-02)
**Data-flow + trust boundaries:**
- **Operator ↔ Web UI (127.0.0.1)** — trust boundary. State-changing routes require a
  bearer token when `web.auth_token` is set; binding beyond loopback without a token is
  refused (`assert_safe_binding`, C-01). Reads are open (operator's own data).
- **Engine ↔ Exchange (Binance/eToro)** — signed/keyed egress; the money-moving boundary,
  bounded by the `_swap` cap + auto-halt.
- **Engine ↔ LLM (Anthropic/OpenAI)** — the model returns text only; its output crosses
  back through schema validation before it can influence a trade (STRIDE: tampering /
  elevation contained here).
- **Engine ↔ TradingView / sipgate** — inbound TA data treated as untrusted; outbound SMS
  is a fixed template.

**STRIDE per boundary → control:** Spoofing (API token / signed exchange requests);
Tampering (schema validation, LOT_SIZE/notional checks); Repudiation (event log +
git provenance); Information disclosure (secret masking, loopback bind, no PII);
DoS (bounded calls, timeouts); Elevation (no tool-use, capped trades).

**Staleness control:** the re-run triggers in `08-standing-regime.md` fire this review when
a new egress/tool/data-class appears. The fixed egress allowlist (6 destinations) is in
code; a new one is a visible diff.

## Prompt injection — residual acceptance (C-07, UNSETTLED)
Prompt injection has **no reliable general defence**; this is accepted in writing. The
mitigation here is **architectural, not detective**: a successful injection cannot trigger
a consequential action, because the model has no tools/egress and its output is reduced to
a fixed, schema-validated action space bounded by the trading cap. Residual risk: a crafted
model output could still choose a *valid* action (buy/sell within the universe) — bounded by
`max_swap_value`/`daily_trade_cap`, dry-run default, and the auto-halt tripwire. Re-accepted
on the standing-regime cadence; tripwire = the cap tests + the injection test in the gate.

## Supply-chain / poisoned-dependency playbook (C-03)
1. `check_deps.py` + `pip-audit` run every push; a non-existent, unpinned, or vulnerable
   package fails the build (calibration D3 proves it).
2. **On a poisoned-dependency alert:** pin to the last-known-good version in
   `requirements.txt`; run `pip-audit` to confirm; rebuild the container from the pinned
   lockfile; if already deployed, `./deploy.sh stop` then redeploy the prior commit.
3. All 9 runtime deps are long-established packages (years old), so slopsquat/newly-
   registered risk is low; the gate is what keeps it low as deps change.

## EU AI Act classification (C-09)
- **AI-system inventory:** one system — an LLM used as an *internal decision advisor* for
  the operator's own portfolio. No user-facing generative content; no decisions about other
  people; not placed on the EU market as a product.
- **Risk tier:** **not high-risk** (not a listed high-risk use; personal, non-professional
  self-hosted use). Article 50 transparency does not bind (no third-party users consuming
  generated content). **Does not hard-gate at 10.**
- If this were ever offered as a service to others, re-classify — the re-run trigger for
  "a move toward multi-user" is wired.

## Disclosure & marking (C-36)
The dashboard clearly labels LLM-derived sentiment/recommendations as model output
(`market_evaluation`, `recommendations` panels). No content is published to third parties,
so machine-readable marking obligations do not bind. Marking is a friction layer, not proof
of provenance — not overclaimed anywhere.

## Jailbreak (C-30)
Not a user-facing chat surface — the model is called with fixed internal prompts, no
end-user prompt reaches it. Jailbreak-to-consequence is bounded by the same architectural
containment as injection (no tools, schema-bounded, capped). Residual accepted with the cap
as the compensating control and tripwire.
