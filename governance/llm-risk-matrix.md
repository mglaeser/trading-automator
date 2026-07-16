# LLM & agentic risk coverage matrix (C-05, C-06)

Every category mapped to a control **and** an executable test. An empty cell is a
finding; a control with no test is a finding wearing a disguise (C-05). Re-validate when
the taxonomy publishes a new edition.

## LLM application risk taxonomy (C-05 — 10 categories)

| Category | Control here | Test |
|---|---|---|
| Prompt injection | Architectural containment: model has no tools/egress; output schema-validated to a fixed action space; capped `_swap`. | `test_injection_cannot_produce_out_of_schema_action`, `test_no_session_holds_the_lethal_trifecta` |
| Sensitive-information disclosure | No third-party PII in the system; secrets masked in API responses; no secrets in prompts. | `test_config_masking`, `test_no_secrets_or_pii_in_prompts` |
| Supply chain | Dependency-existence + pin + SCA gate; all deps long-established. | `scripts/check_deps.py`, `pip-audit`, calibration D3 |
| Data & model poisoning | N/A — no training/fine-tuning, no persistent corpus. Cache is short-TTL, per-symbol, reproducible. | argued N/A (C-21, B-33) |
| Improper output handling | Schema validation → no-signal on bad output; UI escapes all interpolation (`esc()`). | `test_swap_evaluation_rejects_*`, XSS escaping in index.html |
| Excessive agency | Trading blast-radius cap + auto-halt at `_swap`; model has no tools. | `test_daily_cap_refuses_and_halts_engine`, `test_llm_advisor_has_no_egress_or_tools` |
| System-prompt leakage | System prompt carries no secrets/rules-as-controls; scanned. | `test_no_secrets_or_pii_in_prompts`, `secret_scan.py` |
| Vector & embedding weaknesses | N/A — no vector store / embeddings. | argued N/A (C-32) |
| Misinformation / fabrication | Only schema-bounded `action`/`confidence` drive trades; the free-text `reason` is displayed, never acted upon; dry-run default + cap bound impact. | `test_swap_evaluation_*`; C-38 finding |
| Unbounded consumption | LLM `max_tokens=1000`, bounded calls/cycle; trading cap bounds money. | `test_daily_cap_*`, cap tests |

## Agentic risk taxonomy (C-06 — 10 categories)

Most are inert because **the LLM is an advisor with no tool-use** (`governance/capability-labels.json`).

| Category | Status here |
|---|---|
| Goal hijack | Contained: hijacked output is still schema-bounded and capped. |
| Tool misuse | N/A — the model has no tools. |
| Identity & privilege abuse | Single principal (operator); no per-agent identities to abuse. |
| Agentic supply chain | N/A — no connectors/MCP servers (C-17, C-18 N/A). |
| Unexpected code execution | N/A — no code-exec capability from the model. |
| Memory & context poisoning | N/A — no persistent agent memory (C-19). |
| Insecure inter-agent comms | N/A — single engine, no agent-to-agent. |
| Cascading failures | Bounded: fail-safe (no trade on error) + cap + auto-halt. |
| Human-agent trust exploitation (→ *pipeline's* trust in model output) | Contained: the pipeline trusts only schema-valid output, and the cap bounds the consequence. |
| Rogue agents | N/A — no autonomous agents; one deterministic engine. |

**Conclusion:** C-06 does **not** escalate to STOP-SHIP — no model here can call a tool that
writes, sends, spends, deletes or executes. The one live concern (the pipeline trusting
model output) is bounded structurally by schema validation and the trading cap.
