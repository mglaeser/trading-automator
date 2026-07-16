# 07 — Substitution Ledger (Phase 6)

Every control a conventional audit would discharge with *"a human reviews it"*, the
mechanism (S1–S13) that replaces it here, and the evidence the mechanism works. If this
ledger has a gap, the operating model has a gap — a place where everyone assumes something
is standing. It has no silent gaps; the three genuine limits are named as residuals R-1..3.

| Classical control (ends in a person) | Substitution | Mechanism here | Evidence it works |
|---|---|---|---|
| A reviewer approves the merge | **S1** deterministic gate | `.github/workflows/ci.yml` + `scripts/policy_gate.py`, fail-closed, no override | `policy_gate` blocked 10 open blockers at baseline; PASSes only when all closed — `audit/evidence/phase5-gate-demonstration.txt` |
| A reviewer notices the tests are weak | **S4** mutation as meta-gate | `scripts/mutation_smoke.py` (8 core mutants) | 8/8 killed; a disabled cap/clamp/validation mutant is caught |
| A reviewer spots a hard-coded key | **S3/S6** secret scan | `scripts/secret_scan.py --history` in the gate | catches seeded D1; head+history clean |
| A reviewer spots an invented package | **S1/S3** dependency existence | `scripts/check_deps.py` + `pip-audit` | catches seeded D3; 9/9 deps verified on PyPI |
| A reviewer spots a swallowed exception | **S3** blind-except lint | `ruff` BLE in the gate | catches seeded D4 |
| A reviewer spots a silent model swap | **S1** model-pin lint | `scripts/check_model_pins.py` | blocks `-latest` aliases (residual B-13: dated pins recommended) |
| A reviewer confirms the gate still works | **S12** continuous calibration | `scripts/gate_selftest.py` re-seeds D1..D6 every push | 5/5 caught (was 2/6) |
| A human approves an irreversible/large trade | **S5/S6** reversibility+blast-radius cap | `engine._swap` clamp + `daily_trade_cap` + `_halt()` | `test_daily_cap_refuses_and_halts_engine`: auto-halt fires |
| An operator watches the dashboard to kill a runaway | **S8/S10** self-firing kill switch | `_halt()` on cap breach (persisted); manual Stop is redundancy | halt demonstrated by test; not counted as the control |
| A human confirms a tool call is safe (injection) | **S13** unrepresentability | the model has **no tools/egress**; only schema-valid output reaches `_swap` | `test_injection_cannot_produce_out_of_schema_action`; single `client.swap` call site |
| A human keeps the prompt from being hot-swapped | **S13** prompt-as-code | prompts are constants in `src/prompts.py`; no config/db/env load path | no hot-swap path exists to police |
| A second reviewer independently checks (segregation) | **S1 + residual R-2** | deterministic gate + discretionary second-model review on high-risk diffs | gate needs no model opinion; R-2 documents the missing standing verifier |
| A human keeps the gate honest (separation of duties) | **compensating + residual R-1** | branch protection + CODEOWNERS (operator enables) | R-1: visible-not-impossible; Article XV Incubating scope |
| A person decides to freeze releases on an incident | **S1** the engine fails safe | any job error → no trade, logged, SMS; container self-restarts | `_run_job` fail-safe path; A-24 finding |

**No control in this engagement is discharged by proposing that a human review it.** The
one legitimate human input — the operator's decision to go live (author intent) — is
in-command, not in-loop, and is bounded by the cap that applies regardless (A-15/CL-3).
