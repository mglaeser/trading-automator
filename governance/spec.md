# Specification & invariants — the frozen intent (A-04, A-17)

The channel through which human intent enters this machine. Each invariant is stated as
acceptance criteria and mapped to the executable test that pins it. A change that violates
one must fail a test; a change with no mapped criterion should not merge.

## Product intent (non-goals included)
- **Goal:** manage one operator's crypto portfolio on one exchange, driven by TradingView
  technical analysis + an LLM sentiment read, with dry-run-by-default safety.
- **Non-goals:** multi-user/multi-tenant service; custody of other people's funds;
  high-frequency trading; giving the LLM autonomous tool-use; a public web service.

## Invariants and their tests

| # | Invariant (acceptance) | Pinned by |
|---|---|---|
| I-1 | Only assets in `trading.assets` are ever bought or sold. | `test_swap_to_target_ignores_unconfigured_assets`, `test_sell_all_only_configured_crypto` |
| I-2 | Allocation scoring: `sell_buy` moves confidence from asset[0] to asset[1]; negatives clamp to 0; result normalises into the unallocated budget. | `test_distribution_scoring`, `test_distribution_all_hold_returns_zeros` |
| I-3 | A fresh-inflow split fires only on a real delta above baseline, never on a standing reserve. | `test_inflow_split_requires_baseline`, `test_inflow_split_fires_on_delta_only` |
| I-4 | Anchor maintenance buys the deficit, capped (not skipped) at `anchor_swap_max`. | `test_anchor_target_buys_deficit`, `test_anchor_target_caps_large_swaps` |
| I-5 | Sells run before buys; buys clamp to available quote. | `test_swap_to_target_sells_before_buys_and_funds_them`, `test_swap_to_target_clamps_buys_to_available_quote` |
| I-6 | **Every trade is capped:** a swap above `max_swap_value` is clamped down; a swap breaching the rolling-24h `daily_trade_cap` is refused and auto-halts the engine (persisted). Cap `0` disables. | `test_swap_clamps_to_per_swap_ceiling`, `test_daily_cap_refuses_and_halts_engine`, `test_caps_disabled_when_zero` |
| I-7 | LLM output is schema-validated before it can influence a trade; off-schema → no-signal. The model has no tools/egress. | `test_swap_evaluation_valid`, `test_swap_evaluation_rejects_wrong_assets`, `test_swap_evaluation_rejects_bad_action`, `test_market_evaluation_rejects_unknown_sentiment`, `test_injection_cannot_produce_out_of_schema_action` |
| I-8 | Binance quantities quantise DOWN to LOT_SIZE (Decimal-exact); orders below min-notional are refused before placing. | `test_round_step_decimal_exact`, `test_check_notional` |
| I-9 | Signed-request transport errors never leak the signature/query. | `test_transport_errors_do_not_leak_secrets` |
| I-10 | Secrets are masked in every API response; a masked value sent back never overwrites the stored secret. | `test_secret_masking_roundtrip`, `test_config_masking` |
| I-11 | Env vars bootstrap config but a UI-saved value wins across restarts (dry-run can never silently flip back off). | `test_env_bootstraps_but_file_wins` |
| I-12 | Jobs never queue; a second trigger while one runs is skipped. | `test_jobs_never_queue` |
| I-13 | An explicit Stop persists (`runtime.engine_enabled=false`) and survives restart/config-save. | `test_engine_start_stop_idempotent_and_persisted`, `test_autostart_respects_explicit_stop` |
| I-14 | `dry_run` defaults on; SMS never sends in dry-run. | `test_health` (dry_run true), `notifications.send_sms_alert` guard |

## Prioritised non-functional requirements (A-17)
- **Safety (highest):** no unbounded money movement (I-6); no trade on partial signals
  (engine `_rebalance` aborts); fail-safe on any job error (no trade, logged).
- **Security:** no secrets committed (secret-scan gate); no known-vuln deps (pip-audit);
  loopback bind without auth (documented; a reverse proxy required to expose).
- **Reliability:** all external I/O has timeouts; LLM has provider failover; the engine
  self-restarts (container healthcheck + restart policy).
- **Maintainability:** a cold-start agent can pass the gate from this repo + AGENTS.md.

The mutation-smoke corpus (`scripts/mutation_smoke.py`) is the meta-test: it proves these
tests can actually fail. Extend it whenever an invariant is added.
