#!/usr/bin/env python3
"""Generate the machine-readable Phase-0 catalogue artifacts.

Emits, deterministically (no timestamps, no randomness):

  audit/00-check-catalogue.json   the 119-check master index (79 active v1.0,
                                  40 Track C registered as planned-extension)
  audit/03-findings.json          initialised from the active scope: exactly 79
                                  NO-EVIDENCE records (overwritten in place as
                                  evidence lands during Phase 3)

This is the manifest/master-index only -- it never restates the normative check
text, which lives in governance/mandate/. Re-running it is safe: it rebuilds the
catalogue and (re)initialises only findings that do not yet carry evidence.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
AUDIT = ROOT / "audit"

# (id, title, priority) grouped by track. Priorities and titles are the
# founding, immutable values from the mandate catalogue (v1.0 for A/B).
TRACK_A = [
    ("A-01", "The verification gate on every production change", 9),
    ("A-02", "A test suite that can actually fail", 9),
    ("A-03", "Deterministic and probabilistic assertions kept apart", 6),
    ("A-04", "A specification exists, is testable, has non-goals, gates merges", 8),
    ("A-05", "Domain boundaries and a consistent vocabulary", 7),
    ("A-06", "Version control, batch size and a rollback that has been executed", 9),
    ("A-07", "Clone, churn and refactoring signature", 7),
    ("A-08", "Security scanning is the control, not a first pass before one", 9),
    ("A-09", "Architecture as decided, not as accreted", 8),
    ("A-10", "Injection-resistant architecture, not injection-resistant wording", 8),
    ("A-11", "Least-privilege topology for every agent and tool (design)", 7),
    ("A-12", "Technical debt and the comprehension problem", 7),
    ("A-13", "Enforced coding standards", 7),
    ("A-14", "A written policy for how AI builds and maintains this", 6),
    ("A-15", "The boundary between prototype and production", 5),
    ("A-16", "The last mile: stubs, edge cases and integration", 6),
    ("A-17", "Non-functional requirements, specified and measured", 8),
    ("A-18", "Model and agent architecture chosen deliberately", 7),
    ("A-19", "API contracts that match the implementation", 7),
    ("A-20", "Prompts and retrieval configuration are code, pass the same gate", 6),
    ("A-21", "Context, retrieval and memory architecture", 7),
    ("A-22", "User outcomes, performance and accessibility", 8),
    ("A-23", "Data architecture and ownership", 7),
    ("A-24", "The system operates and recovers itself", 9),
    ("A-25", "Input validation at every boundary", 8),
    ("A-26", "Error handling that does not lie", 7),
    ("A-27", "Non-functional requirements that are specific to AI", 7),
    ("A-28", "Dependency topology and blast radius", 7),
    ("A-29", "Build versus buy versus open source -- including the model", 6),
    ("A-30", "Non-functional trade-offs analysed, not stumbled into", 6),
    ("A-31", "Unit economics decided at design time", 6),
    ("A-32", "Documentation that is true -- and executable", 7),
    ("A-33", "Maintainability without a maintainer", 8),
    ("A-34", "Autonomy levels, deterministic gates and a kill switch that fires itself", 8),
    ("A-35", "Runtime containment without an operator", 6),
    ("A-36", "Calibration of the verification pipeline", 6),
    ("A-37", "Takeover readiness", 5),
    ("A-38", "Provenance and licensing of the code that shipped", 7),
    ("A-39", "The verification loop must not be self-referential", 5),
    ("A-40", "Energy and carbon as a design constraint", 4),
]

TRACK_B = [
    ("B-01", "The pipeline actually gates", 9),
    ("B-02", "A paved road an agent can walk", 8),
    ("B-03", "Observability that reaches root cause", 9),
    ("B-04", "Dependencies that exist, are pinned, and were vetted", 9),
    ("B-05", "Models, prompts and agents have a lifecycle", 8),
    ("B-06", "Secrets and machine identity", 10),
    ("B-07", "Every model and agent run is traceable and replayable", 8),
    ("B-08", "No path may consume unbounded tokens or money", 7),
    ("B-09", "Signed provenance for everything shipped, including models", 7),
    ("B-10", "Evaluation gates in the pipeline", 8),
    ("B-11", "Rollback for code, prompts and models", 9),
    ("B-12", "Runtime defence", 8),
    ("B-13", "Pinned model versions -- no floating aliases", 8),
    ("B-14", "Governance over prompt and configuration changes", 6),
    ("B-15", "Guardrails are deployed artifacts, and they fail closed", 8),
    ("B-16", "Cost attribution and financial operations", 6),
    ("B-17", "Infrastructure as code, reconciled from version control", 7),
    ("B-18", "Progressive delivery with an automatic abort", 6),
    ("B-19", "Service objectives with an error budget that bites", 7),
    ("B-20", "Runtime detection and containment of injection and exfiltration", 9),
    ("B-21", "The application survives a provider outage", 6),
    ("B-22", "Agents deployed with least privilege, enforced", 9),
    ("B-23", "Behavioural baselines for agents, with automatic containment", 7),
    ("B-24", "Quality drift detection", 7),
    ("B-25", "Environment separation and parity", 7),
    ("B-26", "Feature flags and kill switches that fire themselves", 6),
    ("B-27", "Artifact integrity", 7),
    ("B-28", "Detection that triggers action, not just a notification", 8),
    ("B-29", "Reliability primitives, validated by breaking things", 7),
    ("B-30", "Capacity, including inference capacity", 6),
    ("B-31", "Backups you have actually restored", 8),
    ("B-32", "Drift detection", 5),
    ("B-33", "Integrity of the retrieval corpus", 7),
    ("B-34", "Latency budgets for inference", 5),
    ("B-35", "Release governance: segregate the gate from the gated", 6),
    ("B-36", "Model deprecation is a plan, not an outage", 6),
    ("B-37", "Retirement of AI artifacts and the right to erasure", 5),
    ("B-38", "Inference economics", 4),
    ("B-39", "Design against a named reference framework", 5),
]

TRACK_C = [
    ("C-01", "Core application security", 10),
    ("C-02", "Threat model", 8),
    ("C-03", "Supply-chain security and hallucinated packages", 9),
    ("C-04", "Privacy and data governance", 10),
    ("C-05", "The LLM application risk taxonomy, mapped and tested", 9),
    ("C-06", "The agentic risk taxonomy", 8),
    ("C-07", "Prompt injection", 9),
    ("C-08", "The dangerous three: never combine all of them", 8),
    ("C-09", "EU AI Act", 9),
    ("C-10", "Evaluation methodology", 8),
    ("C-11", "A running AI risk-management programme", 7),
    ("C-12", "Excessive agency and the autonomy policy", 7),
    ("C-13", "AI management system", 6),
    ("C-14", "Validating the judge", 6),
    ("C-15", "Guardrails have their own tests, and their own adversary", 7),
    ("C-16", "Machine identity and agent-to-agent trust", 7),
    ("C-17", "Tool poisoning", 7),
    ("C-18", "Connector and tool-server security", 7),
    ("C-19", "Memory and context poisoning", 6),
    ("C-20", "Responsible-AI dimensions with owners and numbers", 6),
    ("C-21", "Training and fine-tuning data governance", 7),
    ("C-22", "Retrieval evaluated separately from generation", 7),
    ("C-23", "Personal data in prompts, logs and traces", 8),
    ("C-24", "Disclosure through memorisation and system-prompt leakage", 7),
    ("C-25", "Copyright and licensing of generated code", 6),
    ("C-26", "SBOM, AI-BOM, provenance and cyber-resilience obligations", 8),
    ("C-27", "Sector compliance baseline", 9),
    ("C-28", "Residency and regulatory scope decided at design time", 7),
    ("C-29", "Content safety and misuse prevention", 6),
    ("C-30", "Jailbreak resistance", 6),
    ("C-31", "Adversarial technique taxonomy and agentic threat layers", 5),
    ("C-32", "Vector and embedding weaknesses", 6),
    ("C-33", "An AI usage policy that is enforced, not merely published", 6),
    ("C-34", "Provider training on your data -- check the contract and the switch", 7),
    ("C-35", "Benchmark contamination and who evaluates the evaluator", 4),
    ("C-36", "Transparency and marking of generated output", 6),
    ("C-37", "Accountability without a signature", 5),
    ("C-38", "Fabrication and the downstream reliance on it", 6),
    ("C-39", "Lifecycle process and vocabulary standards", 4),
    ("C-40", "Societal and environmental impact", 3),
]

BAND_BY_PRIORITY = {
    10: "STOP-SHIP", 9: "BLOCKER-1", 8: "BLOCKER-2", 7: "MUST-FIX",
    6: "SHOULD-FIX", 5: "PLAN", 4: "ASSESS", 3: "ASSESS",
}

# The 44 checks that carry a Structural fix (S13) field, mapped to their door.
DOORS = {
    "tenancy-in-dal": ["C-01", "A-07"],
    "tool-gateway": ["A-11", "A-34", "B-08", "B-22", "C-06", "C-08", "C-12", "C-17"],
    "model-gateway": ["A-29", "A-31", "B-13", "B-16", "B-34", "B-36", "B-38", "C-34"],
    "telemetry-emitter": ["B-07", "C-23", "C-24"],
    "prompt-registry": ["A-20", "B-05", "B-14"],
    "derived-store-registry": ["B-37", "C-04", "C-28", "C-32"],
    "guarded-outbound-client": ["A-28"],
    "policy-bundle-separation": ["B-35"],
    "agent-split": ["B-20", "C-07"],
    "heldout-eval-store": ["B-10", "C-35"],
    "credential-broker": ["B-25", "C-16"],
    "module-visibility": ["A-05", "A-09"],
    "functional-core-shell": ["A-02"],
    "deletion": ["A-12"],
    "generate-both-sides": ["A-19"],
    "strangler-refactor": ["A-06"],
    "generate-inventory": ["C-02", "C-09"],
}
DOOR_OF = {}
for door, ids in DOORS.items():
    for cid in ids:
        DOOR_OF.setdefault(cid, door)
# C-08 belongs to both tool-gateway and agent-split; note the primary door.

STRUCTURAL_FIX_IDS = set(DOOR_OF) | {"C-08"}

# Conditional escalations from §3 that are live in THIS system.
CONDITIONAL = {
    "A-01": "STOP-SHIP if A-39 also fails (no deterministic gate AND no independent verifier)",
    "A-02": "STOP-SHIP if mutation testing shows the suite cannot detect injected faults",
    "A-36": "BLOCKER-1 if the pipeline catch rate is not measured on a continuing basis",
    "A-39": "STOP-SHIP if A-01 also fails",
    "B-35": "STOP-SHIP if any code-writing agent can write to the policy bundle that gates it",
    "C-06": "priority 10 / STOP-SHIP if any model can call a tool that writes/sends/spends/deletes/executes",
    "C-37": "BLOCKER-1 if any production component has no attested provenance chain",
    "C-04": "STOP-SHIP where EU personal data is processed; else re-band against the law that applies",
    "C-09": "hard gate at 10 if anything is high-risk on the EU market",
}


def build():
    checks = []
    order_in_band = {}
    for track, rows, volume, scope in (
        ("A", TRACK_A, "part1", "active"),
        ("B", TRACK_B, "part1", "active"),
        ("C", TRACK_C, "part2", "planned-extension"),
    ):
        for cid, title, prio in rows:
            band = BAND_BY_PRIORITY[prio]
            order_in_band[band] = order_in_band.get(band, 0) + 1
            checks.append({
                "id": cid,
                "title": title,
                "track": track,
                "volume": volume,
                "priority": prio,
                "band": band,
                "within_band_order": order_in_band[band],
                "structural_fix": cid in STRUCTURAL_FIX_IDS,
                "door": DOOR_OF.get(cid),
                "conditional_escalation": CONDITIONAL.get(cid),
                "scope_status": scope,
            })

    active = [c for c in checks if c["scope_status"] == "active"]
    planned = [c for c in checks if c["scope_status"] != "active"]

    catalogue = {
        "catalogue_version": "1.0",
        "note": ("Master index only -- navigation/validation, never a restatement "
                 "of normative check text (see governance/mandate/). Track C's 40 "
                 "checks are registered as planned-extension:part2, activated as "
                 "catalogue v2.0 when Part 2 opens."),
        "registered_check_count": len(checks),
        "active_check_count": len(active),
        "planned_extension_count": len(planned),
        "required_check_ids": [c["id"] for c in checks],
        "checks": checks,
    }
    (AUDIT / "00-check-catalogue.json").write_text(
        json.dumps(catalogue, indent=2) + "\n")

    # Initialise findings from the ACTIVE scope only: 79 NO-EVIDENCE records.
    # Preserve any record that already carries evidence (idempotent re-run).
    findings_path = AUDIT / "03-findings.json"
    existing = {}
    if findings_path.exists():
        for rec in json.loads(findings_path.read_text()):
            if rec.get("verdict") != "NO-EVIDENCE":
                existing[rec["id"]] = rec

    findings = []
    for c in active:
        if c["id"] in existing:
            findings.append(existing[c["id"]])
            continue
        findings.append({
            "id": c["id"],
            "title": c["title"],
            "priority": c["priority"],
            "band": c["band"],
            "verdict": "NO-EVIDENCE",
            "probe": None,
            "evidence": [],
            "standing_control": None,
        })
    findings_path.write_text(json.dumps(findings, indent=2) + "\n")

    return len(checks), len(active), len(planned), len(findings)


if __name__ == "__main__":
    total, active, planned, nfind = build()
    print(f"catalogue: {total} checks ({active} active v1.0, {planned} planned-extension)")
    print(f"findings initialised: {nfind} records "
          f"({sum(1 for _ in range(nfind))} NO-EVIDENCE on first build)")
