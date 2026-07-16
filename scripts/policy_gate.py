#!/usr/bin/env python3
"""The deterministic policy gate (S1, Article I).

Reads the audit findings + engagement status and decides, with no model opinion:
  --merge  (default): FAIL if any active STOP-SHIP/BLOCKER-1/BLOCKER-2 record is
           un-remediated (verdict FAIL or NO-EVIDENCE), or any PASS lacks a
           standing control, or the fail-closed findings-set invariants (§5) break.
           A PARTIAL blocker (remediated, carrying a documented residual) may merge.
  --deploy: additionally requires production_eligible == true.

There is no override path. Exit 0 = allowed, 1 = blocked.
"""
import json
import pathlib
import sys

AUDIT = pathlib.Path(__file__).resolve().parent.parent / "audit"
BLOCKER_BANDS = {"STOP-SHIP", "BLOCKER-1", "BLOCKER-2"}


def eff_band(f, verdicts):
    """Apply the live §3 conditional escalations to a record's band.
    A-01+A-39 escalate to STOP-SHIP only when BOTH are unresolved (neither a
    deterministic gate nor an independent verifier exists)."""
    cid, v = f["id"], f["verdict"]
    ok = ("PASS", "NOT-APPLICABLE")
    a01, a39 = verdicts.get("A-01"), verdicts.get("A-39")
    if cid == "A-01" and v not in ok and a39 not in ok:
        return "STOP-SHIP"
    if cid == "A-39" and v not in ok and a01 not in ok:
        return "STOP-SHIP"
    if cid == "A-02" and v not in ok:
        return "STOP-SHIP"
    if cid == "A-36" and v not in (*ok, "PARTIAL"):
        return "BLOCKER-1"
    return f["band"]


def main():
    deploy = "--deploy" in sys.argv
    findings = json.loads((AUDIT / "03-findings.json").read_text())
    catalogue = json.loads((AUDIT / "00-check-catalogue.json").read_text())
    status = json.loads((AUDIT / "engagement-status.json").read_text())
    active = {c["id"] for c in catalogue["checks"] if c["scope_status"] == "active"}
    verdicts = {f["id"]: f["verdict"] for f in findings}

    fail = []

    # §5 fail-closed findings-set invariants
    ids = [f["id"] for f in findings]
    if set(ids) != active:
        fail.append(f"findings set != active scope (missing {active - set(ids)}, "
                    f"extra {set(ids) - active})")
    if len(ids) != len(set(ids)):
        fail.append("duplicate finding records")

    # blocker + standing-control checks
    for f in findings:
        band = eff_band(f, verdicts)
        if band in BLOCKER_BANDS and f["verdict"] in ("FAIL", "NO-EVIDENCE"):
            fail.append(f"{f['id']} ({band}) is open: verdict {f['verdict']}")
        if f["verdict"] == "PASS" and not f.get("standing_control"):
            fail.append(f"{f['id']} is PASS with a null standing_control (must be PARTIAL)")

    if deploy and not status.get("production_eligible", False):
        fail.append(f"production_eligible is false: {status.get('production_eligible_reason')}")

    mode = "DEPLOY" if deploy else "MERGE"
    if fail:
        print(f"POLICY GATE ({mode}): BLOCKED")
        for x in fail:
            print("  -", x)
        return 1
    print(f"POLICY GATE ({mode}): PASS")
    if not deploy:
        print("  (note: production admission still blocked -- Part 2 security scope "
              "unaudited; run with --deploy to confirm.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
