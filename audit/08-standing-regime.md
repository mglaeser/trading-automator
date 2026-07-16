# 08 — Standing Regime (Phase 7)

The deliverable that outlives the engagement. Everything here is a running artifact, not a
phase. Right-sized to an **Incubating, solo-operated** repo (Article XV): the every-change
tier is fully automated in CI; the periodic drills are a scriptable operator checklist
(residual R-3). The regime should **shrink** — the structural fixes (Article IX) already
removed several rows (no tool gateway to police, no hot-swap path, no exfil channel).

## The Runner (who executes it)
- **Automated:** GitHub Actions (`.github/workflows/ci.yml`) on every push/PR — the
  load-bearing cadence. No separate always-on Runner or dead-man switch (R-3).
- **Operator (in-command):** the periodic drills below; each is one command.

## Ratchet register (S11) — floors that rise, never fall

| Metric | Baseline | Direction | Enforced by | Blocks |
|---|---|---|---|---|
| Pipeline seeded-defect catch rate | **5/5** fast lane (was 2/6) | may not fall | `gate_selftest.py` | merge |
| Core mutation score | **8/8 = 1.00** | may not fall | `mutation_smoke.py` | merge |
| Lint errors | 0 | stay 0 | `ruff` | merge |
| Ruff suppressions | 8 (justified) | may only fall | ruff + review | merge |
| Unresolved/unpinned/vulnerable deps | 0 | stay 0 | `check_deps.py` + `pip-audit` | merge |
| Secrets in tree or history | 0 | stay 0 | `secret_scan.py --history` | merge |
| Floating `-latest` model aliases | 0 | stay 0 | `check_model_pins.py` | merge |
| Irreversible trade without the cap | 0 | stay 0 | cap tests + `_swap` chokepoint | merge |
| Open FAIL in a blocker band | 0 | stay 0 | `policy_gate.py` | merge |
| PASS with null standing control | 0 | stay 0 | `policy_gate.py` | merge |
| `production_eligible` (computed; false while any blocker open OR independent-verification/Runner absent) | false | flips only when computed true | `policy_gate --deploy` | deploy |

## Cadence

| Cadence | What runs | Automated? |
|---|---|---|
| **Every push/PR** | lint · tests · mutation-smoke · dep-existence · SCA · secret-scan(history) · model-pin · **calibration heartbeat** · policy-gate | ✅ CI |
| **Monthly (operator checklist)** | rotate keys reminder · rollback drill (redeploy a prior commit, time it) · branch-protection audit (R-1) · confirm withdrawal-disabled keys | ⬜ scriptable |
| **On trigger** | see below | mixed |

## Continuous calibration (S12) — the heartbeat
The seed corpus **D1..D6** (`02-calibration.md`) is standing: `gate_selftest.py` injects it
every push and asserts each is caught; `mutation_smoke.py` proves the suite kills core
faults. **Grow the corpus:** every future defect/incident adds a seed (a new mutant in
`mutation_smoke.py` or a new case in `gate_selftest.py`). Catch rate is the health SLI — a
drop fails the build.

## Decay watch — how this system would actually rot, and the detector

| Decay path | Detector |
|---|---|
| Suppression creep (`# noqa` to unblock) | ruff suppression count ratcheted; each carries a justification |
| A gate softened / made non-blocking | `gate_selftest.py` stops catching its seed → build fails; policy-gate self-checks |
| Cap raised silently to move more money | cap is config; a change to defaults is a visible diff; tests pin the mechanism |
| Model swapped to a floating alias | `check_model_pins.py` |
| A new trade path bypassing `_swap` | clone-sweep discipline (AGENTS.md); one `client.swap` call site invariant |
| The model gains a tool (completes the trifecta) | AGENTS.md rule + re-run trigger below; injection test |
| Drills quietly stop (R-3) | the every-push heartbeat still runs; monthly checklist is the backstop |
| Branch protection disabled (R-1) | monthly branch-protection audit; missing green `gate` run on a commit |

## Re-run triggers (events that re-open parts of the catalogue)
- **The LLM gains tool-use / function-calling / an egress capability** → re-run A-10, A-11,
  A-34, B-20 **and Part 2's C-06/C-07/C-08** before merge. *This is the single change that
  turns a contained system into an exposed one.*
- **A new external integration / egress destination** → re-run A-28, B-20; update the fixed
  egress allowlist consciously.
- **A new model or provider-side model change** → re-run B-13, B-24; re-pin.
- **A new data class or a move toward multi-user** → re-run the N/A justifications for A-21,
  A-22, B-19, B-25, B-33, B-37 (they assume single-user) and **all of Part 2's privacy set**.
- **Any incident** → add a regression test before closing it; add the defect to the
  calibration corpus.
- **Part 2 delivered** → activate the 40 Track C checks (catalogue v2.0), re-freeze a
  baseline, amend + re-ratify the constitution, and only then can `production_eligible`
  flip true.

## Owner
The regime's owning role is **the operator** (in-command). Its health is one number: the
seeded-defect catch rate (`gate_selftest.py`). If it falls, nothing else about the regime
is working, whatever the dashboards say.

---

## Track C additions to the ratchet register (v2.0)

| Metric | Baseline | Direction | Enforced by | Blocks |
|---|---|---|---|---|
| Sessions holding all three trifecta legs | 0 | stay 0 | `test_no_session_holds_the_lethal_trifecta` | merge |
| State-changing routes without auth-when-token-set | 0 | stay 0 | `test_web_auth` | merge |
| Non-loopback bind without a token | refused | stays refused | `assert_safe_binding` | startup |
| Secrets/PII in prompts | 0 | stay 0 | `test_no_secrets_or_pii_in_prompts` + secret_scan | merge |
| Model tools (egress-capable) | 0 | stay 0 without a full C-06/C-07/C-08 re-run | capability-labels.json + review | merge |

## Track C re-run triggers (added)
- **LLM gains a tool / egress** → re-run C-06, C-07, C-08, C-12, C-17 + A-10/A-11/B-20. The
  single change that turns this contained system into an exposed one.
- **Move toward multi-user / market placement** → re-run C-01, C-04, C-09, C-16, C-23, C-28,
  and re-band the N/A privacy set.
- **New model / provider** → re-run C-34 (training opt-out) + B-13/B-24.
