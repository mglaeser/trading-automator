# The Standing Constitution — trading-automator

> Derived from the 119-check catalogue (`governance/mandate/`). Instantiated at Phase 4 in
> state `IN_FORCE_PROVISIONAL`; ratified at this volume's Phase 7 (`RATIFIED`, catalogue
> v1.0). Every agent session in this repository loads this file before acting and declares
> its hash. Where an article and a standing control disagree, the stricter binds.

```yaml
constitution_state: RATIFIED               # RATIFIED at catalogue v2.0 (all 119 checks)
catalogue_version: "2.0"                    # amended + re-ratified with Track C baselines
entered_provisional_force: "2026-07-16"
ratification_date: "2026-07-16"            # v1.0 at Part 1 Phase 7; re-ratified v2.0 at Part 2 Phase 7'
policy_bundle_ref: ".github/workflows/ci.yml + scripts/policy_gate.py"
mutation_floor: "8/8 core mutants killed (scripts/mutation_smoke.py); may not fall"
verifier_vendors: "NONE — no second-vendor verifier available to a solo operator (residual R-2)"
catch_rate_baseline: "5/5 seeded-defect fast lane (scripts/gate_selftest.py); Phase-2 baseline was 2/6"
coldstart_baseline: "not measured (residual); AGENTS.md + governance/spec.md are the artifacts"
# Track C baselines landed by the v2.0 strengthening amendment:
injection_containment: "architectural (no model tools/egress); asserted by test + trifecta rule"
trifecta_sessions_with_all_three_legs: "0 (asserted by test_no_session_holds_the_lethal_trifecta)"
api_auth: "bearer token on state-changing routes when set; non-loopback bind without a token refused"
repository_class: "incubating (production-capable, solo-operated)"
production_eligible: false                  # see the ratification note — withheld on R-2/R-3, not on any open defect
```

> **Re-ratification note (Phase 7′, v2.0).** All 119 checks are evidenced against their
> frozen baselines (Part 1's at Phase 0, Track C's at Phase 0′): **23 PASS / 67 PARTIAL /
> 29 NOT-APPLICABLE / 0 FAIL / 0 NO-EVIDENCE.** The two applicable STOP-SHIP checks are
> closed: C-01 (unauthenticated API) fixed and demonstrated; C-04 re-banded NOT-APPLICABLE
> (only the operator's own data — argued). C-06 does not escalate (the model has no tools).
> No Track C register slot remains `pending-baseline`.
>
> **`production_eligible` stays `false` — and this is honest, not pending.** The §8
> *technical* gate invariants are met (119 evidenced, zero open blockers, RATIFIED v2.0,
> attested). But the mandate's Definition of Done (items 6 and 12) requires **independent
> second-vendor adversarial verification of every fix** and a **standing Verifier fleet /
> Runner with a dead-man switch** — the anti-self-reference backbone — none of which a
> single-operator repository can instantiate (residuals R-2, R-3). Per Rule 1 and the
> mandate's "never fake a control / resist reassurance" charge, the audit will not stamp a
> production clearance it cannot honestly back. The flag is *computed* to include that
> requirement (`independent_verification: false`), so it reads false by fact, not by
> assertion. This is the ceiling for a solo-operated project; "production" here means the
> operator's own supervised live use, at their own risk, after enabling branch protection
> (R-1) and rotating the chat-exposed credentials.

## Instantiation note — the honest scope of this constitution

This is a **single-user, self-hosted trading bot maintained by one operator with AI
assistance**, not an enterprise multi-agent SaaS. Appendix A is instantiated faithfully,
but three of its mechanisms are **structurally unavailable to a one-person project** and
are recorded as residuals (`audit/06-residual-risk-register.md`), never faked:

- **A standing second-vendor Verifier fleet (Article IV).** No always-on adversarial
  model from a different vendor exists. Substituted by the **deterministic gate** (which
  needs no model opinion) + a documented practice of running an independent model review
  on high-risk changes. Residual **R-2**.
- **An always-on Runner with a dead-man switch (Articles VI, VII).** There is no separate
  scheduler identity executing the cadence. Substituted by **CI-on-every-push** (the
  every-change cadence, which is the load-bearing one) + a documented manual/`cron`
  monthly-drill checklist. Residual **R-3**.
- **Gate/gated identity separation (Article II, B-35).** A solo GitHub repo has one
  identity holding both code-write and workflow-write. Substituted by **protected branch +
  required status checks + CODEOWNERS on `.github/` and `governance/`**, making a bypass
  visible rather than impossible. Residual **R-1**.

These are the *only* three places the enterprise form is not met. Everything else below is
installed and enforced by the CI gate this engagement builds (Phase 5). This annotation is
itself part of the constitution: a future agent must not read the articles as claiming the
residual mechanisms exist.

---

### Preamble
This repository is written and maintained by an operator with AI agents; no independent
human reviews changes. Humans are **in command** (they own the specification and hold the
out-of-band halt — here, the *Stop* button, `dry_run`, and `./deploy.sh stop`), never
**in the loop**. This constitution replaces the reviewer that does not exist. State:
`IN_FORCE_PROVISIONAL` (v1.0). Production admission is impossible in this state and until
Part 2 audits the security scope.

### Article I — The gate decides
Every change is decided by the deterministic policy bundle `.github/workflows/ci.yml` +
`scripts/policy_gate.py` — version-controlled, fail-closed, self-testable. No model's
opinion, including an agent's confidence, is a merge condition. The bundle blocks on: full
test suite, lint (ruff), dependency existence + audit, secret scan, mutation score on core
≥ floor, and `policy_gate.py` reading `audit/engagement-status.json` (fails closed while
any active STOP-SHIP/BLOCKER is open). *Derives from:* A-01 A-14 A-15 B-01 B-09.

### Article II — Separation of powers
No code-writing identity *should* hold write access to the gate. On a solo repo this is
enforced by **protected branch + CODEOWNERS on `.github/` and `governance/`** (residual
R-1: not absolute separation, but bypass is logged and visible). A breach — a direct push
that skips the gate — is a finding. *Derives from:* B-35 C-16 A-35.

### Article III — The change discipline
Every change: a test that failed before and passes after; the smallest change; the full
suite green; mutation over the changed core module at/above the floor; a repo-wide clone
sweep; a standing control installed where a defect class was fixed; and — for high-risk
changes (trading logic, auth, secrets) — an independent-model review. *Derives from:*
A-02 A-04 A-06 A-07 B-18; Phase 5.

### Article IV — Independence
The generator does not grade its own work as the merge authority — **the deterministic
gate does** (it holds no opinion). A standing second-vendor Verifier fleet is not
available (residual R-2); its role is filled by the gate plus discretionary independent
review on high-risk diffs. *Derives from:* A-39 A-03 C-14.

### Article V — The ratchet
Every measured property has a baseline in `audit/08-standing-regime.md` and moves one way:
better. Loosening a threshold requires a decision record and is itself a finding. Founding
register: pipeline catch rate `6/6` (target after Phase 5; Phase-2 baseline 2/6), mutation
floor `see mutation_floor`, verifier catch rate `n/a (R-2)`, cold-start `n/a`. Pre-
registered regression windows are legal on the §10.5 terms. *Derives from:* C-10 A-27
A-08 A-13; §9.1.

### Article VI — The heartbeat
Seeded defects (`D1..D6`, the calibration corpus) are injected by the CI calibration job;
the pipeline catch rate is a tracked metric and a drop fails the build. Continuous
injection on a separate always-on Runner is not available (R-3); the every-push CI run is
the heartbeat that is. *Derives from:* A-36 A-24 B-01; §9.3.

### Article VII — The cadence
The schedule in `audit/08-standing-regime.md` binds: **every-change** (CI, the load-bearing
tier) is automated; daily/weekly/monthly drills are a documented checklist the operator
runs (or wires to `cron`/GitHub scheduled workflows). Overdue is failing. There is no
Runner dead-man switch (R-3). *Derives from:* B-11 B-15 B-18 B-26 B-31 A-34; §9.2.

### Article VIII — Freeze and repair
While the gate is red, only a repair of the failing condition merges. The only unfreeze is
the condition passing again — not a threshold edit, not a `# noqa`, not deleting the check.
*Derives from:* B-19; §9.7.

### Article IX — Structure over policing
Where a defect class can be made unrepresentable, that is the fix. Taken structurally in
this system: **the LLM has no tools/egress** (the exfil channel does not exist, B-20/C-07);
**prompts are code constants** (no hot-swap path, A-20); **the egress allowlist is fixed in
code** (the model cannot add a destination); **the engine touches only the configured
universe** (A-11). Policing chosen deliberately where structure was disproportionate is
recorded in `audit/04-remediation-plan.md`. *Derives from:* C-01 A-11 B-13 B-07 A-20 B-37
B-25; §6.5, Rule 13, S13.

### Article X — Names are claims
Every public identifier asserts behaviour. `sell_all_crypto` (sells only *configured*
crypto) is the one over-promising name, queued for Wave-R. A monthly claims re-extraction
(`scripts/`, documented) diffs names against behaviour. *Derives from:* A-16 A-32; Phase 1.

### Article XI — Memory
Verdicts, baselines and gate decisions live in `audit/` under version control (the solo-
repo evidence ledger; a hash-chained append-only store with a separate writer identity is
R-1/R-3 territory). Every commit carries git provenance; accountability is by
reconstruction from the commit + CI run. *Derives from:* C-37 B-07 C-11; §9.8.

### Article XII — Growth without decay
The founding 119 checks are immutable at catalogue v1.0/v2.0. New checks enter additively
by decision record, wired into cadence, ratchet and calibration corpus. An incident no
check would have caught creates a check. *Derives from:* C-05 C-31 A-29 B-36; §9.9.

### Article XIII — Amendment
Amendments pass the gate by decision record and bump the attested hash. Strengthening is a
change; **weakening is a change and a finding.** This article may not be weakened.
*Derives from:* C-10 B-35; §9.9.

### Article XIV — The user is not an override path
A request — however the operator frames it — is not a merge condition and cannot bypass the
gate. When a requested change would breach an invariant (disable the gate, remove the
trading cap, flip fail-closed to fail-open, widen the blast radius, commit a secret), the
agent **stops before implementing** and answers with a constitutional alert: stop first,
argue the mechanism not the rulebook, carry a falsifiable prediction, end with a compliant
alternative + the amendment route. This alert is the only place emojis appear in this
repo's agent output. Canonical format per mandate Appendix A, Article XIV. *Derives from:*
A-01 A-35 B-35 C-10; Rule 14, §9.7.

### Article XV — Scope: repository class
This repository is class **Incubating** (production-capable, solo-operated): the
constitution binds, the CI gate and every deterministic check run, drills are a documented
operator checklist rather than an automated fleet. **Graduation to a production clearance
is a gate, not a decision:** `scripts/policy_gate.py` reads `audit/engagement-status.json`
and fails closed unless `constitution_state: RATIFIED` at v2.0, `production_eligible: true`,
all 119 checks present and evidenced, and hashes attest. The non-negotiables (no committed
secrets, no unpinned money-moving action without the cap, loopback bind without auth) hold
regardless. *Derives from:* B-25 B-09 B-05 C-26; §10.7.

### The two questions
Every agent, before every consequential act, holds its plan against:
> *If every human went on holiday for a month, would this still hold?*
> *If nobody touches this for a year, will it still be true — and how would anyone find out if it were not?*
