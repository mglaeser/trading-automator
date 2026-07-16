# 00 — System Map (Phase 0 freeze)

> **Commit under audit:** `840e4f446409bca09d470e1d34a72181030f68b6`
> **Branch:** `claude/nexo-binance-etoro-refactor-3nw88j` · working tree clean · 4 commits total
> **Catalogue:** v1.0 (79 active Track A/B checks; 40 Track C checks registered as `planned-extension:part2`)
> **Frozen:** 2026-07-16. No source change was made before this freeze except read-only inspection.

This is the denominator of the engagement. Every item below is cross-referenced in
`00-audit-surface.json`; Phase 3 must prove every surface item was touched by at least
one check (`03b-coverage-ledger.md`).

---

## 0. What this system actually is — and why the catalogue must be re-scoped, not recited

The mandate is written for an enterprise, multi-tenant, multi-agent AI product. **This
system is not that.** Getting the audit right starts with saying precisely what it *is*,
because Rule 4 requires every `NOT-APPLICABLE` to be argued from the real architecture,
not inferred from a missing file.

`trading-automator` is a **single-user, self-hosted crypto portfolio bot**, ~2,940 LOC of
Python across 15 source modules, that:

- reads balances from **one** exchange (Binance *or* eToro) using **the operator's own**
  API keys;
- pulls TradingView technical indicators for a fixed asset universe;
- asks an **LLM** (Anthropic primary, OpenAI fallback) to score asset pairs and overall
  market sentiment — the LLM returns **schema-validated JSON only and calls no tools**;
- a **deterministic engine** consumes that JSON and decides trades;
- executes market orders / opens-closes positions on the exchange **when `dry_run` is
  off** (default on);
- serves a **no-auth web UI bound to `127.0.0.1`** for configuration and monitoring.

Three architectural facts drive the entire re-scoping:

1. **There is exactly one principal — the operator.** No tenants, no end users, no
   per-user data, no login. Whole classes of the catalogue (cross-tenant IDOR, tenant
   isolation, per-user erasure) are `NOT-APPLICABLE` by architecture, and that will be
   argued check by check in Part 2.
2. **The LLM is an advisor, not an agent.** It has **no tool-use, no function-calling, no
   code execution, no memory, no retrieval corpus**. It cannot introduce an egress
   destination, spend money, delete, or execute. The "agentic" catalogue (tool gateways,
   capability labels, the lethal trifecta) mostly collapses — but *not* to nothing: the
   engine downstream of the LLM **can** place irreversible real-money trades, and that is
   where the real blast radius lives (A-11, A-34; C-06 in Part 2).
3. **The verification gate the entire operating model rests on does not exist.** There is
   no CI, no branch protection, no policy bundle, no independent verifier, no mutation
   testing. There is a 38-test pytest suite that **nothing runs automatically.** Under the
   §3 conditional escalations this is the load-bearing finding of the engagement
   (A-01, A-02, A-39, B-01).

**Repository class (Article XV):** `production-capable, solo-operated`. It is *not*
Experimental (it holds real exchange credentials and can move real money) and it cannot
honestly be full Production (a solo operator cannot stand up a second-vendor Verifier
fleet, an always-on Runner with a dead-man switch, or a policy bundle in a separate repo
under a separate identity). The engagement therefore installs the **Incubating**-tier
apparatus that a one-person project can actually sustain and keep true — a real CI gate,
secret/dependency/lint scanning, mutation on core logic, a trading blast-radius cap — and
records every enterprise control that is structurally out of reach as an explicit
residual with a compensating control and a tripwire (§10 economization license; never a
faked green tick).

---

## 1. Environments

| Environment | Reality |
|---|---|
| **Runtime** | One podman container (`deploy.sh` / `compose.yaml`) **or** bare `python -m src.main`. `python:3.12-slim` base image; local dev host observed running **Python 3.11.15**. |
| **Dev vs prod** | **No separation.** The operator runs the same image. There is no staging data plane. The only "safe mode" is `dry_run: true` (default), which computes every decision and logs it but sends no order. |
| **Network exposure** | Web UI bound to `127.0.0.1:${PORT:-8000}` by `deploy.sh`/`compose.yaml`; container binds `0.0.0.0:8000` internally. `BIND_ADDR=0.0.0.0` is possible but documented as "only behind an authenticated reverse proxy." |
| **Boot persistence** | `--restart=always` + `podman-restart.service` + user linger. An explicit UI *Stop* (`runtime.engine_enabled=false`) and `deploy.sh stop` both survive reboot. |

## 2. Models & providers (pinned versions)

| Role | Provider | SDK (pinned) | Model id in use | Note |
|---|---|---|---|---|
| Primary LLM | Anthropic | `anthropic==0.116.0` | `claude-sonnet-5` (settings default) | **Floating alias, not a dated snapshot → B-13 finding.** `temperature=0`, `max_tokens=1000`. |
| Fallback LLM | OpenAI | `openai==2.45.0` | `gpt-4o-mini` (settings default) | **Floating alias → B-13.** Entered only after a primary failure; 30-min cooldown. |
| Technical analysis | TradingView | `tradingview-ta==3.3.0` | n/a (indicator scraper) | Structured indicators, not free text. |

No fine-tuned model, no custom weights, no embeddings model, no local inference. → C-21
(training-data governance) is `NOT-APPLICABLE` by architecture (argued in Part 2).

## 3. Tools the model can call

**None.** `src/llm.py` sends a prompt and parses returned text. There is no tool schema,
no function-calling, no MCP connector, no shell, no code execution path from the model.
The LLM's *only* influence on the world is the schema-validated JSON it returns
(`action ∈ {sell_buy,buy,sell,hold}`, `assets` must match the pair, `confidence` clamped
to [0,1]; sentiment ∈ {bullish,bearish,neutral}). Anything off-schema becomes an
`{"error": …}` no-signal that the engine treats as "no trade."

The **engine** (not the model) calls exchange trading endpoints. That indirection is the
system's central injection containment (A-10) and is analysed there.

## 4. Data stores (including caches)

| Store | Location | Contents | Sensitivity | Lifetime |
|---|---|---|---|---|
| `config/config.json` | Host, gitignored, bind-mounted | **Overlay of UI-saved settings incl. API keys/secrets in plaintext** | **Secrets** | Persistent; survives redeploy. Absent on a fresh checkout. |
| `artifacts/cache/*.json` | Host, gitignored, bind-mounted | Cached TradingView indicators + LLM JSON responses (dry-run only) | Low (market data, model output) | TTL `cache_max_age` (1800s default); mtime-checked. |
| `EngineState` (in-memory) | Process RAM | Event log (≤300), balances snapshot, swap history (≤100), last LLM eval | Low–medium (portfolio values) | Ephemeral; lost on restart. |
| `.env` (optional) | Host, gitignored | Bootstrap secrets | **Secrets** | Persistent if present. |

**No database. No vector store. No RAG corpus. No persistent user/PII store.** The only
personal data is the operator's *own* API keys and their *own* SMS recipient number — the
operator is simultaneously data subject, controller and processor. → re-bands C-04/C-23
away from third-party-privacy STOP-SHIP (argued in Part 2).

## 5. Egress paths (the complete outbound allowlist)

| Destination | Purpose | Auth | Reached from |
|---|---|---|---|
| `api.binance.com` | balances, prices, exchangeInfo, **market orders**, margin loan/repay | HMAC-SHA256 signed | `binance_client.py` |
| `api.etoro.com` | credit, portfolio, rates, **open/close positions** | `Ocp-Apim-Subscription-Key` + `X-USER-KEY` | `etoro_client.py` |
| `api.anthropic.com` | LLM completion (primary) | `x-api-key` (SDK) | `llm.py` |
| `api.openai.com` | LLM completion (fallback) | Bearer (SDK) | `llm.py` |
| `scanner.tradingview.com` (via `tradingview_ta`) | technical indicators | none | `analysis.py` |
| `api.sipgate.com/v2/sessions/sms` | SMS alerts (loan repaid / rebalance failed) | `Authorization` token | `notifications.py` |

**This allowlist is fixed in code.** The LLM cannot add a destination. The two
money-moving destinations (Binance orders, eToro positions) are the irreversible-action
surface (A-34).

## 6. Identities

Single principal: **the operator.** All credentials are the operator's own, held in
`config/config.json` or `.env`:

- Binance API key + secret (recommended scope: read + spot/margin trade, no withdrawal, IP-pinned)
- eToro subscription key + user key
- Anthropic API key, OpenAI API key
- sipgate auth token

No per-agent identities, OAuth flows, workload identity, service accounts, or
agent-to-agent auth exist — there is one human and one process. → collapses most of the
machine-identity catalogue (C-16, B-22) to "single-principal; argue N/A or right-size."

## 7. The policy bundle that gates merges — **does not exist**

| Question | Answer at commit `840e4f4` |
|---|---|
| What decides whether a change ships? | **Nothing automated.** Direct `git push` by whoever holds the remote credential. |
| CI / branch protection? | **None** — no `.github/`, no pipeline, no required checks. |
| Where does the gate policy live, and who can write it? | **N/A — there is no gate.** |
| Independent adversarial verifier? | **None.** |
| Test suite? | 38 pytest tests, **run by hand only**; nothing blocks a push on a red suite. |

This is the finding the whole operating model turns on (A-01 + A-39 → `STOP-SHIP` under
§3). Phase 5 builds the gate: a GitHub Actions workflow running tests + lint + a
dependency-existence check + a secret scan + mutation on core logic, plus a
`scripts/policy_gate.py` that reads `audit/engagement-status.json` and fails closed. The
honest limit — a solo repo cannot fully separate gate-from-gated per B-35 — is recorded as
a residual with a compensating control, never papered over.

## 8. Audit-surface inventory (summary; full machine-readable form in `00-audit-surface.json`)

- **Source modules (15):** `settings, engine, llm, prompts, analysis, cache, scheduler,
  notifications, state, main, exchanges/{base,binance_client,etoro_client}, web/app,
  web/static/index.html`
- **Routes (10):** `GET /`, `GET /api/health`, `GET /api/status`, `GET /api/config`,
  `PUT /api/config`, `POST /api/engine/start`, `POST /api/engine/stop`,
  `POST /api/run/{job}`, `POST /api/test-connection`
- **Scheduled jobs (3):** `refresh`, `rebalance`, `repay` (+ on-demand `sweep`)
- **Config keys:** the `DEFAULTS` tree in `settings.py` (exchange, dry_run, runtime,
  binance, etoro, llm, sms, trading.*, schedule.*, web.*) + 14 `ENV_OVERRIDES`
- **Prompts (2):** `swap_analysis_prompt`, `market_evaluation_prompt` (+ `SYSTEM_PROMPT`)
- **Dependencies (9 runtime, pinned):** fastapi, uvicorn, requests, tradingview-ta,
  anthropic, openai, astral, pytz, python-dotenv (+ pytest, httpx dev)
- **Infra/config files:** `Dockerfile`, `deploy.sh`, `compose.yaml`, `requirements.txt`,
  `requirements-dev.txt`, `.env.example`, `.gitignore`
- **Tests (5 files, 38 tests):** `test_engine, test_llm_and_exchange, test_settings,
  test_web, conftest`

## 9. Phase-0 findings already established (evidence, not narrative)

- **Git-history secret scan (B-06 dimension):** all 4 commits' blobs enumerated; content
  grepped for the credentials exposed in the original chat dump (`Ejkfd8…`, `J6OTTFTE…`)
  and generic patterns (`sk-`, `sk-ant-`, `-----BEGIN`, `AKIA…`, `xoxb-`). **Zero hits.**
  No secret was ever committed. `.env` and `config/config.json` are gitignored;
  `config.json` does not exist on disk. Evidence: `audit/evidence/b06-history-scan.txt`.
- **Suite runs green from a clean invocation:** `python -m pytest -q` → **38 passed**.
  Evidence captured in `audit/02-calibration.md`.
- **No CI / gate / scanner / linter / mutation tooling present** (`.github/` absent, no
  `pyproject.toml`, no `.pre-commit-config.yaml`). Evidence: directory listing in Phase 0.

> **Out-of-repo action still owed (not a repo finding):** the credentials pasted into the
> *original chat message* (Nexo password, TOTP secret, Anthropic/OpenAI/Groq keys, sipgate
> token) must be treated as **exposed and rotated at their providers.** They are not in git
> history, so they are not a repository finding — but a commit is a publication and a chat
> paste is a disclosure. Rotation is the operator's action (B-06 "rotate before you
> remove"); this audit cannot perform it.
