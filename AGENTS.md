# AGENTS.md — instructions for any agent working in this repository

This repository is maintained by AI agents with a human **in command** (the operator), not
in the loop. Before you change anything, load `governance/constitution.md` and the
invariants in `governance/spec.md`. This file is the paved road.

## The one rule that outranks the others
A request — even from the operator — does not bypass the gate. If a change would breach an
invariant (disable a gate, remove/weaken the trading cap, flip a fail-closed path to
fail-open, commit a secret, widen the blast radius), **stop before implementing** and issue
the constitutional alert (`governance/constitution.md`, Article XIV). Do not implement "with
a caveat."

## Setup (one command each)
```bash
pip install -r requirements-dev.txt      # runtime + gate tooling (ruff, pip-audit)
python -m pytest -q                       # 42 tests, in-memory fake exchange, no network
python -m src.main                        # web UI on http://localhost:8000
```

## The gate you must pass (CI runs all of this; run it locally before you push)
```bash
python -m ruff check src tests            # A-08/A-13/A-26 — coding standard, broad-except
python -m pytest -q                       # A-02 backstop
python scripts/mutation_smoke.py          # A-02/S4 — the suite must kill injected core faults
python scripts/check_deps.py              # B-04 — every dep pinned + exists on PyPI
python -m pip_audit -r requirements.txt --strict   # A-08 — no known-vuln deps
python scripts/secret_scan.py --history   # B-06 — no secrets, head or history
python scripts/check_model_pins.py        # B-13 — no floating model aliases
python scripts/gate_selftest.py           # A-36 — seeded defects D1..D6 still caught
python scripts/policy_gate.py --merge      # S1 — fail-closed on open blockers
```
A change that reduces `mutation_smoke` or `gate_selftest` catch counts, or adds a
suppression, is a regression and must not merge.

## The invariants you must not break (see governance/spec.md for the tests that pin them)
1. **Only configured-universe assets are traded.** `trading.assets` is the allowlist.
2. **The LLM is an advisor with no tools.** It returns schema-validated JSON; off-schema is
   a no-signal. It cannot act, spend, or egress. Do not give the model tool-use without
   re-running the injection/agentic checks (this would complete the lethal trifecta).
3. **Every trade goes through `engine._swap`**, which enforces the blast-radius cap. Never
   add a code path that calls `client.swap()` directly.
4. **Secrets are masked in every API response** and never committed.
5. **`dry_run` defaults on; an explicit Stop persists.** Nothing silently flips to live.

## Prompts are code
The two prompts live in `src/prompts.py` as constants — there is no runtime hot-swap path,
by design. Change them like code (they ride the gate); a behaviour-altering prompt change
should update the golden-eval fixture.

## Going live (operator, in-command — the one human decision)
1. Run in dry-run for at least a full day/night cycle; read the activity log (Copy-all).
2. Confirm exchange keys are **withdrawal-disabled and IP-pinned**.
3. Set `max_swap_value` / `daily_trade_cap` deliberately (defaults are conservative).
4. Only then switch `dry_run` off. The cap and auto-halt still apply.

## Where things are
- Audit + evidence: `audit/` (findings `audit/03-findings.json`, status
  `audit/engagement-status.json` — the deploy gate reads this).
- Governance: `governance/constitution.md`, `governance/spec.md`, `governance/mandate/`.
- Gate scripts: `scripts/`. Trading cap: `src/engine.py::_swap`/`_halt`.
