# 01 — Claims Ledger (Phase 1)

Every claim the system makes about itself — README, docstrings, code comments, endpoint
and identifier names — extracted and tested against the frozen baseline (`840e4f4`). A
false claim is a finding in its own right: it is what a future maintainer, an operator, or
a break-glass responder will trust. Verdicts are `TRUE` / `PARTIAL` / `FALSE`, each with
the probe that produced it. Line references are into the frozen source.

## A. Safety-invariant claims (README §"Safety invariants" + `engine.py` docstring)

| # | Claim | Probe | Verdict | Note |
|---|---|---|---|---|
| 1 | "Only assets in the configured universe are ever bought or sold; airdrops or manually held positions are never touched." | Read `swap_to_target` (sell-off loop guarded by `asset in assets`, `engine.py:446`), `sell_all_crypto` (`assets.get(bal.asset)`, `:496-497`), `_sweep` (`bal.asset not in assets`, `:516`). | **TRUE** | Buys are confined to targets derived from configured assets + quote + anchor. One latent edge: nothing asserts the *anchor* asset is itself in `trading.assets`; a misconfiguration could buy an anchor outside the universe. Filed as a hardening note under A-25. |
| 2 | "A rebalance run aborts (no trades) when technical analysis is missing for any buyable asset, when all pairwise LLM evaluations failed, or when the market evaluation failed." | Read `_rebalance` (`engine.py:315-405`). The three `raise RuntimeError` guards exist (`:340`, `:350`, `:359`). **But** `handle_inflow_split` and `maintain_anchor_target` execute *before* the TA fetch (`:328-331`) and **can place swaps** before any abort fires. | **PARTIAL → FALSE as worded** | The *market rebalance* aborts, but the claim "aborts (**no trades**)" is inaccurate: housekeeping trades (inflow split, anchor maintenance) may already have executed when the abort raises. Operationally small (anchor swap is clamped to `anchor_swap_max`), but the safety wording overstates it. **Finding CL-1**, feeds A-26/A-32. |
| 3 | "Sells always run before buys, and buys are clamped to the actually available quote balance." | `swap_to_target` sorts adjustments ascending so negatives (sells) run first (`:454`); buys use `spend = min(diff, round_down(available))` (`:463`) and decrement `available`. | **TRUE** | Verified by `test_swap_to_target_sells_before_buys_and_funds_them` and `_clamps_buys_to_available_quote`. |
| 4 | "Every LLM response is schema-validated (action/assets/confidence/sentiment) before it can influence a trade." | `crypto_swap_evaluation` validates `action ∈ VALID_ACTIONS`, `assets == {a,b}`, clamps `confidence` (`llm.py:126-131`); `market_evaluation` validates sentiment (`:159-161`). Off-schema → `{"error": …}`. | **TRUE** | Verified by 4 tests in `test_llm_and_exchange.py`. |
| 5 | "Binance orders are pre-checked against the pair's minimum notional and LOT_SIZE (Decimal-exact), and live sells are clamped to the free balance." | `_round_step` uses `Decimal`/`ROUND_DOWN` (`binance_client.py:124-130`); `_check_notional` fails fast (`:132-140`); `swap` clamps to `_free_balance` in live mode (`:234-240`). | **TRUE** | Helpers verified by tests; the integrated `swap()` path (two-leg routing, notional on both legs) is **not** directly tested — see claim #14. |
| 6 | "Inflow detection is delta-based: only an actual increase of the quote balance since the previous cycle counts as a deposit." | `handle_inflow_split` returns `False` until `_last_cycle_quote` is set and only fires on `low < (quote - baseline) < high` (`engine.py:259-264`); baseline set at end of `_rebalance` (`:403-405`). | **TRUE** | Verified by `test_inflow_split_requires_baseline` and `_fires_on_delta_only`. |
| 7 | "A degenerate 'bullish but nothing scored positive' signal keeps the current allocation instead of liquidating everything." | Bullish branch checks `if not any(pct > 0 …)` and skips `swap_to_target` (`engine.py:379-385`). | **TRUE** | Guards against liquidating on an all-hold bullish read. |
| 8 | "Jobs never queue up: a second trigger is skipped with a log line instead of piling onto a lock." | `_run_job` uses `self._job_lock.acquire(blocking=False)` (`engine.py:113`). | **TRUE** | Verified by `test_jobs_never_queue`. |

## B. Security / deployment claims (README §"Security" + `deploy.sh`)

| # | Claim | Probe | Verdict | Note |
|---|---|---|---|---|
| 9 | "No credentials live in the repository." | Full git-history scan, all 4 commits, known + generic secret patterns → zero hits (`audit/evidence/b06-history-scan.txt`). | **TRUE** | `.env` and `config/config.json` gitignored; `config.json` absent on disk. |
| 10 | "Keys … are masked in every API response to the browser." | `GET/PUT /api/config` return `settings.masked()` (`web/app.py:58,79`); `SECRET_PATHS` covers all 7 secret fields; `/api/status` carries no secret fields. | **TRUE** | Masked round-trip verified by `test_config_masking`. |
| 11 | "The web UI has no built-in authentication. Bind it to localhost…" | `deploy.sh`/`compose.yaml` bind `127.0.0.1`; no auth middleware in `web/app.py`. | **TRUE (honest self-disclosure)** | This is an accurate admission, not a control. The mitigation (loopback bind) is real but **any local process / any user on the host** can drive the full API incl. flipping `dry_run` and starting live trading. Feeds C-01 (Part 2) and A-25. |
| 12 | "SMS alerts … never in dry-run mode." | `send_sms_alert` returns early if `dry_run` (`notifications.py:21-23`). | **TRUE** | |
| 13 | "`--restart=always` … an explicit *Stop* … survives … reboot" | `stop_container` clears restart policy (`deploy.sh:127`); `stop()` persists `runtime.engine_enabled=false` (`engine.py:558`); `main.py`/`put_config` autostart gate honours it. | **TRUE** | Verified by `test_autostart_respects_explicit_stop`. |

## C. Documentation-coverage claims (README §"Development")

| # | Claim | Probe | Verdict | Note |
|---|---|---|---|---|
| 14 | "The suite covers the trading maths …, config semantics …, LLM response validation, **Binance order mechanics**, and the web API …" | 38 tests reviewed. Binance coverage = `_round_step`, `_check_notional`, transport-error sanitisation **only**. The `swap()` order-routing (direct/reverse/two-leg), the integrated notional pre-check, and the live free-balance clamp are **not exercised** (they need network or a mocked session). | **PARTIAL** | "Binance order mechanics" overstates the coverage: the *helpers* are tested, the *order path* is not. **Finding CL-2**, feeds A-02 (mutation) and A-16. |
| 15 | "all against an in-memory fake exchange, no network needed." | `conftest.FakeClient` + `TestClient`; no test opens a socket. | **TRUE** | |

## D. Human-review / human-in-the-loop claims (flagged per §1 — claims about controls that may not exist)

| # | Claim | Probe | Verdict | Note |
|---|---|---|---|---|
| 16 | README: "Only after reviewing the logged behaviour, switch *Dry run* to off." | This describes an **operator decision**, not an enforced control. Nothing in code requires any observation window, any minimum dry-run duration, or any gate before `dry_run` can be set to `false` — it can be flipped instantly via `PUT /api/config` or the `DRY_RUN` env var. | **Claim about a non-existent control** | This is legitimately **in-command** (the operator authoring intent to go live), so it is not a false-control in the reviewer sense — but it is **unenforced**. There is no cooling-off, no confirmation, no blast-radius cap gating the transition. **Finding CL-3**, feeds A-34/A-15 and the Phase-5 trading blast-radius cap. |

**No claim in this system asserts an automated human *code-review* step** (there is no
CONTRIBUTING.md, no SECURITY.md, no PR process claimed). That absence is itself accurate:
the system correctly does not pretend a reviewer exists. The one human-dependent claim
(#16) is an operational go-live decision, handled above.

## E. Names as claims (identifier-level; §Phase 1 "Names are claims", Article X)

| Identifier | Asserts | Behaves as named? | Note |
|---|---|---|---|
| `exchange_configured(settings)` | credentials present for selected exchange | **Yes** | case-insensitive check |
| `_check_notional` | order meets pair minimum | **Yes** | raises below minimum |
| `_round_step` | quantise down to LOT_SIZE | **Yes** | Decimal, never rounds up |
| `_free_balance` | actual free balance | **Yes** | live `/account` read |
| `test_connection` | connectivity probe | **Yes** | ping + signed account |
| `handle_inflow_split` | split a fresh deposit | **Yes** | delta-gated |
| `maintain_anchor_target` | hold anchor at target share | **Yes** | clamped adjustment |
| `sell_all_crypto` | sell all crypto | **PARTIAL** | sells all *configured* crypto (`crypto:true`); unconfigured held. Docstring corrects the name, but the bare name over-promises. **Minor**, feeds Article X monthly re-extraction. |
| `create_completion` | LLM completion | **Yes** | with fallback |
| `cached_response` | cache a response | **Yes** | writes even when cache disabled, for inspection — documented |

No convicted lying names of the `validate_user`-that-doesn't-validate class. `sell_all_crypto`
is the only over-promising name; queued as a low-priority Wave-R note (rename to
`sell_configured_crypto` or leave with the clarifying docstring — recorded, not urgent).

## Summary — claims that became findings

- **CL-1** (from claim #2): "rebalance aborts with no trades" is false when inflow/anchor
  housekeeping already traded before the abort. → A-26, A-32.
- **CL-2** (from claim #14): README overstates Binance test coverage; the live order path
  is untested. → A-02, A-16.
- **CL-3** (from claim #16): the dry-run → live transition is unenforced; no blast-radius
  gate. → A-34, A-15; drives the Phase-5 trading cap.

Everything else in the ledger survived contact with reality. The documentation of this
system is, unusually, mostly **true** — the failures are narrow overstatements of safety
("no trades", "order mechanics") rather than fabricated controls.
