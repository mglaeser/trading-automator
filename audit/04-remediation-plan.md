# 04 — Remediation Plan (Phase 4)

Constitution is `IN_FORCE_PROVISIONAL` (`governance/constitution.md`); every fix below is
made under it. Planned over all 79 v1.0 verdicts, with doors sized for Track C's rooms so
Part 2 extends without re-work.

## The three root causes (most findings collapse into these)

1. **No verification gate exists.** Drives A-01, A-02, A-06, A-08, A-13, A-36, A-39, B-01,
   B-04, B-06, plus the "no standing control" cap on every PARTIAL. **One fix: build the
   CI gate.** This is the single highest-leverage move in the engagement.
2. **The irreversible money-moving capability has no blast-radius cap.** Drives A-11, A-34,
   A-15, A-35, B-08, B-26, CL-3. **One fix: a deterministic trading cap + auto-halt at the
   single `engine._swap` chokepoint.**
3. **Machine-maintainability artifacts are thin.** Drives A-04, A-14, A-32, A-33, A-37,
   B-02. **One fix: `governance/spec.md` + `AGENTS.md`.**

Everything else is either already structurally sound (Article IX), proportionately policed,
or a documented residual.

## Structural ledger (§6.5.6) — the 28 Track A/B checks carrying a structural fix

| Check(s) | Door | Move available | Taken? | If not: the control run forever instead, and why cheaper |
|---|---|---|---|---|
| A-11 A-34 B-08 B-22 | tool-gateway | One mediated trade gateway: every order through `engine._swap`, wrapped cap→validate→apply→auto-halt | **YES (partial→built)** | The single `_swap` chokepoint already exists; the cap is added *there*, so it cannot be bypassed by any handler. Sized for C-06/C-08/C-12/C-17. |
| B-20 C-07 C-08 | agent-split | LLM has no tools and no egress; the exfil leg does not exist | **YES (pre-existing, by architecture)** | Nothing to build — asserted by a new invariant test. |
| A-20 B-05 B-14 | prompt-registry | Prompts are code constants; no config/db/env load path | **YES (pre-existing)** | No hot-swap path exists to police. |
| A-29 A-31 B-13 B-16 B-34 B-36 B-38 | model-gateway | `llm.py` is already the single inference chokepoint | **PARTIAL** | Pin model snapshots + unpinned-model lint at the one chokepoint (B-13). **Not building** a full gateway abstraction for 2 call sites; cost-attribution (A-31/B-16/B-38) is *policed=none* because spend is immaterial (cents/day) — recorded, not defaulted. |
| B-07 C-23 C-24 | telemetry-emitter | One typed redacting emitter | **NO** | 2 log call sites, no PII in logs (verified). A typed emitter is disproportionate; policing = add model-id+prompt-hash+token logging at the `llm.py` chokepoint. Cheaper because the surface is 2 lines, not N. |
| A-28 | guarded-outbound-client | Constructor-enforced timeout/retry/breaker/fallback | **PARTIAL** | Timeouts already on all 3 adapters + LLM failover exists. Full guarded-client class disproportionate for 3 adapters; policing = keep timeouts, add the fail-safe test. |
| A-05 A-09 | module-visibility | Import linter so cross-boundary import won't lint | **YES** | ruff import-boundary rule added (cheap, one config). |
| A-02 | functional-core-shell | Extract decision logic from I/O | **YES (pre-existing)** | Engine handlers already take an injected client; core maths (`asset_distribution_from_recommendation`, cap logic) are pure. Mutation is reachable now. |
| A-12 | deletion | Delete dead code | **N/A** | No dead code found. |
| A-19 | generate-both-sides | Generate schema from spec | **YES (framework)** | FastAPI generates the OpenAPI schema from handlers; drift is structurally low. |
| A-06 | strangler-refactor | Trunk + flags | **N/A** | No large refactor in scope. |
| A-07 | (tenancy/DAL clone class) | Dedup template | **N/A** | Low duplication measured; no clone class. |
| B-35 | policy-bundle-separation | Gate in a separate repo/identity | **NO (unachievable solo)** | Residual **R-1**: solo repo has one identity. Policing = protected branch + CODEOWNERS on `.github/`+`governance/`; cheaper only because the alternative (a second org/identity) is operational overhead a solo operator won't sustain — bypass is made *visible*, not impossible. |
| B-10 C-35 | heldout-eval-store | Eval set the pipeline can't send to a provider | **NO** | A local golden fixture is proportionate; there is no provider to leak a held-out set *to* for a bot that runs the eval locally. Policing = in-repo golden fixture. |
| B-25 C-16 | credential-broker | Env-scoped credential minting | **N/A** | Single environment; no non-prod plane. |
| B-37 C-04 C-28 C-32 | derived-store-registry | Registry every PII store must join | **N/A** | No third-party personal-data stores. |

**Doors genuinely taken structurally (Article IX):** the trade gateway cap, the
no-egress-from-model invariant, prompts-as-code, model-chokepoint pinning, import
boundaries. **Doors deliberately policed with the cost named:** telemetry emitter, guarded
client, gate separation (R-1), held-out store. **Doors N/A by architecture:** DAL tenancy,
credential broker, derived-store registry, deletion.

## Waves

**Wave 1 — STOP-SHIP + BLOCKER-1 + the material safety control** (closes the operating
model's load-bearing gaps and commissions the regime core):
- **W1.1** Build the CI gate `.github/workflows/ci.yml` + `scripts/policy_gate.py` → A-01,
  B-01, A-39, A-15(partial).
- **W1.2** Mutation testing on core (`mutmut`) wired into the gate at a floor → A-02.
- **W1.3** Dependency existence + `pip-audit` (`scripts/check_deps.py`) → B-04, C-03(pre-stage).
- **W1.4** Secret scan (`scripts/secret_scan.py`, head + history) → B-06, A-08.
- **W1.5** ruff lint+format + import-boundary + broad-except + stub lints → A-08, A-13,
  A-05, A-09, A-16, A-26.
- **W1.6** **Trading blast-radius cap + auto-halt** at `engine._swap` + tests → A-11, A-34,
  A-35, B-08, B-26, A-24, CL-3.
- **W1.7** Calibration job re-runs the D1..D6 corpus in CI; catch-rate recorded → A-36.

**Wave 2 — BLOCKER-2:**
- **W2.1** Pin model snapshots + unpinned-model lint → B-13, B-05, B-24, B-36.
- **W2.2** Injection/adversarial-output test (no out-of-schema action reaches a swap) → A-10, B-15.
- **W2.3** Fail-safe-on-provider-error test + no-trade-on-missing-signal → A-24, B-21, B-29.
- **W2.4** Golden eval fixture (canned TA → asserted action) → B-10, A-03.
- **W2.5** `governance/spec.md` (invariants + NFRs as executable acceptance) → A-04, A-17.
- **W2.6** `AGENTS.md` (paved road, invariants, go-live checklist) → A-33, B-02, A-32, A-14, A-37.

**Wave R — naming truth (interleaved):**
- Correct CL-1 ("aborts, no trades") and CL-2 ("Binance order mechanics") wording in
  README + docstrings; note `sell_all_crypto` name.

**Wave 3/4 — MUST-FIX / lower, proportionate:**
- SBOM (CycloneDX) + license note (A-38, B-09, B-27); property tests on `_parse_json` +
  settings coercion (A-25); log model-id/prompt-hash/tokens (B-07); ADR for LLM-advisor
  architecture (A-18, A-29); config-backup note (B-31).
- Everything marked *residual* goes to `06-residual-risk-register.md` with a compensating
  control + tripwire, never left as a bare gap.

## Dependencies & ordering
W1.1 (the gate) is the spine — every later control registers into it. W1.6 (trading cap)
is independent and can land in parallel. W2.1 (pinning) precedes W2.4 (eval) because a
floating model undermines the eval baseline. Wave R is behaviour-preserving and interleaves
freely. Each fix follows the Phase-5 discipline: red test → smallest change → suite +
mutation → clone sweep → standing control demonstrated → independent review (discretionary,
R-2) → deterministic gate.
