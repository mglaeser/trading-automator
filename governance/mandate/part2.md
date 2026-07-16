# Due-Diligence and Remediation Mandate — Part 2 of 2

**STATUS: NOT YET DELIVERED.**

Part 2 carries Track C (Security, Privacy and Assurance — 40 checks, catalogue v2.0) and
the engagement's terminal Definition of Done. It executes strictly after Part 1 closes, as
a pre-planned additive extension: same rules, same schema, same regime, same constitution
(amended and re-ratified with Track C's measured baselines).

Until Part 2 is delivered and executed:
- the 40 Track C checks are registered in `audit/00-check-catalogue.json` as
  `planned-extension: part2`;
- `audit/engagement-status.json` holds `security_scope_audited: false` and
  `production_eligible: false`;
- the deploy-admission gate (`scripts/policy_gate.py`) fails closed on that file.

This placeholder is replaced with the delivered Part 2 text when it arrives; the manifest
hash is recomputed and the constitution re-ratified at v2.0 (Part 2 Phase 7).
