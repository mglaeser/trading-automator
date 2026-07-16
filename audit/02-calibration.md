# 02 — Pipeline Calibration (Phase 2)

**The first execution of a permanent instrument (§9.3), not a one-off measurement.** Six
clonally-representative defects were seeded one at a time on a scratch branch
(`calibration-scratch`, since deleted), the only automated gate this system has was run
over each, and the catch rate recorded. The seed set becomes the standing calibration
corpus; the pipeline's number becomes the S11 baseline that may never fall.

Harness: `scripts/` + scratchpad `calibrate.py` (applies one defect, runs `pytest -q`,
records red/green, reverts via `git checkout`). Baseline clean suite: **38 passed, ~2.1s**.
Post-run revert verified clean (38 passed).

## What "the pipeline" is here

There is **one** automated gate: `pytest`, and **nothing runs it automatically** — no CI,
no pre-commit, no branch protection (see `00-system-map.md §7`). So "the pipeline's catch
rate" is literally "what a human remembering to type `pytest` would catch." That framing
is the finding, not a footnote.

## The six seeded defects and what the pipeline caught

| Defect (class) | How seeded (adapted to this single-user system) | Pipeline (pytest) | Why |
|---|---|---|---|
| **D1** hard-coded credential | `sk-ant-…` literal added to `src/llm.py` | **MISSED (green)** | No secret scanner exists. `pytest` does not read source for secrets. |
| **D2** broken safety/authorization guard | `sell_all_crypto` universe guard removed → sells *any* held asset (single-user analogue of a missing ownership check) | **CAUGHT (red)** | `test_sell_all_only_configured_crypto` asserts only `{BTC,BNB}` are sold. |
| **D3** non-existent (slopsquat) dependency | `tradingview-ta-helper==0.4.2` appended to `requirements.txt` | **MISSED (green)** | No dependency-existence / SCA check. The suite never installs or resolves it. |
| **D4** swallowed exception on a consequential path | order placement wrapped in `try/except: return None` | **MISSED (green)** | No lint for bare/broad excepts; no test asserts the swap raises on failure. |
| **D5** vacuous assertion | new test `assert result or True` | **MISSED (green)** | The suite *grew* (39 passed). A suite cannot detect its own weakness — that is what mutation testing is for, and there is none. |
| **D6** unvalidated model output → action | LLM `action` schema check disabled | **CAUGHT (red)** | `test_swap_evaluation_rejects_bad_action` asserts an `{"error"}` on a bad action. |

## The three catch rates — and which one matters

| Instrument | Catch rate | Honest status |
|---|---|---|
| **The pipeline** (pytest, by hand) | **2 / 6** | The only number that survives the auditor's departure. **This is the system's real safety margin, and it is 0.33.** |
| **Independent adversarial verifier** (S2: different model, different vendor, "break it") | **not available** | A solo, self-hosted project has **no second-vendor model wired as a standing verifier.** As a same-model-family inspection pass an adversarial reader catches all six — but that is exactly the self-reference §1 Rule 7 forbids counting. Recorded as a **structural residual** (see `06-residual-risk-register.md` / `07-substitution-ledger.md`), never as a passing control. |
| **My own review** | 6 / 6 by inspection | Interesting, not load-bearing. I am temporary and share the blind spots of the generator (§1 Rule 6). |

## The verdict the mandate forces (Phase 2)

> "If the existing pipeline caught fewer than five of six, then a green build in this
> repository is not evidence of anything, and — since there is no reviewer downstream of
> that build — **the system currently has no verification at all.** Say that in the first
> sentence of the executive summary."

**It caught two of six.** That sentence therefore leads `09-executive-summary.md`.

Under §3 conditional escalations, this measurement is what converts several checks to
`STOP-SHIP`:
- **A-01 + A-39** (no deterministic gate *and* no independent verifier) → both `STOP-SHIP`.
- **A-02** (the suite's inability to detect injected faults, confirmed by D4/D5) →
  `STOP-SHIP`-eligible; mutation testing must be installed and shown to catch D5's class.
- **A-36** (pipeline catch rate not measured on a continuing basis) → `BLOCKER-1` until the
  injection becomes a standing, scheduled instrument.

## Baseline recorded for S11 (the ratchet)

| Metric | Baseline (Phase 2) | Direction | Target after Phase 5 |
|---|---|---|---|
| Pipeline seeded-defect catch rate | **2/6 = 0.33** | may only rise | **6/6** once secret-scan (D1), dependency-existence (D3), broad-except lint (D4) and mutation-on-core (D5) gates are installed and shown to catch their seeds |
| Independent-verifier catch rate | not measurable (no S2) | — | remains a residual; compensated by a deterministic gate that needs no model opinion |

The corpus (`D1…D6`) is retained as the founding standing calibration set. Every defect
found later in this engagement, and every future incident, is added to it (§9.3). Phase 5
installs the gates that raise 2/6 toward 6/6 and re-runs this exact harness as the proof
(`05-verification.md`).
