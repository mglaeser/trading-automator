#!/usr/bin/env python3
"""Merge Phase-3 verdicts into audit/03-findings.json and render 03-findings.md.

Idempotent: reads the catalogue for authoritative id/title/priority/band, applies
the verdict table below, preserves any fields already present, and validates the
fail-closed invariants from mandate §5. Re-run after Phase 6 edits.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
AUDIT = ROOT / "audit"
cat = json.loads((AUDIT / "00-check-catalogue.json").read_text())
CHECKS = {c["id"]: c for c in cat["checks"]}

# Phase-3 baseline verdicts against commit 840e4f4. standing_control is null at
# baseline for every record (no standing controls exist pre-Phase-5); Phase 6
# updates the records whose controls were installed and demonstrated.
# v = verdict, p = probe (one line), e = evidence list, n = note/impact,
# na = na_justification, scp = standing-control plan (baseline).
V = {
 # ================= STOP-SHIP band (v1.0) =================
 "B-06": dict(v="PARTIAL",
   p="Scanned all 4 commits' blobs + client bundle + env files for secrets; inspected at-rest storage and identity model.",
   e=["audit/evidence/b06-history-scan.txt: zero committed secrets across all history",
      ".gitignore excludes .env and config/config.json; config.json absent on disk",
      "settings.py: secrets stored PLAINTEXT in config/config.json; no vault, no rotation, no expiry",
      "No secret-scanning gate exists (calibration D1 MISSED, 02-calibration.md)"],
   n="The STOP-SHIP hazard (a committed long-lived secret) is ABSENT — history is clean. What is open: (1) no standing secret-scan gate, so a future leak is uncaught; (2) plaintext long-lived keys at rest, no rotation. Not PASS because nothing holds it. Out-of-repo: the credentials pasted in the original chat must be rotated at their providers.",
   scp="Phase 5: secret-scan (detect-secrets/gitleaks-style) in CI, head every push + full history, fail closed."),

 # ================= BLOCKER-1 band (v1.0) =================
 "A-01": dict(v="FAIL",
   p="Looked for a deterministic policy gate / branch protection / required checks; tried to find any automated block on merge.",
   e=[".github/ absent — no CI, no branch protection, no required status checks",
      "Merges reach the branch by direct `git push`; nothing runs the 38-test suite automatically",
      "Calibration: pipeline catches 2/6 seeded defects (02-calibration.md)"],
   n="STOP-SHIP under §3: with A-39 (no independent verifier) also failing, NEITHER a human NOR a machine independently verifies any line of production code. This voids every other PASS in the volume until fixed.",
   scp="Phase 5: GitHub Actions gate (tests+lint+dep-existence+secret-scan+mutation-on-core) + scripts/policy_gate.py failing closed on engagement-status.json."),
 "A-02": dict(v="FAIL",
   p="Ran the suite clean (38 passed), then seeded a swallowed exception (D4) and a vacuous test (D5) and re-ran.",
   e=["D4 (swallowed order exception) MISSED — suite stayed green",
      "D5 (vacuous assertion) MISSED — suite grew to 39 passed",
      "No mutation testing configured anywhere in the repo"],
   n="STOP-SHIP under §3: the suite cannot detect injected faults, so a green build means nothing. The engine's decision logic is fairly pure (functional-core/shell largely already holds), so mutation is reachable.",
   scp="Phase 5: mutmut/cosmic-ray on src/engine.py + src/llm.py core, blocking gate; re-run D5's class must be caught."),
 "A-06": dict(v="FAIL",
   p="Plotted commit sizes/branch lifetime; looked for an executed, timed rollback and an automatic abort.",
   e=["4 commits; the first is a large rebuild (not atomic) — no batch-size gate",
      "No rollback has been executed/timed; no automatic abort wired to any signal",
      "deploy.sh update rebuilds forward only; rollback would be manual git+redeploy"],
   n="A rollback PATH exists (redeploy a prior commit/image) but is untested and human-triggered. No CI on push.",
   scp="Phase 5: CI on every push; document+the rollback runbook; batch-size advisory. Full auto-abort is out of reach for a single-instance deploy (residual)."),
 "A-08": dict(v="FAIL",
   p="Looked for SAST/DAST/SCA/secret scanning wired as blocking gates; seeded a credential (D1) and a bad dependency (D3).",
   e=["No static analysis, dependency scanning, or secret scanning in any gate",
      "D1 (hard-coded credential) and D3 (non-existent dependency) both MISSED"],
   n="Security scanning is the control here, and it does not exist. Highest-yield gap alongside A-01/B-04.",
   scp="Phase 5: ruff (incl. security lints), pip-audit (SCA), secret-scan, dependency-existence — all blocking in CI, each calibrated against its seed."),
 "A-24": dict(v="PARTIAL",
   p="Induced failure modes mentally + checked recovery: healthcheck, restart policy, SLOs, incident->test.",
   e=["Dockerfile HEALTHCHECK + --restart=always give automatic container restart",
      "engine._run_job fails SAFE: on any job error it logs, records state, and does NOT trade; rebalance failure sends SMS",
      "No SLO/error-budget, no auto-rollback, no incident->regression-test discipline"],
   n="Fails safe (no trade on error) and self-restarts, which is the meaningful recovery for a personal bot. Missing: SLOs, auto-recovery coverage metric.",
   scp="Phase 5: document the fail-safe invariant as a test; SLO/error-budget out of scope for single-user (residual)."),
 "B-01": dict(v="FAIL",
   p="Looked for a pipeline that blocks; grepped for soft-fail constructs.",
   e=[".github/ absent — there is no pipeline to gate or soft-fail",
      "The 38-test suite is the entire safety net and nothing runs it automatically"],
   n="Sibling of A-01. The pipeline is not a weak safety net — it does not exist.",
   scp="Phase 5: the CI gate IS this control; weekly synthetic red-push proves it still blocks."),
 "B-03": dict(v="PARTIAL",
   p="Tried to follow one request end-to-end through logs/metrics/traces.",
   e=["logging configured (main.py) + structured in-memory event log (state.py, <=300 events)",
      "No traces, no metrics, no request IDs, no OpenTelemetry"],
   n="For a single-user bot the logs + event log reach root cause for the common cases; no distributed tracing (nor needed). Re-scoped from enterprise observability.",
   scp="Phase 5: none added (proportionate); documented as accepted for repo class."),
 "B-04": dict(v="PARTIAL",
   p="Enumerated all 9 runtime deps; resolved each against the index; checked pinning; seeded a fake package (D3).",
   e=["All 9 pinned to exact versions and ALL resolve on the index (probe in Phase 3 log): fastapi,uvicorn,requests,tradingview-ta,anthropic,openai,astral,pytz,python-dotenv",
      "No hash pinning (no lockfile); no existence/SCA gate — D3 MISSED"],
   n="No hallucinated or unpinned package is present. The gap is the missing GATE: nothing stops a future slopsquat/unpinned add.",
   scp="Phase 5: scripts/check_deps.py (existence + pin) + pip-audit, blocking; monthly fabricated-name seed must be blocked."),
 "B-11": dict(v="PARTIAL",
   p="Checked rollback for code, prompts, models and whether it can fire on a signal.",
   e=["Code/prompt/model are all in-repo, so rollback = git revert + redeploy (untested, manual)",
      "Models are FLOATING aliases (B-13), so there is no pinned version to roll back TO"],
   n="Rollback is a manual redeploy; prompts roll back with code; model rollback is undermined by floating aliases.",
   scp="Phase 5: pin model snapshots (B-13) so a model rollback target exists; document the redeploy rollback."),
 "B-20": dict(v="PARTIAL",
   p="Traced every path by which model output or retrieved text could egress data; attempted to construct the exfil channel.",
   e=["The LLM has NO tools, NO outbound capability — it returns schema-validated JSON only (llm.py)",
      "The egress allowlist is fixed in code (6 destinations); the model cannot add one",
      "No runtime exfil detection exists — but the channel it would detect does not exist"],
   n="Strong architectural containment: the exfiltration leg is structurally absent (the model cannot act or egress). No runtime detector, and none is load-bearing here.",
   scp="Phase 5: a test asserting the model-output path cannot reach any network call (structural invariant); documented."),
 "B-22": dict(v="PARTIAL",
   p="Enumerated the process's privileges and whether they are least and enforced.",
   e=["Single process, single principal (operator's keys); no per-agent identities",
      "README advises no-withdrawal + IP-pinned exchange keys; not enforceable in code (exchange-side scope)",
      "Key scope is deny-by-default only if the operator sets it so at the exchange"],
   n="Re-scoped: there are no autonomous agents to privilege-separate. The meaningful least-privilege is the exchange key scope, which is documented but exchange-side.",
   scp="Phase 5: a startup check that warns if withdrawal-capable keys are detectable via test_connection permissions; document."),
 "A-36": dict(v="PARTIAL",
   p="Took the Phase-2 seeded-defect result; checked whether catch rate is measured continuously.",
   e=["Catch rate measured ONCE (2/6, 02-calibration.md); not continuous, not an SLI",
      "No game-day / recovery drill"],
   n="BLOCKER-1 under §3 (catch rate not measured on a continuing basis). The instrument exists (the harness) but is not standing.",
   scp="Phase 5: calibration harness becomes a scheduled CI job; catch-rate ratcheted, a drop fails the build."),

 # ================= BLOCKER-2 band (v1.0) =================
 "A-04": dict(v="FAIL",
   p="Looked for testable acceptance criteria, explicit non-goals, and a spec-coverage gate.",
   e=["No spec/acceptance-criteria/non-goals artifact exists; README+tests are the de-facto spec",
      "No spec-coverage gate; a change mapping to no criterion can merge freely"],
   n="Intent lives only in prose + tests. The frozen spec that §1 makes the sole channel of human intent is absent.",
   scp="Phase 4/5: write governance/spec.md (invariants as executable acceptance) + tie the safety invariants to named tests."),
 "A-09": dict(v="PARTIAL",
   p="Tested the decomposition; looked for ADRs and fitness functions.",
   e=["Clean layering: exchanges/ (adapters behind ABC), web/ (API), engine/llm/analysis/scheduler separated",
      "No ADRs; no architecture fitness function enforcing boundaries"],
   n="Architecture is genuinely decided, not accreted — but nothing enforces it stays that way.",
   scp="Phase 5: an import-boundary lint (ruff isort/flake8-tidy-imports) asserting web/ and exchanges/ never import engine internals; ADR for the exchange-abstraction decision."),
 "A-10": dict(v="PARTIAL",
   p="Traced untrusted text (TradingView data, LLM output) to any consequential action; attempted to make it act.",
   e=["LLM output is schema-validated to a fixed action space (llm.py:126-131); off-schema => no trade",
      "The LLM cannot call tools; the engine (deterministic) executes trades from validated JSON only",
      "No injection test corpus"],
   n="Injection containment is ARCHITECTURAL and real: a successful injection cannot exceed {sell_buy,buy,sell,hold} on configured assets with clamped confidence. This is a strength.",
   scp="Phase 5: an injection test (adversarial LLM output) asserting no out-of-schema action ever reaches a swap; runs in CI."),
 "A-17": dict(v="FAIL",
   p="Looked for an NFR table across the nine quality characteristics with measures.",
   e=["No NFR specification exists"],
   n="NFRs are implicit. For a personal bot most are low-stakes, but safety/security NFRs of an AI money-mover deserve explicit measures.",
   scp="Phase 4: governance/spec.md records the prioritised NFRs (safety, security, reliability) with the tests that measure them."),
 "A-22": dict(v="NOT-APPLICABLE",
   p="Assessed against public-service accessibility/RUM obligations.",
   e=["Single-operator internal dashboard bound to 127.0.0.1; not a public service"],
   n="", na="WCAG-AA-as-legal-obligation and Core-Web-Vitals RUM target public/consumer services. This is a private single-user localhost dashboard with no external users, so the public-accessibility framing does not bind. Basic usability is adequate (simple, escaped HTML). The one real 'user outcome' (P&L) is noted as untracked under A-24/A-27, not here.",
   scp="n/a"),
 "A-25": dict(v="PARTIAL",
   p="Enumerated entry points and checked server-side validation; treated TA/LLM as untrusted input.",
   e=["PUT /api/config coerces+drops bad types (settings.update); run_job validates job in JOBS; index.html escapes all innerHTML interpolation (esc())",
      "LLM output schema-validated; exchange responses parsed defensively",
      "No auth on the mutating boundary (PUT /api/config, engine/start) — any local process can drive it",
      "No property/fuzz tests on parsers (_parse_json, settings coercion)"],
   n="Validation is present at the important boundaries; the gaps are (a) no authn on state-changing routes (mitigated by loopback bind, feeds C-01/Part 2) and (b) no fuzz tests.",
   scp="Phase 5: property tests on _parse_json and settings._coerce in CI."),
 "A-33": dict(v="PARTIAL",
   p="Asked whether a cold-start agent could safely change this from the repo alone; assessed artifacts.",
   e=["Clean, documented, tested code; strong docstrings stating invariants",
      "No AGENTS.md; no per-module spec/provenance link; no cold-start-agent test"],
   n="Maintainability is good for a human; the machine-maintainability artifacts (agent instructions, spec links) are thin.",
   scp="Phase 4/5: add AGENTS.md + governance/spec.md so a cold agent has the invariants; the CI gate becomes the safety net a cold agent leans on."),
 "A-34": dict(v="PARTIAL",
   p="For each action class checked reversibility, a deterministic validator, a blast-radius cap, an automatic tripwire; pulled the kill switch.",
   e=["Live trades are IRREVERSIBLE; validators present: notional pre-check, LOT_SIZE, free-balance clamp, universe restriction, sells-before-buys",
      "MISSING: any blast-radius cap (no per-cycle/daily notional limit, no max trades, no loss limit) and any AUTOMATIC halt",
      "Kill switch = manual Stop (engine.stop()); no tripwire fires it"],
   n="The single most material product finding: an irreversible real-money capability with partial validators but NO blast-radius cap and NO self-firing halt. Drives the Phase-5 trading cap.",
   scp="Phase 5: a deterministic per-cycle + rolling-window notional cap and a trade-count/error tripwire that auto-halts (engine.stop) and latches; tests prove it blocks."),
 "B-02": dict(v="PARTIAL",
   p="Cloned-clean bootstrap: pip install -r requirements-dev.txt + python -m src.main; also deploy.sh.",
   e=["One-command bootstrap works (deploy.sh; or pip + python -m src.main)",
      "No cold-start-AGENT walk; no AGENTS.md"],
   n="Paved road exists for a human; not proven for a cold agent.",
   scp="Phase 5: AGENTS.md documents the paved road; CI bootstraps from a clean checkout on every run (proves it)."),
 "B-05": dict(v="PARTIAL",
   p="Looked for a model/prompt/agent registry with versioning + rollback.",
   e=["Prompts are versioned as code (prompts.py); models pinned in settings but as floating aliases (B-13)",
      "No registry; no eval history"],
   n="Lifecycle is 'whatever is in code + settings'. Prompts are structurally un-hot-swappable (code constants) which is good.",
   scp="Phase 5: model pinning (B-13); prompt-change eval note. Full registry disproportionate for 2 prompts (residual)."),
 "B-07": dict(v="PARTIAL",
   p="Tried to reconstruct one LLM interaction: model, version, prompt, output, tokens, cost.",
   e=["llm.py logs provider + action + confidence; cache stores the raw response (dry-run)",
      "Not recorded: prompt hash, token counts, cost, exact model snapshot"],
   n="Partial replayability. For a personal bot the cache + logs are usually enough; provenance fields are thin.",
   scp="Phase 5: log model id + prompt hash + token usage at each call (one typed emit point in llm.py)."),
 "B-10": dict(v="FAIL",
   p="Looked for a golden/eval dataset gating prompt/model changes; checked for a backtest.",
   e=["No golden dataset, no regression eval, no backtest harness for the LLM trading decisions"],
   n="The LLM's trading judgement ships with no offline evaluation. Notable for a money-mover — a prompt/model change cannot be regression-tested.",
   scp="Phase 5: a small golden-fixture eval (canned TA -> asserted action distribution) as a CI check; structural held-out-store disproportionate (residual)."),
 "B-12": dict(v="PARTIAL",
   p="Checked runtime defence + patch cadence.",
   e=["Localhost bind is the network defence (no WAF needed for loopback); python:3.12-slim base + pinned deps",
      "No automated base-image/dependency patch cadence"],
   n="Re-scoped: WAF N/A for a loopback single-user UI. Patch cadence is unmanaged.",
   scp="Phase 5: pip-audit in CI flags vulnerable deps; Dependabot-style note in AGENTS.md."),
 "B-13": dict(v="FAIL",
   p="Grepped model identifiers in settings for floating vs dated snapshots.",
   e=["settings.py DEFAULTS: anthropic_model='claude-sonnet-5', openai_model='gpt-4o-mini' — both FLOATING aliases, not dated immutable snapshots",
      "No CI check forbidding unpinned model references"],
   n="A floating alias means provider-side model migration changes behaviour while the code does not — the one failure class no review would catch. Concrete, one-class fix.",
   scp="Phase 5: default to dated snapshots where available + a lint (scripts/check_model_pins.py) failing on alias-style ids; drift scan of running config."),
 "B-15": dict(v="PARTIAL",
   p="Turned the 'guardrail' off: fed malformed/oversized LLM output and confirmed behaviour.",
   e=["The guardrail here = LLM-output schema validation; it FAILS CLOSED (bad output -> {'error'} -> no trade), verified by tests",
      "No separate guardrail service to kill; no adversarial corpus"],
   n="Fail-closed validation is real and tested — a genuine strength. There is no fail-open path from bad model output to a trade.",
   scp="Phase 5: keep the validation tests in the CI gate; add an adversarial-output test (garbage/oversized/injection)."),
 "B-28": dict(v="PARTIAL",
   p="Checked whether detection triggers action or only notifies.",
   e=["SMS alerts on repay + rebalance failure (notification); the engine itself auto-responds by NOT trading on error (fail-safe)",
      "No automated remediation beyond fail-safe + restart"],
   n="The consequential auto-response (don't trade on bad signal) exists structurally; alerts are notifications on top.",
   scp="Phase 5: the trading-cap tripwire (A-34) is the automated response that halts on anomaly."),
 "B-31": dict(v="PARTIAL",
   p="Identified durable state and whether a restore was ever performed.",
   e=["Only durable state is config/config.json (keys) + optional .env; EngineState is ephemeral by design",
      "No backup/restore drill; config is re-enterable via the UI"],
   n="Minimal durable state; restore = re-enter keys or copy config.json. Low stakes, but no documented procedure.",
   scp="Phase 5: document config backup in AGENTS.md; no automated restore drill (proportionate residual)."),

 # ================= MUST-FIX band (v1.0) =================
 "A-05": dict(v="PARTIAL", p="Mapped modules for a shared vocabulary and enforced boundaries.",
   e=["Consistent domain vocabulary (asset/quote/anchor/swap/balance); one owning role (operator)",
      "Boundaries by convention only — no import linter"],
   n="Clean boundaries, not enforced.", scp="Phase 5: import-boundary lint (shared with A-09)."),
 "A-07": dict(v="PARTIAL", p="Scanned for duplicated blocks/churn; looked for a clone gate.",
   e=["140 defs/classes across 15 modules; code is notably DRY (shared base ABC, helpers reused)",
      "No clone detector / duplication tripwire in CI"],
   n="Low duplication observed; no standing tripwire to keep it low.", scp="Phase 5: ruff + a duplication note; full clone detector disproportionate."),
 "A-11": dict(v="PARTIAL", p="Enumerated every capability the model/engine can reach and its reversibility.",
   e=["Model: zero tools (cannot act). Engine: exchange trade calls (irreversible) with notional/balance/universe validators",
      "No blast-radius cap; no dry-run diff -> apply -> compensate wrapper"],
   n="Least-privilege on the MODEL is total (no tools). The engine's irreversible capability lacks a cap — same root as A-34.",
   scp="Phase 5: the trading-cap (A-34) is the shared fix; documents the irreversibility table."),
 "A-12": dict(v="PARTIAL", p="Looked for dead code and per-module reconstructibility.",
   e=["No dead/unreached modules found; every module is imported and exercised",
      "No per-module spec-link/provenance record"],
   n="No deletion needed (tight codebase). Reconstructibility artifacts thin.", scp="Phase 4: spec.md links invariants to modules."),
 "A-13": dict(v="FAIL", p="Checked for lint/format/static analysis blocking in CI.",
   e=["No linter, formatter, or static analysis configured; no pyproject.toml"],
   n="No enforced standards.", scp="Phase 5: ruff (lint+format) blocking in CI with a suppression counter."),
 "A-18": dict(v="PARTIAL", p="Asked why single-LLM + fallback; checked context budget.",
   e=["Documented rationale in llm.py docstring (primary+fallback, cooldown); context is small/bounded per cycle",
      "No ADR"],
   n="Deliberate and simple; no ADR artifact.", scp="Phase 4: ADR for the LLM-advisor architecture."),
 "A-19": dict(v="PARTIAL", p="Diffed FastAPI-generated OpenAPI against reality; checked idempotency/errors.",
   e=["FastAPI auto-generates the schema from handlers (matches by construction); single consumer = bundled UI",
      "No contract test; errors are ad hoc (HTTPException + JSONResponse)"],
   n="Contract drift is low-risk (one in-repo consumer, generated schema). No standing contract test.",
   scp="Phase 5: a smoke test asserting the route set + status codes in CI."),
 "A-20": dict(v="PARTIAL", p="Located every prompt; checked for a hot-swap path bypassing any gate.",
   e=["Prompts are Python constants in prompts.py (+ SYSTEM_PROMPT in llm.py); NOT loadable from config/db/env",
      "No production hot-swap path exists (structural)"],
   n="Prompts are structurally code-only — the hot-swap path this check fears does not exist. No eval gate though.",
   scp="Phase 5: prompt changes ride the code gate; a prompt-change eval fixture (shared with B-10)."),
 "A-21": dict(v="NOT-APPLICABLE", p="Looked for retrieval/memory architecture.",
   e=["No RAG, no vector store, no persistent agent memory; prompt context built fresh each cycle from bounded TA data"],
   n="", na="There is no retrieval or memory subsystem. The LLM receives a freshly-built, bounded prompt each cycle (TA indicators + pairwise summaries) and retains nothing. Groundedness/freshness/compaction concerns require a retrieval/memory architecture that does not exist here.", scp="n/a"),
 "A-23": dict(v="PARTIAL", p="For each dataset: owner, schema, versioning, quality monitoring.",
   e=["Datasets: config (dict schema in settings.DEFAULTS), cache (JSON), in-mem state — owner=operator",
      "Schemas implicit/validated by settings coercion; no schema-drift monitoring"],
   n="Tiny data surface; schema is enforced for config by coercion. No drift monitor (not needed at this scale).",
   scp="Phase 5: settings coercion tests in CI act as the schema guard."),
 "A-26": dict(v="PARTIAL", p="Grepped for swallowed exceptions, timeouts, circuit breakers.",
   e=["All HTTP calls have timeouts (binance 15s, etoro 20s, sipgate 15s)",
      "Exception handlers are narrow/typed except one documented `except Exception: pass` (web/app.py:107, surfaced via engine state) and intentional per-item log-and-continue in analysis/scheduler",
      "No circuit breakers; CL-1: rebalance 'no-trade' abort can fire AFTER housekeeping trades already executed"],
   n="Error handling is genuinely good (no silent swallows of consequence). Two items: the one bare `pass`, and CL-1's claim/behaviour gap.",
   scp="Phase 5: a broad-except lint (ruff BLE) with justification annotations; fix CL-1 wording/ordering."),
 "A-27": dict(v="PARTIAL", p="Looked for latency/cost/hallucination budgets on the AI feature.",
   e=["LLM calls bounded (max_tokens=1000, temp=0, ~N pairs+1 market per cycle, interval-gated); no explicit cost cap",
      "No hallucination/groundedness threshold"],
   n="Implicitly bounded; no explicit enforced budgets.", scp="Phase 5: document the per-cycle call budget; a cost cap is disproportionate (residual)."),
 "A-28": dict(v="PARTIAL", p="Mapped external deps; checked timeouts/fallbacks; tested one failure.",
   e=["Timeouts on all external calls; LLM has anthropic->openai fallback (tested by unit); exchange/TA have no fallback (single provider)",
      "No circuit breakers; no generated dependency map"],
   n="Resilience is partial: LLM failover real, exchange/TA degrade to logged failure (fail-safe).",
   scp="Phase 5: a guarded-client note; the fail-safe-on-error test covers degradation."),
 "A-32": dict(v="PARTIAL", p="Followed the README as a new engineer; checked for AGENTS.md; ran doc commands.",
   e=["README quick-start commands are accurate (pip + python -m src.main; deploy.sh) and were exercised",
      "Two overstatements: CL-1 ('no trades' abort), CL-2 ('Binance order mechanics' coverage)",
      "No AGENTS.md; docs not executed in CI"],
   n="Docs are mostly true (Phase 1) with 2 narrow overstatements; no agent-instruction file.",
   scp="Phase 4/5: add AGENTS.md; correct CL-1/CL-2 wording; a CI smoke test runs the documented entrypoint."),
 "A-38": dict(v="PARTIAL", p="License-scanned deps + generated code; looked for SBOM + IP position.",
   e=["Deps are permissive (FastAPI/Starlette MIT, requests Apache-2.0, etc.); no copyleft conflict observed",
      "No SBOM, no license-scan gate, no written IP position on AI-generated code"],
   n="No license conflict found; no standing scan or SBOM.", scp="Phase 5: pip-licenses/SBOM (CycloneDX) generated in CI; IP note in governance/."),
 "B-08": dict(v="PARTIAL", p="Tried to make it spend unbounded tokens/money.",
   e=["Tokens bounded (max_tokens=1000, bounded calls/cycle); no recursion",
      "MONEY: no per-cycle/daily notional cap -> unbounded financial exposure in live mode (same root as A-34)"],
   n="Token side capped; money side uncapped. The trading-cap closes the material half.", scp="Phase 5: trading blast-radius cap (A-34)."),
 "B-09": dict(v="FAIL", p="Tried to verify a deployed artifact's provenance; tried to deploy unsigned.",
   e=["No image signing, no SBOM, no attestation, no verify-on-deploy"],
   n="No provenance chain on the container image.", scp="Phase 5: SBOM in CI; cosign/attestation is disproportionate for a personal image (residual, documented)."),
 "B-17": dict(v="PARTIAL", p="Compared declared vs actual infra; looked for drift detection.",
   e=["compose.yaml is semi-declarative; deploy.sh is imperative; single container",
      "No drift detection (nor a fleet to drift)"],
   n="Re-scoped: single container from a pinned image; IaC drift largely N/A.", scp="none (proportionate)."),
 "B-19": dict(v="NOT-APPLICABLE", p="Looked for SLOs + an error-budget policy.",
   e=["Single-user personal deployment; no SLA, no users to owe availability to"],
   n="", na="Error budgets and SLOs govern a service with users and an availability commitment. This bot serves one operator on loopback with no uptime obligation; the meaningful reliability property (fail safe, don't trade on error) is covered by A-24. An SLO here would be ceremony with no consumer.", scp="n/a"),
 "B-23": dict(v="NOT-APPLICABLE", p="Looked for per-agent behavioural baselines + anomaly containment.",
   e=["No autonomous agents; one deterministic engine with fixed handlers"],
   n="", na="'Agent behavioural baseline' presumes autonomous tool-using agents whose action mix could drift. Here a deterministic engine runs fixed handlers on a schedule; there is no agent whose behaviour could deviate. The analogous protection (bounding money moved) is the A-34 trading cap, not behavioural anomaly detection.", scp="n/a"),
 "B-24": dict(v="PARTIAL", p="Asked how a drop in LLM decision quality would be noticed.",
   e=["No online eval of LLM output; a provider-side model change would not be detected",
      "Floating model aliases (B-13) make silent provider drift MORE likely"],
   n="Quality drift would surface only as bad trades. Pinning (B-13) + a golden eval (B-10) are the levers.",
   scp="Phase 5: model pinning removes silent-swap drift; golden eval fixture flags decision drift."),
 "B-25": dict(v="NOT-APPLICABLE", p="Compared connection strings/creds/flags across environments.",
   e=["One environment: the operator's own deployment. No staging/prod split, no separate data plane"],
   n="", na="Environment-separation and 'no production credential in non-production' presuppose multiple environments. This system has exactly one deployment with one set of the operator's own credentials; there is no non-production plane that could hold a production secret. The dry-run/live boundary (a runtime flag, not an environment) is handled by A-15/A-34.", scp="n/a"),
 "B-27": dict(v="PARTIAL", p="Tried to verify image signature; tried to deploy a modified image.",
   e=["No image signing/verification; build is reproducible-ish (pinned deps, pinned base tag)"],
   n="No artifact integrity verification.", scp="Phase 5: SBOM + pinned digests; signing disproportionate (residual)."),
 "B-29": dict(v="PARTIAL", p="Checked reliability primitives and whether failure was injected.",
   e=["Timeouts + LLM failover present; no chaos/failure-injection has been run",
      "The fail-safe-on-error path is unit-testable"],
   n="Primitives present, not validated by breaking.", scp="Phase 5: a test injecting exchange failure asserting no-trade + safe state."),
 "B-33": dict(v="NOT-APPLICABLE", p="Looked for a retrieval corpus and its integrity controls.",
   e=["No vector store / retrieval corpus exists"],
   n="", na="There is no persistent retrieval corpus or embedding index to poison or stale. The only cache is short-TTL TA/LLM JSON in dry-run, keyed by symbol, never cross-user, and reproducible on expiry.", scp="n/a"),

 # ================= SHOULD-FIX band (v1.0) =================
 "A-03": dict(v="PARTIAL", p="Found tests asserting on model output; checked deterministic vs judged split.",
   e=["Tests use CANNED LLM output (deterministic); live LLM decisions are NOT gated by any eval set",
      "The schema validation IS the deterministic reduction of the judged surface (good)"],
   n="Deterministic maths hard-asserted; the probabilistic path is trusted live with no eval gate.", scp="Phase 5: golden eval fixture (shared B-10)."),
 "A-14": dict(v="FAIL", p="Looked for a written AI-build/maintenance policy with verification tiers.",
   e=["No such policy exists"],
   n="", scp="Phase 4: governance/constitution.md + AGENTS.md encode the policy and the (single) verification tier."),
 "A-15": dict(v="PARTIAL", p="Looked for the prototype/production boundary and whether it holds.",
   e=["dry_run is the boundary; NOTHING gates the dry_run->live transition (CL-3): any UI/env flip goes live instantly"],
   n="The boundary exists as a flag but is ungated.", scp="Phase 5: the trading-cap applies in live mode; document the go-live checklist. (Full gate on the flag is operator-in-command.)"),
 "A-16": dict(v="PARTIAL", p="Grepped production paths for stubs/TODO/NotImplemented/mock/placeholder.",
   e=["No production stubs/TODOs/NotImplemented found; the only 'placeholder' hits are HTML input attributes; one documented `pass`",
      "No stub-detector lint"],
   n="Genuinely no last-mile stubs — a strength. No standing lint to keep it so.", scp="Phase 5: a stub-pattern lint in CI."),
 "A-29": dict(v="PARTIAL", p="Checked for build/buy/model decision records + exit plan.",
   e=["LLM provider abstraction exists (primary+fallback in one client); no ADR/TCO/exit-plan doc"],
   n="Provider seam exists; decision undocumented.", scp="Phase 4: ADR (shared A-18)."),
 "A-30": dict(v="PARTIAL", p="Looked for documented consistency/availability/redundancy positions.",
   e=["No datastore trade-offs to speak of (no DB); positions undocumented but low-stakes"],
   n="Minimal; largely immaterial at this scale.", scp="none (proportionate)."),
 "A-31": dict(v="PARTIAL", p="Computed cost per cycle; looked for a unit-economics model.",
   e=["A handful of LLM+TA+exchange calls per cycle; cost is cents/day range; no model/cap"],
   n="Immaterial spend; no model.", scp="none (proportionate); model gateway disproportionate."),
 "A-35": dict(v="PARTIAL", p="Hunted for approval queues / pending-human states; checked automatic containment.",
   e=["ZERO load-bearing approval queues (nothing waits on a human) — a genuine strength",
      "No automatic anomaly containment (the trading-cap will add it)"],
   n="No queue to rot (good). Containment is manual today.", scp="Phase 5: trading-cap auto-halt (A-34) is the automatic containment."),
 "A-37": dict(v="PARTIAL", p="Assessed agent + human takeover readiness.",
   e=["Clean code + tests aid takeover; no takeover pack, no AGENTS.md yet"],
   n="", scp="Phase 4/5: AGENTS.md + governance/ serve as the takeover pack."),
 "B-14": dict(v="PARTIAL", p="Checked whether prompt/config changes are governed + audited.",
   e=["Prompts are code (gated by the code gate once CI exists); config changes via UI are logged to the event log but not durably audited",
      "single operator, so 'who changed it' is unambiguous"],
   n="Prompt governance rides the code gate; config-change audit is ephemeral.", scp="Phase 5: prompts through the CI gate; config-save already logs an event."),
 "B-16": dict(v="PARTIAL", p="Asked cost per request/customer.",
   e=["No cost attribution; single user, immaterial spend"],
   n="Immaterial.", scp="none (proportionate)."),
 "B-18": dict(v="NOT-APPLICABLE", p="Checked how a change reaches all users; tried to fire an abort.",
   e=["Single-instance personal deployment; a redeploy replaces the one instance"],
   n="", na="Progressive/canary rollout presupposes many instances/users to expose a change to gradually. There is one instance and one user. The analogue — exposing a change safely before it moves real money — is the dry-run boundary (A-15) plus the trading cap (A-34), not percentage rollout.", scp="n/a"),
 "B-21": dict(v="PARTIAL", p="Made each provider fail (mentally + LLM fallback is unit-tested).",
   e=["LLM: anthropic->openai failover is real and tested; on total LLM failure the engine refuses to trade (fail-safe)",
      "Exchange/TA: no alternate provider; failure => logged job error, no crash, no trade"],
   n="Survives provider outage by failing safe (LLM has true failover).", scp="Phase 5: the fail-safe-on-provider-error test."),
 "B-26": dict(v="PARTIAL", p="Looked for per-feature kill switches that fire themselves.",
   e=["Manual kill switch = Stop (engine.stop, persisted); dry_run flag; no self-firing tripwire"],
   n="Manual kill present; no automatic trip.", scp="Phase 5: trading-cap tripwire auto-flips to halt (A-34)."),
 "B-30": dict(v="NOT-APPLICABLE", p="Load-tested to the knee; inference capacity.",
   e=["Single user, background cadence (minutes); no concurrency, no scale requirement"],
   n="", na="Capacity/load-shedding/autoscaling govern multi-user throughput. This bot runs a handful of sequential API calls every several minutes for one user; there is no load to plan for and no autoscaler to bound.", scp="n/a"),
 "B-35": dict(v="FAIL", p="Asked whether the code-writer can also write the gate that judges it.",
   e=["No policy bundle exists yet; once CI is added it lives in the SAME repo the operator can push to",
      "A solo GitHub repo has one identity — the operator holds both code-write and workflow-write"],
   n="Segregation of gate-from-gated is structurally UNACHIEVABLE for a single-principal repo without a second identity/org. Recorded honestly, not faked.",
   scp="Phase 5: compensating controls — protected branch + required status checks + CODEOWNERS on .github/ and governance/, so bypass is at least visible/logged; residual with tripwire (06-residual-risk-register)."),
 "B-36": dict(v="PARTIAL", p="Listed model versions + deprecation exposure.",
   e=["Floating aliases (B-13); no deprecation watch; fallback chain gives partial resilience"],
   n="Deprecation would surface as failures + fallback.", scp="Phase 5: pin snapshots (B-13) + a note to watch provider EOL."),
 "B-39": dict(v="PARTIAL", p="Asked which reference framework the design targets.",
   e=["None named"],
   n="Design is sound but not mapped to a framework.", scp="Phase 4: governance/ names the (right-sized) reference posture."),

 # ================= PLAN band (v1.0) =================
 "A-39": dict(v="FAIL",
   p="Traced who writes/reviews/judges/tests each change; checked for a deterministic gate + independent verifier.",
   e=["No independent adversarial verifier (no second-vendor model wired); the calibration 'verifier' was same-family inspection only",
      "No deterministic gate; test authorship is not separated from code authorship"],
   n="STOP-SHIP under §3 with A-01. A genuinely independent second-vendor verifier is out of reach for a solo operator — recorded as a hard residual; the deterministic gate (which needs no model opinion) is the compensating substitution.",
   scp="Phase 5: deterministic CI gate as the sole merge authority (needs no model); independent-verifier residual documented with a compensating control."),
 "B-32": dict(v="NOT-APPLICABLE", p="Changed running infra by hand to see if anything notices.",
   e=["Single container from a pinned image; no managed desired-state to reconcile"],
   n="", na="Drift detection reconciles a declared desired state against a managed fleet. Here the whole runtime is one container rebuilt from a pinned Dockerfile; there is no orchestrator holding desired state to diverge from. Rebuild-from-source is the reconciliation.", scp="n/a"),
 "B-34": dict(v="NOT-APPLICABLE", p="Measured inference latency percentiles vs an interactive budget.",
   e=["Inference is background (a rebalance cycle every several minutes), not interactive"],
   n="", na="Latency budgets (TTFT, p95 end-to-end) matter for interactive, user-facing inference. This LLM call runs inside a background scheduler with minute-scale cadence and no user waiting; a few seconds of model latency is immaterial to correctness or UX.", scp="n/a"),
 "B-37": dict(v="NOT-APPLICABLE", p="Deleted a user end-to-end across every derived store.",
   e=["No third-party personal data; the only personal data is the operator's own keys + SMS number, in config.json"],
   n="", na="Right-to-erasure/derived-store retirement governs third-party personal data spread across stores. Here there are no third-party data subjects: the sole data subject is the operator, who erases their own data by deleting config/config.json (and .env). There is no vector store, training set, or trace store holding anyone else's data.", scp="n/a"),

 # ================= ASSESS band (v1.0) =================
 "A-40": dict(v="NOT-APPLICABLE", p="Assessed whether the energy footprint is material.",
   e=["A handful of API calls per cycle; no training, no local heavy inference, no fleet"],
   n="", na="Energy/carbon is a material design constraint for training runs or high-QPS inference fleets. This system makes a few hosted-API calls every several minutes on one small container; the footprint is immaterial by any rate-based method, documented as such rather than measured with an invented number.", scp="n/a"),
 "B-38": dict(v="NOT-APPLICABLE", p="Measured cache hit rate + cost split.",
   e=["Immaterial spend (cents/day); prompt caching would optimise an already-trivial bill"],
   n="", na="Inference economics (prompt-cache hit rate, cost-based routing) optimise a material inference bill. This bot's LLM spend is a few calls per cycle for one user — immaterial — so cache-hit engineering would be optimisation with no measurable return. Re-band if usage ever scales.", scp="n/a"),
}


def merge():
    findings = json.loads((AUDIT / "03-findings.json").read_text())
    by_id = {f["id"]: f for f in findings}
    active_ids = {c["id"] for c in cat["checks"] if c["scope_status"] == "active"}
    missing = active_ids - set(V)
    assert not missing, f"verdicts missing for active checks: {sorted(missing)}"
    extra = set(V) - active_ids
    assert not extra, f"verdicts for non-active checks: {sorted(extra)}"

    for cid, d in V.items():
        rec = by_id[cid]
        meta = CHECKS[cid]
        rec.update({
            "verdict": d["v"],
            "probe": d["p"],
            "evidence": d["e"],
            "note": d.get("n", ""),
            "structural_fix": meta["structural_fix"],
            "door": meta["door"],
            "conditional_escalation": meta.get("conditional_escalation"),
            "standing_control": rec.get("standing_control"),  # null at baseline
            "standing_control_plan": d.get("scp"),
        })
        if d["v"] == "NOT-APPLICABLE":
            rec["na_justification"] = d.get("na", "")

    # ---- §5 fail-closed validation ----
    ids = [f["id"] for f in findings]
    assert set(ids) == active_ids, "findings set must equal active scope"
    assert len(ids) == len(set(ids)) == 79, "exactly 79 unique records"
    for f in findings:
        if f["verdict"] == "PASS":
            assert f.get("standing_control"), f"{f['id']}: PASS requires standing_control"
        if f["verdict"] == "NOT-APPLICABLE":
            assert f.get("na_justification"), f"{f['id']}: NOT-APPLICABLE requires justification"

    (AUDIT / "03-findings.json").write_text(json.dumps(findings, indent=2) + "\n")
    return findings


def render_md(findings):
    order = {"STOP-SHIP":0,"BLOCKER-1":1,"BLOCKER-2":2,"MUST-FIX":3,"SHOULD-FIX":4,"PLAN":5,"ASSESS":6}
    findings = sorted(findings, key=lambda f: (order[f["band"]], f["id"]))
    counts = {}
    for f in findings:
        counts[f["verdict"]] = counts.get(f["verdict"], 0) + 1
    lines = ["# 03 — Findings (Phase 3, catalogue v1.0 — 79 Track A/B checks)\n",
             f"> Baseline commit `840e4f4`. Verdict tally: " +
             ", ".join(f"**{k}** {v}" for k, v in sorted(counts.items())) + ".\n",
             "> `standing_control` is null on every record at Phase-3 baseline — no standing "
             "control exists pre-Phase-5. Under §3 that caps every 'satisfied today' check at "
             "`PARTIAL`; Phase 6 promotes the ones whose controls were installed and demonstrated.\n"]
    cur = None
    for f in findings:
        if f["band"] != cur:
            cur = f["band"]
            lines.append(f"\n## {cur}\n")
        sf = " · _structural_" if f.get("structural_fix") else ""
        esc = f" · **⇧ {f['conditional_escalation']}**" if f.get("conditional_escalation") else ""
        lines.append(f"### {f['id']} — {f['title']}  ·  **{f['verdict']}** (P{f['priority']}){sf}{esc}")
        lines.append(f"- **Probe:** {f['probe']}")
        for ev in f["evidence"]:
            lines.append(f"- **Evidence:** {ev}")
        if f.get("na_justification"):
            lines.append(f"- **N/A justification:** {f['na_justification']}")
        if f.get("note"):
            lines.append(f"- **Note:** {f['note']}")
        if f.get("standing_control_plan") and f["standing_control_plan"] != "n/a":
            lines.append(f"- **Standing control (planned):** {f['standing_control_plan']}")
        lines.append("")
    (AUDIT / "03-findings.md").write_text("\n".join(lines) + "\n")
    return counts


if __name__ == "__main__":
    fs = merge()
    c = render_md(fs)
    print("findings written:", len(fs))
    print("tally:", dict(sorted(c.items())))
