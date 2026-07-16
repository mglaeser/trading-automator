`SCOPE: TRACKS A/B (CATALOGUE v1.0) COMPLETE — TRACK C (SECURITY, PRIVACY, ASSURANCE) NOT YET AUDITED — NOT CLEARED FOR PRODUCTION TRAFFIC UNTIL PART 2 CLOSES`

# 09 — Executive Summary (Part 1, catalogue v1.0)

**When this engagement began, the pipeline caught two of six seeded defects — and because
no human reviews any change here, a green build in this repository was not evidence of
anything. The system had, in the mandate's terms, no verification at all.** That is the
fact everything else hangs from, and it is now fixed: the deterministic gate catches five
of five in the fast lane, kills eight of eight core mutants, and blocks a merge on any open
blocker. It caught 2/6; it is not me you are trusting now, it is that gate.

## What was actually wrong (baseline: 0 PASS / 52 PARTIAL / 14 FAIL / 13 N/A)
1. **No verification gate existed** — no CI, no branch protection, no scanner, no mutation
   testing, no independent verifier. The 38-test suite ran only when someone typed it.
   (A-01, A-02, A-08, A-13, B-01 — STOP-SHIP/BLOCKER-1 under the §3 escalations.)
2. **The irreversible money-moving capability had no blast-radius cap.** In live mode a
   single injection, bug, or bad LLM read could move unbounded funds, with a manual-only
   kill switch. (A-11, A-34, B-08.)
3. **Two documented safety claims were false** — "rebalance aborts, no trades" (housekeeping
   trades run before the abort) and overstated test coverage of the Binance order path.

## What is fixed and standing (now: 16 PASS / 50 PARTIAL / 0 FAIL / 13 N/A)
- A **CI gate** (`.github/workflows/ci.yml` + six `scripts/*.py`): lint, mutation-smoke,
  dependency-existence, SCA, secret-scan (history), model-pin lint, a seeded-defect
  calibration heartbeat, and a fail-closed policy gate. Every control was **demonstrated
  blocking a re-introduced defect** — not designed, watched.
- A **trading blast-radius cap + self-firing auto-halt** at the single `_swap` chokepoint:
  large swaps clamp down, a swap breaching the rolling-24h cap is refused and the engine
  halts itself (persisted). Proven by test.
- The two false claims corrected; injection containment made explicit with a test.
- **Zero open FAIL in any blocker band.** `policy_gate --merge` PASSES; the suite is 43
  green; catch rate 2/6 → 5/5; core mutation 0 → 8/8.

## What is still broken, and what will break next
- **This is NOT cleared for production.** Track C (security, privacy, assurance — the two
  unconditional STOP-SHIP checks C-01/C-04 among them) is **unaudited**. `production_eligible`
  is `false`, computed, and `policy_gate --deploy` fails closed on it. Part 1 cannot lift
  that; only Part 2 can.
- **Three residuals are structural, not oversights** (`06-residual-risk-register.md`):
  **R-1** a solo repo cannot separate the gate from the gated — *you must enable branch
  protection with the `gate` check required, or the gate is bypassable by a direct push;*
  **R-2** there is no standing second-vendor verifier; **R-3** the periodic drills are a
  manual checklist. Each has a compensating control and a tripwire. None is faked green.
- **The one change that would turn this contained system into an exposed one:** giving the
  LLM tool-use. Today the model has no tools and no egress, so an injection cannot act —
  that containment is architectural. Add a tool and the lethal trifecta can close. The
  re-run trigger for it is wired (`08-standing-regime.md`); honour it.
- **What will rot first:** the trading cap raised "just for today," or a model id drifting
  to an alias. The detectors exist (config diffs, `check_model_pins`), but a solo operator
  is the one who must not wave them through — Article XIV exists for exactly that moment.
- **Owed outside this repo:** rotate the credentials pasted into the original chat. They
  are not in git history, but a paste is a disclosure. The audit cannot do it for you.

## Bottom line
Track A/B is complete, gated, and honest about its own limits. The system is materially
safer than it was — capped, scanned, mutation-tested, and unable to trade past a hard
ceiling — but it is **not production-cleared**, and it will only stay safe if the gate stays
required and nobody teaches the model to act. The green checkmark now means something. Keep
it meaning something.
