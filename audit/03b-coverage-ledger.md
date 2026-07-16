# 03b — Coverage Ledger (Phase 3)

"Thorough" is defined here, not in the executive summary. Every item in
`00-audit-surface.json` is mapped to at least one executed check. Phase 3 does not close
while any item is uncovered; none is. (Track C's 40 checks will add security-specific
coverage in Part 2; the items below are covered by the 79 Track A/B checks now.)

## Source modules

| Surface item | Covered by | Evidence |
|---|---|---|
| `src/settings.py` | A-04, A-13, A-23, A-25, B-06, B-14 | secret masking + coercion read; `test_settings.py` |
| `src/engine.py` | A-02, A-10, A-11, A-24, A-26, A-34, B-08, B-15, CL-1 | full read; `test_engine.py`; calibration D2/D4 |
| `src/llm.py` | A-02, A-03, A-10, A-27, B-05, B-07, B-13, B-15, B-21, B-24 | full read; `test_llm_and_exchange.py`; calibration D1/D6 |
| `src/prompts.py` | A-20, B-05, B-14 | full read; prompts are code constants (no hot-swap path) |
| `src/analysis.py` | A-10, A-25, A-26, B-33 | full read; per-ticker log-and-continue confirmed |
| `src/cache.py` | A-23, B-33, B-38 | full read; TTL + mtime; no personal data |
| `src/scheduler.py` | A-24, A-26, B-26 | full read; race-free stop; log-and-continue |
| `src/notifications.py` | A-26, A-28, B-28 | full read; dry-run guard; timeout present |
| `src/state.py` | A-25, B-03, B-07 | full read; bounded event log; masking-safe |
| `src/main.py` | A-15, A-24, B-01, B-25 | full read; AUTOSTART gate |
| `src/exchanges/base.py` | A-05, A-09, A-11 | full read; ABC boundary |
| `src/exchanges/binance_client.py` | A-10, A-11, A-26, A-28, A-34, B-06, CL-2 | full read; Decimal/notional/free-balance verified; calibration |
| `src/exchanges/etoro_client.py` | A-11, A-26, A-28, A-34 | full read; close-smallest-first logic |
| `src/web/app.py` | A-19, A-25, A-26, B-01; C-01 (Part 2) | full read; no-auth mutating routes noted |
| `src/web/static/index.html` | A-22, A-25 (XSS); C-01 (Part 2) | read; `esc()` escaping on all innerHTML confirmed |

## Routes (all 9 + index)

| Item | Covered by | Note |
|---|---|---|
| `GET /`, `/api/health`, `/api/status` | A-19, A-25 | read-only; no secret leakage |
| `GET /api/config` | A-25, B-06 | masked (`test_config_masking`) |
| `PUT /api/config` (mutating, no auth) | A-15, A-25, A-34, B-14; C-01 (Part 2) | can flip dry_run / autostart — flagged |
| `POST /api/engine/{start,stop}` | A-34, A-35; C-01 (Part 2) | manual kill switch |
| `POST /api/run/{job}` | A-25, A-34; C-01 (Part 2) | job allowlist; can trade live |
| `POST /api/test-connection` | A-25, A-26 | error path returns sanitized status |

## Scheduled jobs, data stores, egress, identities, prompts, deps

| Item | Covered by |
|---|---|
| jobs `refresh/rebalance/repay/sweep` | A-10, A-24, A-34, A-35, B-26 |
| `config/config.json` (secrets) | B-06, B-25, B-37(N/A), A-23 |
| `artifacts/cache/*.json` | B-33, B-38(N/A), A-23 |
| `EngineState` (in-mem) | B-03, B-07, A-25 |
| egress: binance, etoro | A-11, A-28, A-34, B-20, B-22 |
| egress: anthropic, openai | A-10, A-27, B-13, B-20, B-21 |
| egress: tradingview | A-10, A-25, B-33 |
| egress: sipgate | A-26, A-28, B-28 |
| identities (operator keys) | B-06, B-22, B-25 |
| prompts (2 + system) | A-20, B-05, B-14 |
| 9 runtime deps | B-04, A-08, A-38 |
| Dockerfile / deploy.sh / compose.yaml | A-06, B-09, B-12, B-17, B-25, B-27 |
| requirements*.txt | B-04, A-38 |
| 5 test files (38 tests) | A-02, A-03, A-36 |
| `.github/` (absent) | A-01, A-08, A-13, B-01 — the covering finding is the ABSENCE |

## Uncovered items

**None.** Every audit-surface item is touched by ≥1 executed check. The `policy_bundle`
item is "covered" by A-01/B-01/B-35/A-39 whose finding is precisely that it does not exist.
Items listed as `[]` in the surface (tools_callable_by_model, vector_stores, databases,
rag_corpora, fine_tuned_models) are covered by the NOT-APPLICABLE justifications of the
checks that presuppose them (A-21, B-33, B-23, C-21/Part 2).
