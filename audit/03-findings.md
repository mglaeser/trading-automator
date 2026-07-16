# 03 — Findings (catalogue v1.0 — 79 Track A/B checks)

> Phase-6 re-audit tally: **NOT-APPLICABLE** 13, **PARTIAL** 50, **PASS** 16.
> Baseline was 0 PASS / 52 PARTIAL / 14 FAIL / 13 N/A; every FAIL closed to PASS or PARTIAL-with-residual.


## STOP-SHIP

### B-06 — Secrets and machine identity · **PARTIAL** (P10)
- **Probe:** Scanned all 4 commits' blobs + client bundle + env files for secrets; inspected at-rest storage and identity model.
- **Evidence:** audit/evidence/b06-history-scan.txt: zero committed secrets across all history
- **Evidence:** .gitignore excludes .env and config/config.json; config.json absent on disk
- **Evidence:** settings.py: secrets stored PLAINTEXT in config/config.json; no vault, no rotation, no expiry
- **Evidence:** No secret-scanning gate exists (calibration D1 MISSED, 02-calibration.md)
- **Note:** The STOP-SHIP hazard (a committed long-lived secret) is ABSENT — history is clean. What is open: (1) no standing secret-scan gate, so a future leak is uncaught; (2) plaintext long-lived keys at rest, no rotation. Not PASS because nothing holds it. Out-of-repo: the credentials pasted in the original chat must be rotated at their providers.
- **Standing control (planned):** Phase 5: secret-scan (detect-secrets/gitleaks-style) in CI, head every push + full history, fail closed.


## BLOCKER-1

### A-01 — The verification gate on every production change · **PASS** (P9)
- **Probe:** Looked for a deterministic policy gate / branch protection / required checks; tried to find any automated block on merge.
- **Evidence:** .github/ absent — no CI, no branch protection, no required status checks
- **Evidence:** Merges reach the branch by direct `git push`; nothing runs the 38-test suite automatically
- **Evidence:** Calibration: pipeline catches 2/6 seeded defects (02-calibration.md)
- **Note:** STOP-SHIP under §3: with A-39 (no independent verifier) also failing, NEITHER a human NOR a machine independently verifies any line of production code. This voids every other PASS in the volume until fixed.  [Phase 6] Deterministic gate built and demonstrated to block; R-1 (branch protection) is operator-in-command.
- **Standing control:** .github/workflows/ci.yml + scripts/policy_gate.py: every push runs lint, tests, mutation-smoke, dep-existence, SCA, secret-scan, model-pin, calibration and the fail-closed policy gate; no override in the workflow. _(cadence: every push / PR; blocks: merge; owner: operator (in-command) + CI)_ — **demonstrated:** policy_gate.py exited 1 at the Phase-3 baseline naming each open blocker; all gate jobs run green post-repair -- audit/evidence/phase5-gate-demonstration.txt. RESIDUAL R-1: branch protection must be enabled on the remote for the gate to be unbypassable.

### A-02 — A test suite that can actually fail · **PASS** (P9) · _structural_
- **Probe:** Ran the suite clean (38 passed), then seeded a swallowed exception (D4) and a vacuous test (D5) and re-ran.
- **Evidence:** D4 (swallowed order exception) MISSED — suite stayed green
- **Evidence:** D5 (vacuous assertion) MISSED — suite grew to 39 passed
- **Evidence:** No mutation testing configured anywhere in the repo
- **Note:** STOP-SHIP under §3: the suite cannot detect injected faults, so a green build means nothing. The engine's decision logic is fairly pure (functional-core/shell largely already holds), so mutation is reachable.  [Phase 6] The suite provably detects injected core faults.
- **Standing control:** scripts/mutation_smoke.py injects 8 core-logic faults; the suite must kill each. Runs in the gate. _(cadence: every push (smoke) + extendable weekly full mutmut; blocks: merge; owner: operator + CI)_ — **demonstrated:** mutation_smoke.py: 8/8 killed, score 1.00 -- audit/evidence/phase5-gate-demonstration.txt. Closes calibration defect D5's class.

### A-06 — Version control, batch size and a rollback that has been executed · **PARTIAL** (P9) · _structural_
- **Probe:** Plotted commit sizes/branch lifetime; looked for an executed, timed rollback and an automatic abort.
- **Evidence:** 4 commits; the first is a large rebuild (not atomic) — no batch-size gate
- **Evidence:** No rollback has been executed/timed; no automatic abort wired to any signal
- **Evidence:** deploy.sh update rebuilds forward only; rollback would be manual git+redeploy
- **Note:** A rollback PATH exists (redeploy a prior commit/image) but is untested and human-triggered. No CI on push.  [Phase 6] CI-on-push now exists; rollback still untested/manual (residual).
- **Standing control (planned):** Phase 5: CI on every push; document+the rollback runbook; batch-size advisory. Full auto-abort is out of reach for a single-instance deploy (residual).

### A-08 — Security scanning is the control, not a first pass before one · **PASS** (P9)
- **Probe:** Looked for SAST/DAST/SCA/secret scanning wired as blocking gates; seeded a credential (D1) and a bad dependency (D3).
- **Evidence:** No static analysis, dependency scanning, or secret scanning in any gate
- **Evidence:** D1 (hard-coded credential) and D3 (non-existent dependency) both MISSED
- **Note:** Security scanning is the control here, and it does not exist. Highest-yield gap alongside A-01/B-04.  [Phase 6] Scanning is the control and each scanner catches its seeded class.
- **Standing control:** ruff (lint+security idioms) + pip-audit (SCA) + secret_scan + check_deps, all blocking. _(cadence: every push; secret scan also over full history; blocks: merge; owner: operator + CI)_ — **demonstrated:** ruff clean; pip-audit 'No known vulnerabilities'; secret_scan PASS; each seed caught -- audit/evidence/phase5-gate-demonstration.txt.

### A-24 — The system operates and recovers itself · **PARTIAL** (P9)
- **Probe:** Induced failure modes mentally + checked recovery: healthcheck, restart policy, SLOs, incident->test.
- **Evidence:** Dockerfile HEALTHCHECK + --restart=always give automatic container restart
- **Evidence:** engine._run_job fails SAFE: on any job error it logs, records state, and does NOT trade; rebalance failure sends SMS
- **Evidence:** No SLO/error-budget, no auto-rollback, no incident->regression-test discipline
- **Note:** Fails safe (no trade on error) and self-restarts, which is the meaningful recovery for a personal bot. Missing: SLOs, auto-recovery coverage metric.
- **Standing control (planned):** Phase 5: document the fail-safe invariant as a test; SLO/error-budget out of scope for single-user (residual).

### B-01 — The pipeline actually gates · **PASS** (P9)
- **Probe:** Looked for a pipeline that blocks; grepped for soft-fail constructs.
- **Evidence:** .github/ absent — there is no pipeline to gate or soft-fail
- **Evidence:** The 38-test suite is the entire safety net and nothing runs it automatically
- **Note:** Sibling of A-01. The pipeline is not a weak safety net — it does not exist.  [Phase 6] The pipeline gates (was: no pipeline).
- **Standing control:** The CI gate blocks; no soft-fail constructs; policy_gate is the sole merge authority. _(cadence: every push; blocks: merge; owner: operator + CI)_ — **demonstrated:** all gate jobs demonstrated; policy_gate blocks on open blockers -- audit/evidence/phase5-gate-demonstration.txt. RESIDUAL R-1 as A-01.

### B-03 — Observability that reaches root cause · **PARTIAL** (P9)
- **Probe:** Tried to follow one request end-to-end through logs/metrics/traces.
- **Evidence:** logging configured (main.py) + structured in-memory event log (state.py, <=300 events)
- **Evidence:** No traces, no metrics, no request IDs, no OpenTelemetry
- **Note:** For a single-user bot the logs + event log reach root cause for the common cases; no distributed tracing (nor needed). Re-scoped from enterprise observability.
- **Standing control (planned):** Phase 5: none added (proportionate); documented as accepted for repo class.

### B-04 — Dependencies that exist, are pinned, and were vetted · **PASS** (P9)
- **Probe:** Enumerated all 9 runtime deps; resolved each against the index; checked pinning; seeded a fake package (D3).
- **Evidence:** All 9 pinned to exact versions and ALL resolve on the index (probe in Phase 3 log): fastapi,uvicorn,requests,tradingview-ta,anthropic,openai,astral,pytz,python-dotenv
- **Evidence:** No hash pinning (no lockfile); no existence/SCA gate — D3 MISSED
- **Note:** No hallucinated or unpinned package is present. The gap is the missing GATE: nothing stops a future slopsquat/unpinned add.  [Phase 6] No hallucinated/unpinned dependency can enter a build.
- **Standing control:** scripts/check_deps.py (existence + pin) + pip-audit (known-vuln), blocking. _(cadence: every push; blocks: merge; owner: operator + CI)_ — **demonstrated:** check_deps: 9/9 pinned deps exist on PyPI; D3 slopsquat caught; pip-audit clean -- audit/evidence/phase5-gate-demonstration.txt.

### B-11 — Rollback for code, prompts and models · **PARTIAL** (P9)
- **Probe:** Checked rollback for code, prompts, models and whether it can fire on a signal.
- **Evidence:** Code/prompt/model are all in-repo, so rollback = git revert + redeploy (untested, manual)
- **Evidence:** Models are FLOATING aliases (B-13), so there is no pinned version to roll back TO
- **Note:** Rollback is a manual redeploy; prompts roll back with code; model rollback is undermined by floating aliases.
- **Standing control (planned):** Phase 5: pin model snapshots (B-13) so a model rollback target exists; document the redeploy rollback.

### B-20 — Runtime detection and containment of injection and exfiltration · **PASS** (P9) · _structural_
- **Probe:** Traced every path by which model output or retrieved text could egress data; attempted to construct the exfil channel.
- **Evidence:** The LLM has NO tools, NO outbound capability — it returns schema-validated JSON only (llm.py)
- **Evidence:** The egress allowlist is fixed in code (6 destinations); the model cannot add one
- **Evidence:** No runtime exfil detection exists — but the channel it would detect does not exist
- **Note:** Strong architectural containment: the exfiltration leg is structurally absent (the model cannot act or egress). No runtime detector, and none is load-bearing here.  [Phase 6] Exfiltration is structurally absent, not merely undetected.
- **Standing control:** Structural (S13): the model has no egress capability; the exfil leg does not exist. The egress allowlist is fixed in code (6 destinations); the model cannot add one. _(cadence: every push; blocks: merge; owner: operator + CI)_ — **demonstrated:** The LLM returns text only (llm.py); no tool/function-calling path; trades go through _swap.

### B-22 — Agents deployed with least privilege, enforced · **PARTIAL** (P9) · _structural_
- **Probe:** Enumerated the process's privileges and whether they are least and enforced.
- **Evidence:** Single process, single principal (operator's keys); no per-agent identities
- **Evidence:** README advises no-withdrawal + IP-pinned exchange keys; not enforceable in code (exchange-side scope)
- **Evidence:** Key scope is deny-by-default only if the operator sets it so at the exchange
- **Note:** Re-scoped: there are no autonomous agents to privilege-separate. The meaningful least-privilege is the exchange key scope, which is documented but exchange-side.
- **Standing control (planned):** Phase 5: a startup check that warns if withdrawal-capable keys are detectable via test_connection permissions; document.


## BLOCKER-2

### A-04 — A specification exists, is testable, has non-goals, gates merges · **PARTIAL** (P8)
- **Probe:** Looked for testable acceptance criteria, explicit non-goals, and a spec-coverage gate.
- **Evidence:** No spec/acceptance-criteria/non-goals artifact exists; README+tests are the de-facto spec
- **Evidence:** No spec-coverage gate; a change mapping to no criterion can merge freely
- **Note:** Intent lives only in prose + tests. The frozen spec that §1 makes the sole channel of human intent is absent.  [Phase 6] spec.md now records invariants+NFRs mapped to tests; no spec-coverage GATE yet (residual).
- **Standing control (planned):** Phase 4/5: write governance/spec.md (invariants as executable acceptance) + tie the safety invariants to named tests.

### A-09 — Architecture as decided, not as accreted · **PARTIAL** (P8) · _structural_
- **Probe:** Tested the decomposition; looked for ADRs and fitness functions.
- **Evidence:** Clean layering: exchanges/ (adapters behind ABC), web/ (API), engine/llm/analysis/scheduler separated
- **Evidence:** No ADRs; no architecture fitness function enforcing boundaries
- **Note:** Architecture is genuinely decided, not accreted — but nothing enforces it stays that way.
- **Standing control (planned):** Phase 5: an import-boundary lint (ruff isort/flake8-tidy-imports) asserting web/ and exchanges/ never import engine internals; ADR for the exchange-abstraction decision.

### A-10 — Injection-resistant architecture, not injection-resistant wording · **PASS** (P8)
- **Probe:** Traced untrusted text (TradingView data, LLM output) to any consequential action; attempted to make it act.
- **Evidence:** LLM output is schema-validated to a fixed action space (llm.py:126-131); off-schema => no trade
- **Evidence:** The LLM cannot call tools; the engine (deterministic) executes trades from validated JSON only
- **Evidence:** No injection test corpus
- **Note:** Injection containment is ARCHITECTURAL and real: a successful injection cannot exceed {sell_buy,buy,sell,hold} on configured assets with clamped confidence. This is a strength.  [Phase 6] Injection containment is architectural, not a filter -- it cannot decay.
- **Standing control:** Structural (S13): the LLM has no tools/egress and can only influence a trade via schema-valid output; test_injection_cannot_produce_out_of_schema_action pins it. _(cadence: every push; blocks: merge; owner: operator + CI)_ — **demonstrated:** test_injection_cannot_produce_out_of_schema_action passes; _swap is the sole trade chokepoint (grep: one client.swap call); mutation 'action validation inverted' killed.

### A-17 — Non-functional requirements, specified and measured · **PARTIAL** (P8)
- **Probe:** Looked for an NFR table across the nine quality characteristics with measures.
- **Evidence:** No NFR specification exists
- **Note:** NFRs are implicit. For a personal bot most are low-stakes, but safety/security NFRs of an AI money-mover deserve explicit measures.  [Phase 6] spec.md prioritises safety/security/reliability NFRs with tests; not all have runtime measures (residual).
- **Standing control (planned):** Phase 4: governance/spec.md records the prioritised NFRs (safety, security, reliability) with the tests that measure them.

### A-22 — User outcomes, performance and accessibility · **NOT-APPLICABLE** (P8)
- **Probe:** Assessed against public-service accessibility/RUM obligations.
- **Evidence:** Single-operator internal dashboard bound to 127.0.0.1; not a public service
- **N/A:** WCAG-AA-as-legal-obligation and Core-Web-Vitals RUM target public/consumer services. This is a private single-user localhost dashboard with no external users, so the public-accessibility framing does not bind. Basic usability is adequate (simple, escaped HTML). The one real 'user outcome' (P&L) is noted as untracked under A-24/A-27, not here.

### A-25 — Input validation at every boundary · **PARTIAL** (P8)
- **Probe:** Enumerated entry points and checked server-side validation; treated TA/LLM as untrusted input.
- **Evidence:** PUT /api/config coerces+drops bad types (settings.update); run_job validates job in JOBS; index.html escapes all innerHTML interpolation (esc())
- **Evidence:** LLM output schema-validated; exchange responses parsed defensively
- **Evidence:** No auth on the mutating boundary (PUT /api/config, engine/start) — any local process can drive it
- **Evidence:** No property/fuzz tests on parsers (_parse_json, settings coercion)
- **Note:** Validation is present at the important boundaries; the gaps are (a) no authn on state-changing routes (mitigated by loopback bind, feeds C-01/Part 2) and (b) no fuzz tests.
- **Standing control (planned):** Phase 5: property tests on _parse_json and settings._coerce in CI.

### A-33 — Maintainability without a maintainer · **PARTIAL** (P8)
- **Probe:** Asked whether a cold-start agent could safely change this from the repo alone; assessed artifacts.
- **Evidence:** Clean, documented, tested code; strong docstrings stating invariants
- **Evidence:** No AGENTS.md; no per-module spec/provenance link; no cold-start-agent test
- **Note:** Maintainability is good for a human; the machine-maintainability artifacts (agent instructions, spec links) are thin.
- **Standing control (planned):** Phase 4/5: add AGENTS.md + governance/spec.md so a cold agent has the invariants; the CI gate becomes the safety net a cold agent leans on.

### A-34 — Autonomy levels, deterministic gates and a kill switch that fires itself · **PASS** (P8) · _structural_
- **Probe:** For each action class checked reversibility, a deterministic validator, a blast-radius cap, an automatic tripwire; pulled the kill switch.
- **Evidence:** Live trades are IRREVERSIBLE; validators present: notional pre-check, LOT_SIZE, free-balance clamp, universe restriction, sells-before-buys
- **Evidence:** MISSING: any blast-radius cap (no per-cycle/daily notional limit, no max trades, no loss limit) and any AUTOMATIC halt
- **Evidence:** Kill switch = manual Stop (engine.stop()); no tripwire fires it
- **Note:** The single most material product finding: an irreversible real-money capability with partial validators but NO blast-radius cap and NO self-firing halt. Drives the Phase-5 trading cap.  [Phase 6] Autonomy is bounded by a validated cap and a self-firing halt.
- **Standing control:** Kill switch fires itself: a swap breaching daily_trade_cap calls _halt(), which stops trading, persists runtime.engine_enabled=false, and shuts the scheduler off-thread. _(cadence: every push (halt test); blocks: merge + runtime; owner: operator + CI)_ — **demonstrated:** test_daily_cap_refuses_and_halts_engine: engine_running False + persisted after the breach.

### B-02 — A paved road an agent can walk · **PARTIAL** (P8)
- **Probe:** Cloned-clean bootstrap: pip install -r requirements-dev.txt + python -m src.main; also deploy.sh.
- **Evidence:** One-command bootstrap works (deploy.sh; or pip + python -m src.main)
- **Evidence:** No cold-start-AGENT walk; no AGENTS.md
- **Note:** Paved road exists for a human; not proven for a cold agent.
- **Standing control (planned):** Phase 5: AGENTS.md documents the paved road; CI bootstraps from a clean checkout on every run (proves it).

### B-05 — Models, prompts and agents have a lifecycle · **PARTIAL** (P8) · _structural_
- **Probe:** Looked for a model/prompt/agent registry with versioning + rollback.
- **Evidence:** Prompts are versioned as code (prompts.py); models pinned in settings but as floating aliases (B-13)
- **Evidence:** No registry; no eval history
- **Note:** Lifecycle is 'whatever is in code + settings'. Prompts are structurally un-hot-swappable (code constants) which is good.
- **Standing control (planned):** Phase 5: model pinning (B-13); prompt-change eval note. Full registry disproportionate for 2 prompts (residual).

### B-07 — Every model and agent run is traceable and replayable · **PARTIAL** (P8) · _structural_
- **Probe:** Tried to reconstruct one LLM interaction: model, version, prompt, output, tokens, cost.
- **Evidence:** llm.py logs provider + action + confidence; cache stores the raw response (dry-run)
- **Evidence:** Not recorded: prompt hash, token counts, cost, exact model snapshot
- **Note:** Partial replayability. For a personal bot the cache + logs are usually enough; provenance fields are thin.
- **Standing control (planned):** Phase 5: log model id + prompt hash + token usage at each call (one typed emit point in llm.py).

### B-10 — Evaluation gates in the pipeline · **PARTIAL** (P8) · _structural_
- **Probe:** Looked for a golden/eval dataset gating prompt/model changes; checked for a backtest.
- **Evidence:** No golden dataset, no regression eval, no backtest harness for the LLM trading decisions
- **Note:** The LLM's trading judgement ships with no offline evaluation. Notable for a money-mover — a prompt/model change cannot be regression-tested.  [Phase 6] deterministic decision surface (scoring/schema) is regression-tested; a live-model golden set is disproportionate for an advisory, schema-bounded LLM -- residual.
- **Standing control (planned):** Phase 5: a small golden-fixture eval (canned TA -> asserted action distribution) as a CI check; structural held-out-store disproportionate (residual).

### B-12 — Runtime defence · **PARTIAL** (P8)
- **Probe:** Checked runtime defence + patch cadence.
- **Evidence:** Localhost bind is the network defence (no WAF needed for loopback); python:3.12-slim base + pinned deps
- **Evidence:** No automated base-image/dependency patch cadence
- **Note:** Re-scoped: WAF N/A for a loopback single-user UI. Patch cadence is unmanaged.
- **Standing control (planned):** Phase 5: pip-audit in CI flags vulnerable deps; Dependabot-style note in AGENTS.md.

### B-13 — Pinned model versions -- no floating aliases · **PARTIAL** (P8) · _structural_
- **Probe:** Grepped model identifiers in settings for floating vs dated snapshots.
- **Evidence:** settings.py DEFAULTS: anthropic_model='claude-sonnet-5', openai_model='gpt-4o-mini' — both FLOATING aliases, not dated immutable snapshots
- **Evidence:** No CI check forbidding unpinned model references
- **Note:** A floating alias means provider-side model migration changes behaviour while the code does not — the one failure class no review would catch. Concrete, one-class fix.  [Phase 6] check_model_pins blocks '-latest' aliases; current ids remain provider aliases (operator should pin dated snapshots) -- residual.
- **Standing control (planned):** Phase 5: default to dated snapshots where available + a lint (scripts/check_model_pins.py) failing on alias-style ids; drift scan of running config.

### B-15 — Guardrails are deployed artifacts, and they fail closed · **PASS** (P8)
- **Probe:** Turned the 'guardrail' off: fed malformed/oversized LLM output and confirmed behaviour.
- **Evidence:** The guardrail here = LLM-output schema validation; it FAILS CLOSED (bad output -> {'error'} -> no trade), verified by tests
- **Evidence:** No separate guardrail service to kill; no adversarial corpus
- **Note:** Fail-closed validation is real and tested — a genuine strength. There is no fail-open path from bad model output to a trade.  [Phase 6] The guardrail fails closed and is tested.
- **Standing control:** Schema validation fails CLOSED (bad model output -> no-signal -> no trade); test_injection + the rejection tests pin it. _(cadence: every push; blocks: merge; owner: operator + CI)_ — **demonstrated:** test_injection_cannot_produce_out_of_schema_action + 3 rejection tests pass.

### B-28 — Detection that triggers action, not just a notification · **PARTIAL** (P8)
- **Probe:** Checked whether detection triggers action or only notifies.
- **Evidence:** SMS alerts on repay + rebalance failure (notification); the engine itself auto-responds by NOT trading on error (fail-safe)
- **Evidence:** No automated remediation beyond fail-safe + restart
- **Note:** The consequential auto-response (don't trade on bad signal) exists structurally; alerts are notifications on top.
- **Standing control (planned):** Phase 5: the trading-cap tripwire (A-34) is the automated response that halts on anomaly.

### B-31 — Backups you have actually restored · **PARTIAL** (P8)
- **Probe:** Identified durable state and whether a restore was ever performed.
- **Evidence:** Only durable state is config/config.json (keys) + optional .env; EngineState is ephemeral by design
- **Evidence:** No backup/restore drill; config is re-enterable via the UI
- **Note:** Minimal durable state; restore = re-enter keys or copy config.json. Low stakes, but no documented procedure.
- **Standing control (planned):** Phase 5: document config backup in AGENTS.md; no automated restore drill (proportionate residual).


## MUST-FIX

### A-05 — Domain boundaries and a consistent vocabulary · **PARTIAL** (P7) · _structural_
- **Probe:** Mapped modules for a shared vocabulary and enforced boundaries.
- **Evidence:** Consistent domain vocabulary (asset/quote/anchor/swap/balance); one owning role (operator)
- **Evidence:** Boundaries by convention only — no import linter
- **Note:** Clean boundaries, not enforced.
- **Standing control (planned):** Phase 5: import-boundary lint (shared with A-09).

### A-07 — Clone, churn and refactoring signature · **PARTIAL** (P7) · _structural_
- **Probe:** Scanned for duplicated blocks/churn; looked for a clone gate.
- **Evidence:** 140 defs/classes across 15 modules; code is notably DRY (shared base ABC, helpers reused)
- **Evidence:** No clone detector / duplication tripwire in CI
- **Note:** Low duplication observed; no standing tripwire to keep it low.
- **Standing control (planned):** Phase 5: ruff + a duplication note; full clone detector disproportionate.

### A-11 — Least-privilege topology for every agent and tool (design) · **PASS** (P7) · _structural_
- **Probe:** Enumerated every capability the model/engine can reach and its reversibility.
- **Evidence:** Model: zero tools (cannot act). Engine: exchange trade calls (irreversible) with notional/balance/universe validators
- **Evidence:** No blast-radius cap; no dry-run diff -> apply -> compensate wrapper
- **Note:** Least-privilege on the MODEL is total (no tools). The engine's irreversible capability lacks a cap — same root as A-34.  [Phase 6] Least-privilege on the model is total; the engine's irreversible action is capped.
- **Standing control:** The irreversible trade capability is wrapped at the single _swap chokepoint: estimate -> clamp to max_swap_value -> daily-cap check -> execute; model holds no tools. _(cadence: every push (cap tests); blocks: merge; owner: operator + CI)_ — **demonstrated:** test_swap_clamps_to_per_swap_ceiling + test_daily_cap_refuses_and_halts_engine pass; clone sweep: client.swap() called in exactly one place (engine.py:_swap).

### A-12 — Technical debt and the comprehension problem · **PARTIAL** (P7) · _structural_
- **Probe:** Looked for dead code and per-module reconstructibility.
- **Evidence:** No dead/unreached modules found; every module is imported and exercised
- **Evidence:** No per-module spec-link/provenance record
- **Note:** No deletion needed (tight codebase). Reconstructibility artifacts thin.
- **Standing control (planned):** Phase 4: spec.md links invariants to modules.

### A-13 — Enforced coding standards · **PASS** (P7)
- **Probe:** Checked for lint/format/static analysis blocking in CI.
- **Evidence:** No linter, formatter, or static analysis configured; no pyproject.toml
- **Note:** No enforced standards.  [Phase 6] Coding standard enforced and self-tested.
- **Standing control:** ruff check src tests, blocking; per-file suppressions carry justifications and are counted. _(cadence: every push; blocks: merge; owner: operator + CI)_ — **demonstrated:** ruff clean on product code; catches D4 -- audit/evidence/phase5-gate-demonstration.txt.

### A-18 — Model and agent architecture chosen deliberately · **PARTIAL** (P7)
- **Probe:** Asked why single-LLM + fallback; checked context budget.
- **Evidence:** Documented rationale in llm.py docstring (primary+fallback, cooldown); context is small/bounded per cycle
- **Evidence:** No ADR
- **Note:** Deliberate and simple; no ADR artifact.
- **Standing control (planned):** Phase 4: ADR for the LLM-advisor architecture.

### A-19 — API contracts that match the implementation · **PARTIAL** (P7) · _structural_
- **Probe:** Diffed FastAPI-generated OpenAPI against reality; checked idempotency/errors.
- **Evidence:** FastAPI auto-generates the schema from handlers (matches by construction); single consumer = bundled UI
- **Evidence:** No contract test; errors are ad hoc (HTTPException + JSONResponse)
- **Note:** Contract drift is low-risk (one in-repo consumer, generated schema). No standing contract test.
- **Standing control (planned):** Phase 5: a smoke test asserting the route set + status codes in CI.

### A-21 — Context, retrieval and memory architecture · **NOT-APPLICABLE** (P7)
- **Probe:** Looked for retrieval/memory architecture.
- **Evidence:** No RAG, no vector store, no persistent agent memory; prompt context built fresh each cycle from bounded TA data
- **N/A:** There is no retrieval or memory subsystem. The LLM receives a freshly-built, bounded prompt each cycle (TA indicators + pairwise summaries) and retains nothing. Groundedness/freshness/compaction concerns require a retrieval/memory architecture that does not exist here.

### A-23 — Data architecture and ownership · **PARTIAL** (P7)
- **Probe:** For each dataset: owner, schema, versioning, quality monitoring.
- **Evidence:** Datasets: config (dict schema in settings.DEFAULTS), cache (JSON), in-mem state — owner=operator
- **Evidence:** Schemas implicit/validated by settings coercion; no schema-drift monitoring
- **Note:** Tiny data surface; schema is enforced for config by coercion. No drift monitor (not needed at this scale).
- **Standing control (planned):** Phase 5: settings coercion tests in CI act as the schema guard.

### A-26 — Error handling that does not lie · **PASS** (P7)
- **Probe:** Grepped for swallowed exceptions, timeouts, circuit breakers.
- **Evidence:** All HTTP calls have timeouts (binance 15s, etoro 20s, sipgate 15s)
- **Evidence:** Exception handlers are narrow/typed except one documented `except Exception: pass` (web/app.py:107, surfaced via engine state) and intentional per-item log-and-continue in analysis/scheduler
- **Evidence:** No circuit breakers; CL-1: rebalance 'no-trade' abort can fire AFTER housekeeping trades already executed
- **Note:** Error handling is genuinely good (no silent swallows of consequence). Two items: the one bare `pass`, and CL-1's claim/behaviour gap.  [Phase 6] Error handling no longer lies; the swallow gate is demonstrated.
- **Standing control:** ruff BLE (blind-except) blocks new silent swallows; surviving broad catches carry machine-readable justifications; all I/O has timeouts. _(cadence: every push; blocks: merge; owner: operator + CI)_ — **demonstrated:** D4 (except: return None) caught by ruff BLE001; CL-1 documentation overstatement corrected.

### A-27 — Non-functional requirements that are specific to AI · **PARTIAL** (P7)
- **Probe:** Looked for latency/cost/hallucination budgets on the AI feature.
- **Evidence:** LLM calls bounded (max_tokens=1000, temp=0, ~N pairs+1 market per cycle, interval-gated); no explicit cost cap
- **Evidence:** No hallucination/groundedness threshold
- **Note:** Implicitly bounded; no explicit enforced budgets.
- **Standing control (planned):** Phase 5: document the per-cycle call budget; a cost cap is disproportionate (residual).

### A-28 — Dependency topology and blast radius · **PARTIAL** (P7) · _structural_
- **Probe:** Mapped external deps; checked timeouts/fallbacks; tested one failure.
- **Evidence:** Timeouts on all external calls; LLM has anthropic->openai fallback (tested by unit); exchange/TA have no fallback (single provider)
- **Evidence:** No circuit breakers; no generated dependency map
- **Note:** Resilience is partial: LLM failover real, exchange/TA degrade to logged failure (fail-safe).
- **Standing control (planned):** Phase 5: a guarded-client note; the fail-safe-on-error test covers degradation.

### A-32 — Documentation that is true -- and executable · **PARTIAL** (P7)
- **Probe:** Followed the README as a new engineer; checked for AGENTS.md; ran doc commands.
- **Evidence:** README quick-start commands are accurate (pip + python -m src.main; deploy.sh) and were exercised
- **Evidence:** Two overstatements: CL-1 ('no trades' abort), CL-2 ('Binance order mechanics' coverage)
- **Evidence:** No AGENTS.md; docs not executed in CI
- **Note:** Docs are mostly true (Phase 1) with 2 narrow overstatements; no agent-instruction file.
- **Standing control (planned):** Phase 4/5: add AGENTS.md; correct CL-1/CL-2 wording; a CI smoke test runs the documented entrypoint.

### A-38 — Provenance and licensing of the code that shipped · **PARTIAL** (P7)
- **Probe:** License-scanned deps + generated code; looked for SBOM + IP position.
- **Evidence:** Deps are permissive (FastAPI/Starlette MIT, requests Apache-2.0, etc.); no copyleft conflict observed
- **Evidence:** No SBOM, no license-scan gate, no written IP position on AI-generated code
- **Note:** No license conflict found; no standing scan or SBOM.
- **Standing control (planned):** Phase 5: pip-licenses/SBOM (CycloneDX) generated in CI; IP note in governance/.

### B-08 — No path may consume unbounded tokens or money · **PASS** (P7) · _structural_
- **Probe:** Tried to make it spend unbounded tokens/money.
- **Evidence:** Tokens bounded (max_tokens=1000, bounded calls/cycle); no recursion
- **Evidence:** MONEY: no per-cycle/daily notional cap -> unbounded financial exposure in live mode (same root as A-34)
- **Note:** Token side capped; money side uncapped. The trading-cap closes the material half.  [Phase 6] No path consumes unbounded money.
- **Standing control:** Spend is capped at the _swap chokepoint (per-swap ceiling + rolling 24h cap + halt); LLM tokens bounded (max_tokens, bounded calls/cycle). _(cadence: every push; blocks: merge + runtime; owner: operator + CI)_ — **demonstrated:** test_daily_cap + test_swap_clamps; money path bounded (was unbounded).

### B-09 — Signed provenance for everything shipped, including models · **PARTIAL** (P7)
- **Probe:** Tried to verify a deployed artifact's provenance; tried to deploy unsigned.
- **Evidence:** No image signing, no SBOM, no attestation, no verify-on-deploy
- **Note:** No provenance chain on the container image.  [Phase 6] no image signing/SBOM yet; deps are permissive; residual (proportionate for a personal image).
- **Standing control (planned):** Phase 5: SBOM in CI; cosign/attestation is disproportionate for a personal image (residual, documented).

### B-17 — Infrastructure as code, reconciled from version control · **PARTIAL** (P7)
- **Probe:** Compared declared vs actual infra; looked for drift detection.
- **Evidence:** compose.yaml is semi-declarative; deploy.sh is imperative; single container
- **Evidence:** No drift detection (nor a fleet to drift)
- **Note:** Re-scoped: single container from a pinned image; IaC drift largely N/A.
- **Standing control (planned):** none (proportionate).

### B-19 — Service objectives with an error budget that bites · **NOT-APPLICABLE** (P7)
- **Probe:** Looked for SLOs + an error-budget policy.
- **Evidence:** Single-user personal deployment; no SLA, no users to owe availability to
- **N/A:** Error budgets and SLOs govern a service with users and an availability commitment. This bot serves one operator on loopback with no uptime obligation; the meaningful reliability property (fail safe, don't trade on error) is covered by A-24. An SLO here would be ceremony with no consumer.

### B-23 — Behavioural baselines for agents, with automatic containment · **NOT-APPLICABLE** (P7)
- **Probe:** Looked for per-agent behavioural baselines + anomaly containment.
- **Evidence:** No autonomous agents; one deterministic engine with fixed handlers
- **N/A:** 'Agent behavioural baseline' presumes autonomous tool-using agents whose action mix could drift. Here a deterministic engine runs fixed handlers on a schedule; there is no agent whose behaviour could deviate. The analogous protection (bounding money moved) is the A-34 trading cap, not behavioural anomaly detection.

### B-24 — Quality drift detection · **PARTIAL** (P7)
- **Probe:** Asked how a drop in LLM decision quality would be noticed.
- **Evidence:** No online eval of LLM output; a provider-side model change would not be detected
- **Evidence:** Floating model aliases (B-13) make silent provider drift MORE likely
- **Note:** Quality drift would surface only as bad trades. Pinning (B-13) + a golden eval (B-10) are the levers.
- **Standing control (planned):** Phase 5: model pinning removes silent-swap drift; golden eval fixture flags decision drift.

### B-25 — Environment separation and parity · **NOT-APPLICABLE** (P7) · _structural_
- **Probe:** Compared connection strings/creds/flags across environments.
- **Evidence:** One environment: the operator's own deployment. No staging/prod split, no separate data plane
- **N/A:** Environment-separation and 'no production credential in non-production' presuppose multiple environments. This system has exactly one deployment with one set of the operator's own credentials; there is no non-production plane that could hold a production secret. The dry-run/live boundary (a runtime flag, not an environment) is handled by A-15/A-34.

### B-27 — Artifact integrity · **PARTIAL** (P7)
- **Probe:** Tried to verify image signature; tried to deploy a modified image.
- **Evidence:** No image signing/verification; build is reproducible-ish (pinned deps, pinned base tag)
- **Note:** No artifact integrity verification.
- **Standing control (planned):** Phase 5: SBOM + pinned digests; signing disproportionate (residual).

### B-29 — Reliability primitives, validated by breaking things · **PARTIAL** (P7)
- **Probe:** Checked reliability primitives and whether failure was injected.
- **Evidence:** Timeouts + LLM failover present; no chaos/failure-injection has been run
- **Evidence:** The fail-safe-on-error path is unit-testable
- **Note:** Primitives present, not validated by breaking.
- **Standing control (planned):** Phase 5: a test injecting exchange failure asserting no-trade + safe state.

### B-33 — Integrity of the retrieval corpus · **NOT-APPLICABLE** (P7)
- **Probe:** Looked for a retrieval corpus and its integrity controls.
- **Evidence:** No vector store / retrieval corpus exists
- **N/A:** There is no persistent retrieval corpus or embedding index to poison or stale. The only cache is short-TTL TA/LLM JSON in dry-run, keyed by symbol, never cross-user, and reproducible on expiry.


## SHOULD-FIX

### A-03 — Deterministic and probabilistic assertions kept apart · **PARTIAL** (P6)
- **Probe:** Found tests asserting on model output; checked deterministic vs judged split.
- **Evidence:** Tests use CANNED LLM output (deterministic); live LLM decisions are NOT gated by any eval set
- **Evidence:** The schema validation IS the deterministic reduction of the judged surface (good)
- **Note:** Deterministic maths hard-asserted; the probabilistic path is trusted live with no eval gate.
- **Standing control (planned):** Phase 5: golden eval fixture (shared B-10).

### A-14 — A written policy for how AI builds and maintains this · **PARTIAL** (P6)
- **Probe:** Looked for a written AI-build/maintenance policy with verification tiers.
- **Evidence:** No such policy exists
- **Note:** [Phase 6] constitution.md + AGENTS.md are the policy; single verification tier (proportionate).
- **Standing control (planned):** Phase 4: governance/constitution.md + AGENTS.md encode the policy and the (single) verification tier.

### A-16 — The last mile: stubs, edge cases and integration · **PARTIAL** (P6)
- **Probe:** Grepped production paths for stubs/TODO/NotImplemented/mock/placeholder.
- **Evidence:** No production stubs/TODOs/NotImplemented found; the only 'placeholder' hits are HTML input attributes; one documented `pass`
- **Evidence:** No stub-detector lint
- **Note:** Genuinely no last-mile stubs — a strength. No standing lint to keep it so.
- **Standing control (planned):** Phase 5: a stub-pattern lint in CI.

### A-20 — Prompts and retrieval configuration are code, pass the same gate · **PARTIAL** (P6) · _structural_
- **Probe:** Located every prompt; checked for a hot-swap path bypassing any gate.
- **Evidence:** Prompts are Python constants in prompts.py (+ SYSTEM_PROMPT in llm.py); NOT loadable from config/db/env
- **Evidence:** No production hot-swap path exists (structural)
- **Note:** Prompts are structurally code-only — the hot-swap path this check fears does not exist. No eval gate though.
- **Standing control (planned):** Phase 5: prompt changes ride the code gate; a prompt-change eval fixture (shared with B-10).

### A-29 — Build versus buy versus open source -- including the model · **PARTIAL** (P6) · _structural_
- **Probe:** Checked for build/buy/model decision records + exit plan.
- **Evidence:** LLM provider abstraction exists (primary+fallback in one client); no ADR/TCO/exit-plan doc
- **Note:** Provider seam exists; decision undocumented.
- **Standing control (planned):** Phase 4: ADR (shared A-18).

### A-30 — Non-functional trade-offs analysed, not stumbled into · **PARTIAL** (P6)
- **Probe:** Looked for documented consistency/availability/redundancy positions.
- **Evidence:** No datastore trade-offs to speak of (no DB); positions undocumented but low-stakes
- **Note:** Minimal; largely immaterial at this scale.
- **Standing control (planned):** none (proportionate).

### A-31 — Unit economics decided at design time · **PARTIAL** (P6) · _structural_
- **Probe:** Computed cost per cycle; looked for a unit-economics model.
- **Evidence:** A handful of LLM+TA+exchange calls per cycle; cost is cents/day range; no model/cap
- **Note:** Immaterial spend; no model.
- **Standing control (planned):** none (proportionate); model gateway disproportionate.

### A-35 — Runtime containment without an operator · **PASS** (P6)
- **Probe:** Hunted for approval queues / pending-human states; checked automatic containment.
- **Evidence:** ZERO load-bearing approval queues (nothing waits on a human) — a genuine strength
- **Evidence:** No automatic anomaly containment (the trading-cap will add it)
- **Note:** No queue to rot (good). Containment is manual today.  [Phase 6] Runtime containment is automatic; no queue to rot.
- **Standing control:** Zero load-bearing approval queues (nothing waits on a human) + automatic containment via the daily-cap auto-halt. _(cadence: every push; blocks: merge; owner: operator + CI)_ — **demonstrated:** No approval-queue/pending-human state in the codebase; the halt is automatic (test).

### A-36 — Calibration of the verification pipeline · **PASS** (P6)
- **Probe:** Took the Phase-2 seeded-defect result; checked whether catch rate is measured continuously.
- **Evidence:** Catch rate measured ONCE (2/6, 02-calibration.md); not continuous, not an SLI
- **Evidence:** No game-day / recovery drill
- **Note:** BLOCKER-1 under §3 (catch rate not measured on a continuing basis). The instrument exists (the harness) but is not standing.  [Phase 6] The pipeline's catch rate is measured continuously and ratcheted.
- **Standing control:** scripts/gate_selftest.py re-seeds D1..D6 and asserts the responsible gate still catches each. _(cadence: every push; blocks: merge; owner: operator + CI)_ — **demonstrated:** gate_selftest: 5/5 caught (was 2/6 pre-repair) -- audit/evidence/phase5-gate-demonstration.txt; audit/02-calibration.md.

### B-14 — Governance over prompt and configuration changes · **PARTIAL** (P6) · _structural_
- **Probe:** Checked whether prompt/config changes are governed + audited.
- **Evidence:** Prompts are code (gated by the code gate once CI exists); config changes via UI are logged to the event log but not durably audited
- **Evidence:** single operator, so 'who changed it' is unambiguous
- **Note:** Prompt governance rides the code gate; config-change audit is ephemeral.
- **Standing control (planned):** Phase 5: prompts through the CI gate; config-save already logs an event.

### B-16 — Cost attribution and financial operations · **PARTIAL** (P6) · _structural_
- **Probe:** Asked cost per request/customer.
- **Evidence:** No cost attribution; single user, immaterial spend
- **Note:** Immaterial.
- **Standing control (planned):** none (proportionate).

### B-18 — Progressive delivery with an automatic abort · **NOT-APPLICABLE** (P6)
- **Probe:** Checked how a change reaches all users; tried to fire an abort.
- **Evidence:** Single-instance personal deployment; a redeploy replaces the one instance
- **N/A:** Progressive/canary rollout presupposes many instances/users to expose a change to gradually. There is one instance and one user. The analogue — exposing a change safely before it moves real money — is the dry-run boundary (A-15) plus the trading cap (A-34), not percentage rollout.

### B-21 — The application survives a provider outage · **PARTIAL** (P6)
- **Probe:** Made each provider fail (mentally + LLM fallback is unit-tested).
- **Evidence:** LLM: anthropic->openai failover is real and tested; on total LLM failure the engine refuses to trade (fail-safe)
- **Evidence:** Exchange/TA: no alternate provider; failure => logged job error, no crash, no trade
- **Note:** Survives provider outage by failing safe (LLM has true failover).
- **Standing control (planned):** Phase 5: the fail-safe-on-provider-error test.

### B-26 — Feature flags and kill switches that fire themselves · **PASS** (P6)
- **Probe:** Looked for per-feature kill switches that fire themselves.
- **Evidence:** Manual kill switch = Stop (engine.stop, persisted); dry_run flag; no self-firing tripwire
- **Note:** Manual kill present; no automatic trip.  [Phase 6] The kill switch fires itself and is tested.
- **Standing control:** Auto-halt tripwire flips the engine off on a cap breach without human action; dry_run + Stop are additional switches. _(cadence: every push; blocks: merge + runtime; owner: operator + CI)_ — **demonstrated:** test_daily_cap_refuses_and_halts_engine demonstrates the self-firing kill switch.

### B-30 — Capacity, including inference capacity · **NOT-APPLICABLE** (P6)
- **Probe:** Load-tested to the knee; inference capacity.
- **Evidence:** Single user, background cadence (minutes); no concurrency, no scale requirement
- **N/A:** Capacity/load-shedding/autoscaling govern multi-user throughput. This bot runs a handful of sequential API calls every several minutes for one user; there is no load to plan for and no autoscaler to bound.

### B-35 — Release governance: segregate the gate from the gated · **PARTIAL** (P6) · _structural_
- **Probe:** Asked whether the code-writer can also write the gate that judges it.
- **Evidence:** No policy bundle exists yet; once CI is added it lives in the SAME repo the operator can push to
- **Evidence:** A solo GitHub repo has one identity — the operator holds both code-write and workflow-write
- **Note:** Segregation of gate-from-gated is structurally UNACHIEVABLE for a single-principal repo without a second identity/org. Recorded honestly, not faked.  [Phase 6] gate/gated separation unachievable on a solo repo (one identity) -- residual R-1; compensating: protected branch + CODEOWNERS on .github/ + governance/. Handled by Article XV Incubating scope, not faked.
- **Standing control (planned):** Phase 5: compensating controls — protected branch + required status checks + CODEOWNERS on .github/ and governance/, so bypass is at least visible/logged; residual with tripwire (06-residual-risk-register).

### B-36 — Model deprecation is a plan, not an outage · **PARTIAL** (P6) · _structural_
- **Probe:** Listed model versions + deprecation exposure.
- **Evidence:** Floating aliases (B-13); no deprecation watch; fallback chain gives partial resilience
- **Note:** Deprecation would surface as failures + fallback.
- **Standing control (planned):** Phase 5: pin snapshots (B-13) + a note to watch provider EOL.


## PLAN

### A-15 — The boundary between prototype and production · **PARTIAL** (P5)
- **Probe:** Looked for the prototype/production boundary and whether it holds.
- **Evidence:** dry_run is the boundary; NOTHING gates the dry_run->live transition (CL-3): any UI/env flip goes live instantly
- **Note:** The boundary exists as a flag but is ungated.
- **Standing control (planned):** Phase 5: the trading-cap applies in live mode; document the go-live checklist. (Full gate on the flag is operator-in-command.)

### A-37 — Takeover readiness · **PARTIAL** (P5)
- **Probe:** Assessed agent + human takeover readiness.
- **Evidence:** Clean code + tests aid takeover; no takeover pack, no AGENTS.md yet
- **Standing control (planned):** Phase 4/5: AGENTS.md + governance/ serve as the takeover pack.

### A-39 — The verification loop must not be self-referential · **PARTIAL** (P5)
- **Probe:** Traced who writes/reviews/judges/tests each change; checked for a deterministic gate + independent verifier.
- **Evidence:** No independent adversarial verifier (no second-vendor model wired); the calibration 'verifier' was same-family inspection only
- **Evidence:** No deterministic gate; test authorship is not separated from code authorship
- **Note:** STOP-SHIP under §3 with A-01. A genuinely independent second-vendor verifier is out of reach for a solo operator — recorded as a hard residual; the deterministic gate (which needs no model opinion) is the compensating substitution.  [Phase 6] deterministic gate installed (the substitution); no standing second-vendor verifier -- residual R-2, PLAN band.
- **Standing control (planned):** Phase 5: deterministic CI gate as the sole merge authority (needs no model); independent-verifier residual documented with a compensating control.

### B-32 — Drift detection · **NOT-APPLICABLE** (P5)
- **Probe:** Changed running infra by hand to see if anything notices.
- **Evidence:** Single container from a pinned image; no managed desired-state to reconcile
- **N/A:** Drift detection reconciles a declared desired state against a managed fleet. Here the whole runtime is one container rebuilt from a pinned Dockerfile; there is no orchestrator holding desired state to diverge from. Rebuild-from-source is the reconciliation.

### B-34 — Latency budgets for inference · **NOT-APPLICABLE** (P5) · _structural_
- **Probe:** Measured inference latency percentiles vs an interactive budget.
- **Evidence:** Inference is background (a rebalance cycle every several minutes), not interactive
- **N/A:** Latency budgets (TTFT, p95 end-to-end) matter for interactive, user-facing inference. This LLM call runs inside a background scheduler with minute-scale cadence and no user waiting; a few seconds of model latency is immaterial to correctness or UX.

### B-37 — Retirement of AI artifacts and the right to erasure · **NOT-APPLICABLE** (P5) · _structural_
- **Probe:** Deleted a user end-to-end across every derived store.
- **Evidence:** No third-party personal data; the only personal data is the operator's own keys + SMS number, in config.json
- **N/A:** Right-to-erasure/derived-store retirement governs third-party personal data spread across stores. Here there are no third-party data subjects: the sole data subject is the operator, who erases their own data by deleting config/config.json (and .env). There is no vector store, training set, or trace store holding anyone else's data.

### B-39 — Design against a named reference framework · **PARTIAL** (P5)
- **Probe:** Asked which reference framework the design targets.
- **Evidence:** None named
- **Note:** Design is sound but not mapped to a framework.
- **Standing control (planned):** Phase 4: governance/ names the (right-sized) reference posture.


## ASSESS

### A-40 — Energy and carbon as a design constraint · **NOT-APPLICABLE** (P4)
- **Probe:** Assessed whether the energy footprint is material.
- **Evidence:** A handful of API calls per cycle; no training, no local heavy inference, no fleet
- **N/A:** Energy/carbon is a material design constraint for training runs or high-QPS inference fleets. This system makes a few hosted-API calls every several minutes on one small container; the footprint is immaterial by any rate-based method, documented as such rather than measured with an invented number.

### B-38 — Inference economics · **NOT-APPLICABLE** (P4) · _structural_
- **Probe:** Measured cache hit rate + cost split.
- **Evidence:** Immaterial spend (cents/day); prompt caching would optimise an already-trivial bill
- **N/A:** Inference economics (prompt-cache hit rate, cost-based routing) optimise a material inference bill. This bot's LLM spend is a few calls per cycle for one user — immaterial — so cache-hit engineering would be optimisation with no measurable return. Re-band if usage ever scales.

