"""Track C structural security invariants, asserted mechanically in the gate.

- C-08 lethal trifecta: no session holds all of {untrusted-input, private-data,
  external-communication}. Adding a capability that completes the triangle fails.
- C-06/C-08: the LLM advisor has no egress/tool capability (it can only return
  text) — the exfil leg is structurally absent.
- C-24: no secrets or PII in the system prompt or prompt templates.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
LEGS = {"untrusted-input", "private-data", "external-communication"}


def test_no_session_holds_the_lethal_trifecta():
    labels = json.loads((ROOT / "governance/capability-labels.json").read_text())
    for s in labels["sessions"]:
        legs = set(s["legs"])
        assert legs <= LEGS, f"{s['name']}: unknown leg {legs - LEGS}"
        assert legs != LEGS, f"{s['name']} holds all three legs (C-08 breach)"
        assert len(legs) <= 2, f"{s['name']} holds {len(legs)} legs"


def test_llm_advisor_has_no_egress_or_tools():
    # The advisor session must declare no tools and must not hold the
    # external-communication leg -- its only output is text.
    labels = json.loads((ROOT / "governance/capability-labels.json").read_text())
    advisor = next(s for s in labels["sessions"] if s["name"] == "llm-advisor")
    assert advisor["tools"] == []
    assert "external-communication" not in advisor["legs"]

    # And the code backs the label: LLMClient exposes no send/post/egress method.
    from src.llm import LLMClient
    forbidden = {"send", "post", "get", "request", "egress", "write", "upload"}
    methods = {m for m in dir(LLMClient) if not m.startswith("__")}
    leaked = methods & forbidden
    assert not leaked, f"LLMClient exposes egress-shaped methods: {leaked}"


def test_no_secrets_or_pii_in_prompts():
    import re

    from src import prompts
    from src.llm import SYSTEM_PROMPT

    blob = SYSTEM_PROMPT + prompts.__doc__ + "".join(
        v for v in vars(prompts).values() if isinstance(v, str)
    )
    secret_like = re.compile(r"sk-ant-|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN")
    pii_like = re.compile(r"\b[\w.]+@[\w.]+\.\w+\b|\b\d{3}-\d{2}-\d{4}\b")
    assert not secret_like.search(blob), "secret pattern in a prompt"
    assert not pii_like.search(blob), "PII pattern in a prompt"
