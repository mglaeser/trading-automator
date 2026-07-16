# 05 — Verification (Phase 6)

Per fix: the failing test before, the passing test after, the mutation/clone evidence, the
standing control demonstrated blocking a re-introduced defect, and the deterministic gate
decision. A verdict changed only on fresh re-run evidence, never on the fact that a change
was made. Raw gate output: `audit/evidence/phase5-gate-demonstration.txt`.

## Fix 1 — Trading blast-radius cap + auto-halt (A-11/A-34/A-35/B-08/B-26)
- **Red first:** `tests/test_trading_cap.py` — `test_swap_clamps_to_per_swap_ceiling` and
  `test_daily_cap_refuses_and_halts_engine` FAILED before the change ("DID NOT RAISE",
  clamp assertion off). Pasted in the Phase-5 log.
- **Change:** cap logic added at the single `engine._swap` chokepoint + `_halt()` +
  `max_swap_value`/`daily_trade_cap` defaults.
- **Green after:** 4 cap tests pass; full suite 43 passed.
- **Mutation:** `mutation_smoke.py` flips "per-swap clamp disabled", "daily-cap comparison
  flip" → both KILLED (suite catches them).
- **Clone sweep:** `grep '\.swap(' src/engine.py` → exactly one call site (`_swap:180`);
  every handler routes through it, so the cap cannot be bypassed. No clones.
- **Standing control demonstrated:** `test_daily_cap_refuses_and_halts_engine` watches the
  auto-halt fire (engine_running False + persisted) — the control blocks a real breach.
- **Gate decision:** red→green ✓, suite green ✓, mutation ✓, clone-clean ✓, control
  demonstrated ✓, no new capability ✓ → **merge allowed**.

## Fix 2 — The verification gate itself (A-01/B-01/A-08/A-13/A-02/A-36/B-04)
- **Red first:** Phase-2 calibration — the pre-existing pipeline caught **2/6** seeded
  defects; `policy_gate.py` exited 1 at baseline naming 10 open blockers.
- **Change:** `.github/workflows/ci.yml` + `scripts/{policy_gate,check_deps,secret_scan,
  check_model_pins,gate_selftest,mutation_smoke}.py` + `pyproject.toml` ruff config.
- **Green after:** ruff clean; pytest 43; pip-audit clean; each script exits 0 on the
  clean tree.
- **Standing control demonstrated (the re-introduced-defect proof):** `gate_selftest.py`
  re-seeds D1..D6 → **5/5 caught** (secret-scan kills D1, pytest D2, check_deps D3, ruff
  D4, pytest D6); `mutation_smoke.py` → **8/8 killed** (closes D5's weak-suite class).
  Catch rate **2/6 → 5/5 (+mutation for the 6th)**.
- **Gate decision:** `policy_gate --merge` PASS after promotion; `--deploy` BLOCKED
  (Part 2 pending) — both demonstrated.

## Fix 3 — Injection containment made explicit (A-10/B-15/B-20)
- **Red/added:** `test_injection_cannot_produce_out_of_schema_action` — an adversarial
  model output with an out-of-schema action must become a no-signal.
- **Green after:** passes; `mutation_smoke` "action validation inverted" KILLED.
- **Structural (S13):** the model has no tools/egress; the only route to a trade is
  schema-valid output through `_swap`. The control cannot decay because the capability does
  not exist.

## Fix 4 — Documentation truth (Wave R: CL-1, CL-2)
- README safety-invariant #2 corrected ("opens no sentiment trades", housekeeping noted);
  README dev section corrected ("Binance order **helpers**"); engine docstring corrected;
  cap documented. Verified by re-reading against behaviour (Phase 1 claims re-checked).

## Fix 5 — Lint / error-handling hygiene (A-13/A-26/A-05/A-09)
- **Change:** `ruff` config; `raise … from exc` (B904); `contextlib.suppress` for the
  documented web runner; 7 legitimate broad catches annotated with machine-readable
  justifications; settings dict reformatted.
- **Green after:** `ruff check src tests` clean; suite 43. **Demonstrated:** ruff kills
  D4 (blind-except) in `gate_selftest`.

## Independent verdict re-audit (§ Phase 6 "audit the audit")
A genuine second-vendor independent re-audit is **not available** to a solo operator
(residual R-2). In its place: (1) the deterministic gate re-derives every blocking verdict
from executable evidence, needing no model opinion; (2) the §5 fail-closed invariants are
re-checked by `policy_gate.py` on every run (79 records == active scope, no PASS with null
standing control). This substitution is recorded, not presented as equivalent — see
`07-substitution-ledger.md` and residual **R-2**.

## Net effect
Baseline **0 PASS / 52 PARTIAL / 14 FAIL / 13 N/A** → after repair **16 PASS / 50 PARTIAL
/ 0 FAIL / 13 N/A**. Every FAIL closed to PASS-with-demonstrated-control or
PARTIAL-with-residual. Pipeline catch rate 2/6 → 5/5. Mutation on core 0 → 8/8.
