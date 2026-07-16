#!/usr/bin/env python3
"""Phase 0'/3'/6': activate catalogue v2.0 (the 40 Track C checks) and record
their verdicts against the Phase-0' baseline (commit under audit at Part 2).

Idempotent. Updates 00-check-catalogue.json (Track C -> active, version 2.0),
appends the 40 C records to 03-findings.json with evidence + standing controls,
and re-validates the §5 fail-closed invariants over all 119.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
AUDIT = ROOT / "audit"


def SC(mech, demo, owner="operator + CI", cadence="every push", blocks="merge"):
    return {"mechanism": mech, "cadence": cadence, "ratchet": "may not regress",
            "calibration": "seeded in gate_selftest/mutation where applicable",
            "blocks_on_breach": blocks, "owning_role": owner, "demonstrated": demo}


# id -> dict(v=verdict, p=probe, e=[evidence], sc=standing_control|None,
#            na=justification, note=...)
V = {
 "C-01": dict(v="PASS",
   p="Attacked the API: IDOR (single-user, no per-user objects -> N/A); tested authn on state-changing routes and the bind exposure.",
   e=["BASELINE FAIL: PUT /api/config, engine start/stop, run/{job}, test-connection were unauthenticated; any local process could flip dry_run or place trades (mitigated only by loopback bind).",
      "FIX: assert_safe_binding refuses non-loopback bind without a token (src/main.py); require_auth guards all state-changing routes when web.auth_token is set (src/web/app.py).",
      "IDOR/cross-tenant dimension is N/A: one principal, no per-user resources."],
   sc=SC("Bind-guard + bearer-token auth on every state-changing route; secret-scan + no-secrets-in-prompts in the gate.",
         "6 tests in test_web_auth.py: 401 without token, 200 with; bind-guard raises on 0.0.0.0 without token; reads/health stay open. Full suite 53 green.", "operator + CI", blocks="merge + deploy"),
   note="The one genuine STOP-SHIP that applies; fixed. Exposure beyond loopback without auth is now unrepresentable."),
 "C-04": dict(v="NOT-APPLICABLE",
   p="Followed the personal data: where it enters, is stored/copied, retained, and on what basis; tested erasure.",
   e=["The only personal data is the OPERATOR'S OWN: their exchange/LLM API keys + their own SMS recipient number, in gitignored config.json.",
      "No third-party data subjects; no customer data; no analytics; the LLM prompts carry market data + the operator's own portfolio values only.",
      "Erasure = delete config/config.json (+ .env). No derived PII stores (no DB, no vector store, no trace store)."],
   na="C-04's STOP-SHIP form governs processing of THIRD-PARTY personal data under GDPR's controller/processor/data-subject triangle. Here the operator is simultaneously the sole controller, processor and data subject, processing only their own data on their own self-hosted instance for their own purposes. No lawful-basis/DPIA/subject-access obligation to third parties arises. Re-banded off STOP-SHIP per the check's own 'otherwise re-band against the law that applies' clause. The only residual (operator's keys at rest) is tracked under B-06."),
 "C-02": dict(v="PARTIAL",
   p="Asked for the threat model; built it from the system as it stands (DFD + trust boundaries + STRIDE per boundary); asked what keeps it current.",
   e=["governance/security-notes.md: data-flow + trust boundaries (operator/UI, engine/exchange, engine/LLM, engine/TA/SMS) with a STRIDE enumeration mapped to controls.",
      "Every threat maps to a control or a documented acceptance; the fixed 6-destination egress allowlist is in code (a new one is a visible diff).",
      "No automated new-trust-boundary CI detector (proportionate); the standing-regime re-run triggers cover new integrations."],
   sc=None, note="Threat model built and version-controlled; the automated staleness detector is a residual, mitigated by the fixed in-code egress set + re-run triggers."),
 "C-03": dict(v="PASS",
   p="Enumerated deps; resolved each on PyPI; checked pinning + registration age; seeded a slopsquat (D3).",
   e=["All 9 runtime deps pinned and resolve on PyPI; all long-established (years old) -> no newly-registered/slopsquat risk.",
      "check_deps.py + pip-audit block on every push; D3 (fake package) caught (02-calibration.md).",
      "Poisoned-dependency playbook: governance/security-notes.md."],
   sc=SC("check_deps.py (existence+pin) + pip-audit (known-vuln) in the gate; playbook documented.",
         "gate_selftest D3 caught; pip-audit 'No known vulnerabilities'.")),
 "C-05": dict(v="PASS",
   p="Built the 10-category LLM-risk coverage matrix, mapping each to a control AND a test.",
   e=["governance/llm-risk-matrix.md: every category mapped to a control + an executable test; empty/test-less cells = none.",
      "Injection, output-handling, excessive-agency, consumption all carry tests in the gate."],
   sc=SC("Coverage matrix with a test per cell; CI runs the mapped tests.",
         "llm-risk-matrix.md complete; the mapped tests (injection, cap, masking, schema) pass in the 53-test suite.")),
 "C-06": dict(v="PASS",
   p="Walked all 10 agentic-risk categories against the architecture; checked whether any model can call a writing/spending tool.",
   e=["The LLM has NO tools (governance/capability-labels.json): it returns text; the deterministic engine acts. C-06 does NOT escalate to STOP-SHIP.",
      "Irreversible action (trade) is wrapped with a validator + blast-radius cap + auto-halt (A-34); not a bare irreversible capability.",
      "Categories tool-misuse/code-exec/inter-agent/memory-poisoning/rogue-agents are N/A (argued in llm-risk-matrix.md)."],
   sc=SC("Capability inventory (capability-labels.json) + trifecta test + the trading cap.",
         "test_no_session_holds_the_lethal_trifecta + test_llm_advisor_has_no_egress_or_tools pass; cap tests pass.")),
 "C-07": dict(v="PARTIAL",
   p="Attempted direct + indirect injection; assessed whether a successful injection can be consequential.",
   e=["Containment is ARCHITECTURAL: model has no tools/egress; output is schema-validated to {sell_buy,buy,sell,hold} on configured assets; the trading cap bounds consequence.",
      "test_injection_cannot_produce_out_of_schema_action pins it.",
      "Residual (a valid-but-wrong action) accepted in writing (security-notes.md) with the cap + dry-run + auto-halt as compensating control and tripwire."],
   sc=SC("Injection test + structural no-tools/no-egress + the cap tripwire; residual re-accepted on cadence.",
         "test_injection... passes; the cap tests fire the tripwire."),
   note="UNSETTLED DOCTRINE: no general injection defence exists; the durable mitigation here is architectural, and it holds because the model is an advisor, not an agent."),
 "C-08": dict(v="PASS",
   p="Labelled every session's legs {untrusted-input, private-data, external-communication}; searched for any holding all three.",
   e=["capability-labels.json: llm-advisor holds [untrusted-input] only (no egress); trade-engine holds [private-data, external-communication] but NOT untrusted-input (it acts on schema-validated output only).",
      "No session holds all three -> the trifecta cannot assemble."],
   sc=SC("The two-of-three rule asserted mechanically on every push; a capability completing the triangle fails the build.",
         "test_no_session_holds_the_lethal_trifecta passes; adding a third leg to any session fails it.")),
 "C-09": dict(v="PARTIAL",
   p="Inventoried the AI system(s) and classified the risk tier against the EU AI Act.",
   e=["One AI system: an LLM used as an internal decision advisor for the operator's own portfolio (security-notes.md).",
      "Classified NOT high-risk: not a listed high-risk use, personal/non-professional self-hosted use, no user-facing generative content -> Article 50 transparency does not bind. Does NOT hard-gate at 10."],
   sc=SC("Classification documented; re-run trigger fires on any move toward multi-user/market placement.",
         "security-notes.md classification; the standing-regime re-run trigger for multi-user is wired."),
   note="Inventory auto-generation is disproportionate for one system; classification is the deliverable."),
 "C-10": dict(v="PARTIAL",
   p="Asked what 'correct' means for the model path and whether an eval set gates changes.",
   e=["Deterministic decision surface (scoring/schema) is regression-tested + mutation-pinned.",
      "No golden eval set for the model's live judgment -> same residual as B-10 (disproportionate for an advisory, schema-bounded LLM)."],
   sc=None, note="Residual carried from B-10 (06-residual-risk-register)."),
 "C-11": dict(v="PARTIAL",
   p="Looked for a live risk-management programme emitting durable artifacts.",
   e=["The audit/ + governance/ trees ARE the durable artifacts, emitted/updated through the pipeline (not a one-off PDF).",
      "No formal governance charter (proportionate for solo); owning role = operator."],
   sc=None, note="Proportionate; artifacts are pipeline-emitted."),
 "C-12": dict(v="PASS",
   p="Split agency three ways (functionality/permissions/autonomy); checked the kill switch fires itself.",
   e=["Excessive functionality: model has no tools. Excessive permissions: single principal, keys operator-scoped (withdrawal-off advised). Excessive autonomy: bounded by the cap + auto-halt.",
      "Kill switch tested (test_daily_cap auto-halt)."],
   sc=SC("The trading cap + auto-halt + capability inventory; model has no tools.",
         "test_daily_cap_refuses_and_halts_engine; capability-labels.json.")),
 "C-13": dict(v="NOT-APPLICABLE", p="Checked whether an AI management system is claimed.",
   e=["No AMS (ISO/IEC 42001-style) is claimed anywhere."],
   na="The mandate: absence of an AMS is rarely fatal; an unsubstantiated claim is worse than none. No AMS is claimed, so there is nothing to substantiate. Dropped rather than asserted."),
 "C-14": dict(v="NOT-APPLICABLE", p="Looked for a place a model grades another model's output and gates on it.",
   e=["No model-judges-model gate exists. The LLM is the decision-maker; its output is validated DETERMINISTICALLY (schema), not judged by another model."],
   na="A judge is a model that scores another model's output to gate a decision. This system has no such judge -- the deterministic schema validation replaces judgement entirely (the mandate's preferred 'need the judge less'). Nothing to validate."),
 "C-15": dict(v="PARTIAL",
   p="Treated the schema-validation guardrail as an artifact needing its own adversarial tests.",
   e=["The guardrail (LLM-output schema validation) has tests incl. the adversarial injection test; it fails closed.",
      "No continuous automated red-team campaign (proportionate for a non-chat, schema-bounded surface)."],
   sc=None, note="Tested guardrail; continuous red-team disproportionate (residual)."),
 "C-16": dict(v="NOT-APPLICABLE", p="Inventoried non-human identities; checked for borrowed sessions.",
   e=["One principal (the operator). No per-agent identities, no service accounts, no agent-to-agent calls."],
   na="Machine-identity governance presupposes multiple non-human identities that could be over-scoped or borrow a human session. Here one process runs under the operator's own credentials; there is no agent identity plane to inventory or a human session to borrow."),
 "C-17": dict(v="NOT-APPLICABLE", p="Looked for tool definitions/descriptions the model is given.",
   e=["The model is given no tools and no tool descriptions; it receives a fixed prompt and returns text."],
   na="Tool poisoning requires tool definitions/descriptions read by the model. This model has none -- no function-calling, no MCP, no connectors. There is no tool description to poison."),
 "C-18": dict(v="NOT-APPLICABLE", p="Looked for external tool servers/connectors.",
   e=["No MCP servers, no connectors, no external tool servers. The only external calls are fixed REST endpoints in code."],
   na="Connector/tool-server security governs authenticated connections to external tool servers. There are none; the egress is a fixed 6-destination allowlist in code, not a pluggable tool-server surface."),
 "C-19": dict(v="NOT-APPLICABLE", p="Checked what can write to persistent agent memory / retrieved context.",
   e=["No persistent agent memory. The only cache is short-TTL TA/LLM JSON keyed by symbol, dry-run only, reproducible on expiry; it is never cross-session instruction state."],
   na="Memory/context poisoning requires persistent memory a later session reads as instruction. This system builds a fresh, bounded prompt each cycle and retains no cross-session memory. The cache holds market data, not instructions, and is per-symbol and short-lived."),
 "C-20": dict(v="PARTIAL",
   p="For each responsible-AI dimension, sought an owner, a measure, and a cadence.",
   e=["Most dimensions (fairness/bias) are N/A -- no decisions about people. Controllability: Stop + cap + dry-run. Robustness: cap + mutation + injection tests.",
      "Contestability: the operator controls every decision and can halt/override."],
   sc=None, note="Fairness/bias dimensions N/A (no human-affecting decisions); controllability/robustness covered by the cap + gate."),
 "C-21": dict(v="NOT-APPLICABLE", p="Looked for training/fine-tuning datasets.",
   e=["No custom or fine-tuned model; inference is against hosted APIs only."],
   na="Training/tuning-data governance applies only where a custom or fine-tuned model exists. All inference here is against hosted Anthropic/OpenAI models; no dataset is used to train or tune anything."),
 "C-22": dict(v="NOT-APPLICABLE", p="Tried to decompose wrong answers into retriever vs generator failure.",
   e=["No retriever/RAG exists; the prompt is built directly from TradingView indicators."],
   na="Retriever-vs-generator decomposition presupposes a retrieval step. There is none -- the model receives structured indicators built in code, not retrieved documents."),
 "C-23": dict(v="PARTIAL",
   p="Grepped the log/event surface for email/phone/national-id/card patterns.",
   e=["Logs + the in-memory event log carry the operator's own portfolio values, asset names, and job status -- no third-party PII, no card/SSN patterns.",
      "The SMS recipient (operator's own number) lives in config (masked in API responses), not in logs.",
      "secret_scan covers secrets in source; no separate runtime log-PII scanner (proportionate -- only operator's own data)."],
   sc=None, note="No third-party PII in logs; the only personal data is the operator's own."),
 "C-24": dict(v="PASS",
   p="Read the system prompt + templates; scanned for secrets/PII; checked whether any security rule lives in the prompt.",
   e=["SYSTEM_PROMPT = 'You are a crypto finance expert responding in JSON.' -- no secrets, no PII, no load-bearing security rule.",
      "All security controls are enforced in code (schema validation, cap, auth), not asked of the model."],
   sc=SC("test_no_secrets_or_pii_in_prompts + secret_scan cover the prompts on every push.",
         "test_no_secrets_or_pii_in_prompts passes; secret_scan scans src/prompts.py + src/llm.py.")),
 "C-25": dict(v="PARTIAL", p="Scanned deps + generated code for copyleft/reproduced snippets; sought an IP position.",
   e=["Deps are permissive; no copyleft conflict; no license-scan gate; no written IP position (residual, same as A-38)."],
   sc=None, note="Residual carried from A-38."),
 "C-26": dict(v="PARTIAL", p="Looked for an SBOM/AI-BOM and deploy-time provenance verification.",
   e=["No SBOM yet; pip-audit + check_deps cover the dependency risk; container unsigned (residual, same as B-09)."],
   sc=None, note="Residual carried from B-09/B-27."),
 "C-27": dict(v="NOT-APPLICABLE", p="Determined which compliance frameworks bind this product.",
   e=["No SOC2/ISO 27001 claimed; NO payment/card data handled (the exchange handles PCI, not this app); no health data."],
   na="C-27 audits only frameworks that genuinely bind. A personal self-hosted trading bot is subject to none: it makes no compliance claim, handles no cardholder data (orders go to the exchange's own PCI-scoped systems), and processes no health data. Nothing to evidence."),
 "C-28": dict(v="NOT-APPLICABLE", p="Traced where data physically lives incl. caches/logs/backups/inference region.",
   e=["Single self-hosted instance; the operator chooses the host. No multi-region stores, no vector store, no managed data plane."],
   na="Residency/regulatory-scope-by-design governs multi-region data placement. This is one container on hardware the operator picks; there is no store whose region could drift. The model provider's inference region is the operator's provider-account choice, documented as their decision."),
 "C-29": dict(v="NOT-APPLICABLE", p="Looked for a content-safety policy/taxonomy and generative-content surface.",
   e=["No user-generated content, no generative output distributed to third parties, no image/text generation surface."],
   na="Content-safety/misuse-prevention governs generative features exposed to users who could elicit harmful content. This system has no such surface -- the model produces internal JSON trade signals consumed only by the deterministic engine, never shown to or elicited by third parties."),
 "C-30": dict(v="PARTIAL", p="Considered jailbreak-to-consequence given no end-user prompt reaches the model.",
   e=["Not a chat surface: the model is called with fixed internal prompts; no end-user text reaches it.",
      "Jailbreak-to-consequence is bounded by the same architectural containment as injection (no tools, schema-bounded, capped). Residual accepted in security-notes.md with the cap as tripwire."],
   sc=None, note="UNSETTLED; bounded by architecture, not a chat surface."),
 "C-31": dict(v="PARTIAL", p="Mapped the threat model to named adversarial techniques/layers.",
   e=["security-notes.md maps boundaries to STRIDE + the injection/exfiltration/excessive-agency classes.",
      "No automated taxonomy-refresh (proportionate; PLAN band)."],
   sc=None, note="Coverage/vocabulary check; proportionate."),
 "C-32": dict(v="NOT-APPLICABLE", p="Checked vector-store access control / inversion / poisoning.",
   e=["No vector store, no embeddings anywhere in the system."],
   na="Vector/embedding weaknesses require an embedding store. There is none -- no RAG, no semantic search, no embeddings are computed or stored."),
 "C-33": dict(v="PARTIAL", p="Looked for an AI usage policy and whether it is enforced, not just published.",
   e=["governance/constitution.md + AGENTS.md are the policy; the machine-relevant clauses (permitted change classes, model pins, tool allowlist=none) are compiled into the CI gate.",
      "Cross-functional ownership N/A for a solo project."],
   sc=None, note="Policy exists and its machine-relevant clauses are gate-enforced; solo ownership."),
 "C-34": dict(v="PARTIAL", p="Checked provider training-on-data: contract AND configured state.",
   e=["Anthropic + OpenAI API terms do not train on API traffic by default; not asserted programmatically here.",
      "Residual: the operator should confirm the opt-out state in their provider accounts (documented in security-notes/residual)."],
   sc=None, note="Provider-default no-train; programmatic assertion is a residual (operator-in-command account setting)."),
 "C-35": dict(v="NOT-APPLICABLE", p="Checked for eval-set contamination / benchmark claims sent to a provider.",
   e=["No benchmark numbers are quoted anywhere; no held-out eval set exists to leak; no marketing/data-room claims."],
   na="Benchmark-contamination governs evaluation numbers used in claims. This system makes no benchmark claim and holds no eval set that could be contaminated or exfiltrated. 'Who evaluates the evaluator' is answered structurally: there is no model-judge (C-14 N/A) -- the deterministic gate does."),
 "C-36": dict(v="PARTIAL", p="Checked disclosure of machine-generated content + marking claims.",
   e=["The dashboard labels LLM-derived sentiment/recommendations as model output; no content is distributed to third parties, so machine-readable marking does not bind.",
      "security-notes.md states marking's limits (not overclaimed)."],
   sc=None, note="Internal-only output; disclosure present, marking N/A, limits documented."),
 "C-37": dict(v="PARTIAL", p="Asked whether any production line is reconstructible (model/prompt/spec/gate/tests/owner).",
   e=["Git history + commit provenance + the audit/ evidence tree form a reconstructible chain per commit; owning role = operator.",
      "No cryptographic signed-attestation chain (residual). Does NOT escalate to BLOCKER-1: git history provides the reconstructible chain the check requires."],
   sc=None, note="Git provenance is the chain; signing is a residual (shared with B-09)."),
 "C-38": dict(v="PARTIAL", p="Resolved every citation/link/identifier the system generates; found where a user acts on unverified output.",
   e=["The system generates no citations/links to users. Only schema-bounded action/confidence drive trades; the free-text 'reason' is displayed but never acted upon.",
      "Impact of a fabricated reason is bounded by schema validation + dry-run default + the trading cap."],
   sc=None, note="No citation surface; fabrication is contained (the reason text cannot cause a bad trade)."),
 "C-39": dict(v="NOT-APPLICABLE", p="Checked lifecycle/vocabulary-standard alignment (only material if an AMS is claimed).",
   e=["No AI management system is claimed (C-13 N/A)."],
   na="C-39 is material only where an AI management system is claimed. None is (C-13 N/A), so there is no lifecycle/terminology alignment claim to substantiate."),
 "C-40": dict(v="NOT-APPLICABLE", p="Assessed material societal/environmental impact.",
   e=["A few hosted-API calls per cycle for one user; no training, no high-QPS inference; no societal decision surface affecting people."],
   na="Societal/environmental impact is a gate only where material. This is a single-user bot making a handful of API calls every several minutes, with no decisions about people and an immaterial energy footprint. Documented as immaterial rather than assigned an invented number."),
}


def main():
    cat = json.loads((AUDIT / "00-check-catalogue.json").read_text())
    cat["catalogue_version"] = "2.0"
    cat["note"] = ("Catalogue v2.0: all 119 checks active. Track C activated by decision "
                   "record at Part 2 Phase 0'.")
    n_active = 0
    for c in cat["checks"]:
        if c["track"] == "C":
            c["scope_status"] = "active"
        if c["scope_status"] == "active":
            n_active += 1
    cat["active_check_count"] = n_active
    cat["planned_extension_count"] = 0
    (AUDIT / "00-check-catalogue.json").write_text(json.dumps(cat, indent=2) + "\n")

    CHECKS = {c["id"]: c for c in cat["checks"]}
    findings = json.loads((AUDIT / "03-findings.json").read_text())
    have = {f["id"] for f in findings}

    for cid, d in V.items():
        meta = CHECKS[cid]
        rec = {
            "id": cid, "title": meta["title"], "priority": meta["priority"],
            "band": meta["band"], "verdict": d["v"], "probe": d["p"],
            "evidence": d["e"], "note": d.get("note", ""),
            "structural_fix": meta["structural_fix"], "door": meta["door"],
            "conditional_escalation": meta.get("conditional_escalation"),
            "standing_control": d.get("sc"), "standing_control_plan": None,
        }
        if d["v"] == "NOT-APPLICABLE":
            rec["na_justification"] = d["na"]
        if cid in have:
            findings = [rec if f["id"] == cid else f for f in findings]
        else:
            findings.append(rec)

    # ---- §5 fail-closed validation over all 119 ----
    active = {c["id"] for c in cat["checks"] if c["scope_status"] == "active"}
    ids = [f["id"] for f in findings]
    assert set(ids) == active, f"findings != active: missing {active-set(ids)}, extra {set(ids)-active}"
    assert len(ids) == len(set(ids)) == 119, f"expected 119 unique, got {len(ids)}"
    for f in findings:
        assert f["verdict"] != "NO-EVIDENCE", f"{f['id']} still NO-EVIDENCE"
        if f["verdict"] == "PASS":
            assert f.get("standing_control"), f"{f['id']} PASS without standing_control"
        if f["verdict"] == "NOT-APPLICABLE":
            assert f.get("na_justification"), f"{f['id']} NA without justification"

    (AUDIT / "03-findings.json").write_text(json.dumps(findings, indent=2) + "\n")
    tally = {}
    for f in findings:
        tally[f["verdict"]] = tally.get(f["verdict"], 0) + 1
    ctally = {}
    for f in findings:
        if f["id"].startswith("C-"):
            ctally[f["verdict"]] = ctally.get(f["verdict"], 0) + 1
    print("Track C tally:", dict(sorted(ctally.items())))
    print("Full 119 tally:", dict(sorted(tally.items())))


if __name__ == "__main__":
    main()
