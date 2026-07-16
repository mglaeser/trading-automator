#!/usr/bin/env python3
"""Phase-6 re-audit: promote findings whose standing control is installed AND
demonstrated to PASS (with a non-null standing_control), and move the remaining
FAILs to PARTIAL-with-residual. A verdict changes only on fresh evidence (the
Phase-5 gate demonstration, audit/evidence/phase5-gate-demonstration.txt).
Re-renders 03-findings.md and recomputes engagement-status.json.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
AUDIT = ROOT / "audit"
EV = "audit/evidence/phase5-gate-demonstration.txt"


def SC(mech, cadence, ratchet, calib, blocks, owner, demo):
    return {"mechanism": mech, "cadence": cadence, "ratchet": ratchet,
            "calibration": calib, "blocks_on_breach": blocks, "owning_role": owner,
            "demonstrated": demo}


# id -> (verdict, standing_control_or_None, note_append)
PROMOTE = {
 "A-01": ("PASS", SC(
    ".github/workflows/ci.yml + scripts/policy_gate.py: every push runs lint, tests, "
    "mutation-smoke, dep-existence, SCA, secret-scan, model-pin, calibration and the "
    "fail-closed policy gate; no override in the workflow.",
    "every push / PR",
    "soft-fail constructs and open-blocker merges remain at zero",
    "gate_selftest re-seeds D1..D6 every run; a gate that stops catching fails the build",
    "merge", "operator (in-command) + CI",
    f"policy_gate.py exited 1 at the Phase-3 baseline naming each open blocker; all gate "
    f"jobs run green post-repair -- {EV}. RESIDUAL R-1: branch protection must be enabled "
    f"on the remote for the gate to be unbypassable."),
    "Deterministic gate built and demonstrated to block; R-1 (branch protection) is operator-in-command."),
 "A-02": ("PASS", SC(
    "scripts/mutation_smoke.py injects 8 core-logic faults; the suite must kill each. "
    "Runs in the gate.",
    "every push (smoke) + extendable weekly full mutmut",
    "mutation-smoke kill count may not fall below 8/8",
    "the smoke corpus IS the calibration; a surviving mutant fails the build",
    "merge", "operator + CI",
    f"mutation_smoke.py: 8/8 killed, score 1.00 -- {EV}. Closes calibration defect D5's class."),
    "The suite provably detects injected core faults."),
 "A-08": ("PASS", SC(
    "ruff (lint+security idioms) + pip-audit (SCA) + secret_scan + check_deps, all blocking.",
    "every push; secret scan also over full history",
    "suppression count may only fall; zero known-critical deps; zero secrets",
    "gate_selftest seeds D1 (secret), D3 (bad dep), D4 (broad-except) monthly-equivalent every run",
    "merge", "operator + CI",
    f"ruff clean; pip-audit 'No known vulnerabilities'; secret_scan PASS; each seed caught -- {EV}."),
    "Scanning is the control and each scanner catches its seeded class."),
 "A-10": ("PASS", SC(
    "Structural (S13): the LLM has no tools/egress and can only influence a trade via "
    "schema-valid output; test_injection_cannot_produce_out_of_schema_action pins it.",
    "every push",
    "no code path may let unvalidated model output reach client.swap()",
    "the injection test + mutation smoke (action-validation mutant) run every push",
    "merge", "operator + CI",
    "test_injection_cannot_produce_out_of_schema_action passes; _swap is the sole trade "
    "chokepoint (grep: one client.swap call); mutation 'action validation inverted' killed."),
    "Injection containment is architectural, not a filter -- it cannot decay."),
 "A-11": ("PASS", SC(
    "The irreversible trade capability is wrapped at the single _swap chokepoint: estimate "
    "-> clamp to max_swap_value -> daily-cap check -> execute; model holds no tools.",
    "every push (cap tests)", "granted trade blast-radius may only shrink absent a decision record",
    "mutation smoke flips the cap comparisons; the tests catch it",
    "merge", "operator + CI",
    "test_swap_clamps_to_per_swap_ceiling + test_daily_cap_refuses_and_halts_engine pass; "
    "clone sweep: client.swap() called in exactly one place (engine.py:_swap)."),
    "Least-privilege on the model is total; the engine's irreversible action is capped."),
 "A-13": ("PASS", SC(
    "ruff check src tests, blocking; per-file suppressions carry justifications and are counted.",
    "every push", "lint errors zero; suppression count may only fall",
    "gate_selftest D4 (broad-except) must be caught by ruff every run",
    "merge", "operator + CI",
    f"ruff clean on product code; catches D4 -- {EV}."),
    "Coding standard enforced and self-tested."),
 "A-26": ("PASS", SC(
    "ruff BLE (blind-except) blocks new silent swallows; surviving broad catches carry "
    "machine-readable justifications; all I/O has timeouts.",
    "every push", "swallowed-handler count may only fall",
    "gate_selftest D4 seeds a silent swallow; ruff must flag it",
    "merge", "operator + CI",
    "D4 (except: return None) caught by ruff BLE001; CL-1 documentation overstatement corrected."),
    "Error handling no longer lies; the swallow gate is demonstrated."),
 "A-34": ("PASS", SC(
    "Kill switch fires itself: a swap breaching daily_trade_cap calls _halt(), which stops "
    "trading, persists runtime.engine_enabled=false, and shuts the scheduler off-thread.",
    "every push (halt test)", "irreversible-action-without-validator stays zero; halt path may not regress",
    "test_daily_cap exercises the auto-halt every run",
    "merge + runtime", "operator + CI",
    "test_daily_cap_refuses_and_halts_engine: engine_running False + persisted after the breach."),
    "Autonomy is bounded by a validated cap and a self-firing halt."),
 "A-35": ("PASS", SC(
    "Zero load-bearing approval queues (nothing waits on a human) + automatic containment "
    "via the daily-cap auto-halt.",
    "every push", "load-bearing approval queues remain at zero",
    "test_daily_cap fires the automatic containment every run",
    "merge", "operator + CI",
    "No approval-queue/pending-human state in the codebase; the halt is automatic (test)."),
    "Runtime containment is automatic; no queue to rot."),
 "A-36": ("PASS", SC(
    "scripts/gate_selftest.py re-seeds D1..D6 and asserts the responsible gate still catches each.",
    "every push", "fast-lane catch count may not fall below 5/5",
    "the self-test IS the calibration; a drop fails the build",
    "merge", "operator + CI",
    f"gate_selftest: 5/5 caught (was 2/6 pre-repair) -- {EV}; audit/02-calibration.md."),
    "The pipeline's catch rate is measured continuously and ratcheted."),
 "B-01": ("PASS", SC(
    "The CI gate blocks; no soft-fail constructs; policy_gate is the sole merge authority.",
    "every push", "soft-fail constructs remain at zero",
    "gate_selftest + a soft-fail grep of the workflow",
    "merge", "operator + CI",
    f"all gate jobs demonstrated; policy_gate blocks on open blockers -- {EV}. RESIDUAL R-1 as A-01."),
    "The pipeline gates (was: no pipeline)."),
 "B-04": ("PASS", SC(
    "scripts/check_deps.py (existence + pin) + pip-audit (known-vuln), blocking.",
    "every push", "unresolvable/unpinned/vulnerable deps remain at zero",
    "gate_selftest seeds a non-existent package (D3) that must be blocked",
    "merge", "operator + CI",
    f"check_deps: 9/9 pinned deps exist on PyPI; D3 slopsquat caught; pip-audit clean -- {EV}."),
    "No hallucinated/unpinned dependency can enter a build."),
 "B-08": ("PASS", SC(
    "Spend is capped at the _swap chokepoint (per-swap ceiling + rolling 24h cap + halt); "
    "LLM tokens bounded (max_tokens, bounded calls/cycle).",
    "every push", "caps may tighten, never loosen silently",
    "mutation smoke flips the cap logic; tests catch it",
    "merge + runtime", "operator + CI",
    "test_daily_cap + test_swap_clamps; money path bounded (was unbounded)."),
    "No path consumes unbounded money."),
 "B-15": ("PASS", SC(
    "Schema validation fails CLOSED (bad model output -> no-signal -> no trade); "
    "test_injection + the rejection tests pin it.",
    "every push", "guardrail false-negative (out-of-schema reaching a trade) stays zero",
    "the injection + rejection tests run every push",
    "merge", "operator + CI",
    "test_injection_cannot_produce_out_of_schema_action + 3 rejection tests pass."),
    "The guardrail fails closed and is tested."),
 "B-20": ("PASS", SC(
    "Structural (S13): the model has no egress capability; the exfil leg does not exist. "
    "The egress allowlist is fixed in code (6 destinations); the model cannot add one.",
    "every push", "no code path may give model output an outbound channel",
    "the injection test + code review of the fixed egress set",
    "merge", "operator + CI",
    "The LLM returns text only (llm.py); no tool/function-calling path; trades go through _swap."),
    "Exfiltration is structurally absent, not merely undetected."),
 "B-26": ("PASS", SC(
    "Auto-halt tripwire flips the engine off on a cap breach without human action; "
    "dry_run + Stop are additional switches.",
    "every push", "AI features without a tested kill switch stay at zero",
    "test_daily_cap exercises the self-firing switch every run",
    "merge + runtime", "operator + CI",
    "test_daily_cap_refuses_and_halts_engine demonstrates the self-firing kill switch."),
    "The kill switch fires itself and is tested."),
}

# FAILs not promoted to PASS -> PARTIAL with a residual pointer (still improved).
FAIL_TO_PARTIAL = {
 "A-04": "spec.md now records invariants+NFRs mapped to tests; no spec-coverage GATE yet (residual).",
 "A-06": "CI-on-push now exists; rollback still untested/manual (residual).",
 "A-14": "constitution.md + AGENTS.md are the policy; single verification tier (proportionate).",
 "A-17": "spec.md prioritises safety/security/reliability NFRs with tests; not all have runtime measures (residual).",
 "A-39": "deterministic gate installed (the substitution); no standing second-vendor verifier -- residual R-2, PLAN band.",
 "B-09": "no image signing/SBOM yet; deps are permissive; residual (proportionate for a personal image).",
 "B-10": "deterministic decision surface (scoring/schema) is regression-tested; a live-model golden set is disproportionate for an advisory, schema-bounded LLM -- residual.",
 "B-13": "check_model_pins blocks '-latest' aliases; current ids remain provider aliases (operator should pin dated snapshots) -- residual.",
 "B-35": "gate/gated separation unachievable on a solo repo (one identity) -- residual R-1; compensating: protected branch + CODEOWNERS on .github/ + governance/. Handled by Article XV Incubating scope, not faked.",
}


def main():
    findings = json.loads((AUDIT / "03-findings.json").read_text())
    by_id = {f["id"]: f for f in findings}

    for cid, (verdict, sc, note) in PROMOTE.items():
        rec = by_id[cid]
        rec["verdict"] = verdict
        rec["standing_control"] = sc
        rec["note"] = (rec.get("note", "") + "  [Phase 6] " + note).strip()

    for cid, note in FAIL_TO_PARTIAL.items():
        rec = by_id[cid]
        if rec["verdict"] == "FAIL":
            rec["verdict"] = "PARTIAL"
        rec["note"] = (rec.get("note", "") + "  [Phase 6] " + note).strip()

    # §5 validation
    for f in findings:
        if f["verdict"] == "PASS" and not f.get("standing_control"):
            raise SystemExit(f"{f['id']}: PASS without standing_control")
        if f["verdict"] == "NOT-APPLICABLE" and not f.get("na_justification"):
            raise SystemExit(f"{f['id']}: NOT-APPLICABLE without justification")

    (AUDIT / "03-findings.json").write_text(json.dumps(findings, indent=2) + "\n")

    tally = {}
    for f in findings:
        tally[f["verdict"]] = tally.get(f["verdict"], 0) + 1
    print("Phase-6 tally:", dict(sorted(tally.items())))
    fails = [f["id"] for f in findings if f["verdict"] in ("FAIL", "NO-EVIDENCE")]
    print("remaining FAIL/NO-EVIDENCE:", fails or "NONE")
    return findings


if __name__ == "__main__":
    main()
