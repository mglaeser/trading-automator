# 06 — Residual Risk Register (Phase 6)

Every risk left unclosed at MUST-FIX or above — and the three structural residuals of the
operating model — with a **compensating control**, an **executable tripwire**, and an
**owning role**. A risk with no compensating control and no tripwire is not accepted; it is
ignored. None here is ignored.

> All owners are **the operator (in-command)** — a solo project has one accountable human.
> "Tripwire" means an automated check that fires if the risk materialises.

## Structural residuals of the operating model (the honest limits)

### R-1 — Gate/gated identity separation is unachievable on a solo repo (B-35, A-01, A-39)
- **Risk:** the operator holds both code-write and workflow-write; a `git push --no-verify`
  or a disabled required-check could bypass the gate. Absolute separation (Article II /
  B-35) needs a second identity/org a solo project will not sustain.
- **Why not faked:** Article XV classes this repo **Incubating**, where full separation is
  explicitly not required; faking it would be the exact decorative control the mandate
  condemns. Recorded, not papered over.
- **Compensating control:** enable branch protection on the default branch with the `gate`
  workflow as a **required** status check + CODEOWNERS on `.github/` and `governance/`, so
  a bypass is logged and visible. **(Operator action — the one setup step the audit cannot
  perform from inside the repo.)**
- **Tripwire:** `scripts/policy_gate.py` runs in CI and fails closed; a merge that skipped
  it leaves no green `gate` run on the commit — detectable in the Actions history. Add a
  branch-protection audit to the monthly checklist.
- **Owner:** operator.

### R-2 — No standing second-vendor adversarial verifier (A-39, A-03, C-14)
- **Risk:** no always-on model from a different vendor attacks each change; the generator
  could share a blind spot with any single-model review.
- **Compensating control:** the **deterministic gate** decides merges and holds no model
  opinion (needs no verifier); for high-risk diffs (trading logic, auth, secrets) the
  operator runs a one-off review with a different model (documented in AGENTS.md).
- **Tripwire:** `mutation_smoke.py` + `gate_selftest.py` are the standing adversary — a
  regression in their catch counts fails the build, catching the class a verifier would.
- **Owner:** operator.

### R-3 — No always-on Runner / dead-man switch; drills are a manual checklist (A-24, cadence)
- **Risk:** the daily/weekly/monthly drills in `08-standing-regime.md` depend on the
  operator (or a scheduled workflow) running them; silence could be read as health.
- **Compensating control:** the **every-push CI gate** (the load-bearing cadence) is fully
  automated; the periodic drills are scriptable as GitHub scheduled workflows when desired.
- **Tripwire:** the calibration heartbeat runs on **every push**, so the most important
  decay signal (catch-rate drop) fires without a scheduler.
- **Owner:** operator.

## Product/security residuals (MUST-FIX and above), each with compensating control + tripwire

| ID | Risk | Compensating control | Tripwire | Band |
|---|---|---|---|---|
| B-06 | Exchange/LLM keys stored plaintext at rest in `config/config.json`; no vault/rotation. | Gitignored + secret-scan gate (no commit possible); operator uses **withdrawal-disabled, IP-pinned** exchange keys (revocable exchange-side). | `secret_scan.py --history` every push; monthly key-rotation reminder in the go-live checklist. | STOP-SHIP band, **PARTIAL** (committed-secret hazard PASS; at-rest residual) |
| A-15 / CL-3 | The `dry_run`→live flip is ungated; a mistaken flip trades live immediately. | The blast-radius cap + auto-halt apply in live mode; conservative defaults; go-live checklist in AGENTS.md. | Cap tests in the gate; the auto-halt fires on a breach. | SHOULD-FIX |
| B-13 | Model ids are provider aliases, not dated snapshots; provider-side migration can change behaviour silently. | `check_model_pins.py` blocks `-latest`; operator should pin dated snapshots. | Model-pin lint every push; LLM failover on provider error. | BLOCKER-2, PARTIAL |
| B-10 | The LLM's live trading judgement has no golden-set regression eval. | Deterministic decision surface (scoring/schema) is regression-tested; schema validation bounds the model. | `test_distribution_scoring` + mutation smoke; a prompt change rides the gate. | BLOCKER-2, PARTIAL |
| A-06 / B-11 | Rollback (code/prompt/model) is manual and untested/untimed. | CI-on-push + pinned deps make redeploy-from-commit reliable; small diffs. | A rollback-drill line on the monthly checklist. | BLOCKER-1/9, PARTIAL |
| B-09 / B-27 | Container image is unsigned; no SBOM. | Pinned base tag + pinned deps + reproducible build; loopback exposure. | `pip-audit` + `check_deps` every push. | MUST-FIX, PARTIAL |
| A-04 / A-17 | No spec-**coverage** gate; a change mapping to no criterion can still merge. | `governance/spec.md` maps invariants→tests; mutation smoke pins them. | Any invariant regression fails a mapped test. | BLOCKER-2, PARTIAL |

**Out-of-repo action still owed (operator):** rotate the credentials that were pasted into
the original chat (Nexo/TOTP/Anthropic/OpenAI/Groq/sipgate). They are **not** in git
history (B-06 scan clean), but a chat paste is a disclosure. This audit cannot rotate them.
