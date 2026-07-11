# Trading Automator

Automated crypto portfolio manager driven by TradingView technical analysis
and LLM evaluation, executing on **Binance** or **eToro** via their official
APIs, with a built-in **web UI** for configuration and live monitoring.

This is the API-based successor of the earlier Nexo/Selenium automation: all
browser automation (login flows, captcha solving, DOM scraping, screenshots)
has been removed and every trading behaviour has been ported to exchange
REST APIs.

## How it works

Every cycle (randomised intervals, different for day and night):

1. **Refresh** — read balances (and outstanding margin loan) from the exchange.
2. **Rebalance** —
   - split fresh quote-asset inflows (buy a slice of the anchor asset),
   - keep the *anchor asset* at its target portfolio share
     (generalisation of the old NEXO 10.3% loyalty level),
   - pull TradingView indicators (RSI, MACD, Bollinger, Stochastic,
     Fibonacci, momentum/trend metrics) for the configured asset universe,
   - have an LLM (Anthropic primary, OpenAI fallback) compare every asset
     pair and judge overall market sentiment,
   - **bullish** → derive target weights from the recommendations, keep a
     configurable reserve in the quote asset, tighten the schedule;
     **bearish** → liquidate all crypto into the quote asset, relax the
     schedule; **neutral** → mostly quote asset plus some anchor.
3. **Repay** — repay any outstanding Binance cross-margin loan with the
   quote asset (the old Nexo loan repayment; no-op on eToro).
4. On demand: **dust sweep** of balances below a threshold.

Safety invariants enforced by the engine:

- Only assets in the configured universe are ever bought or sold; airdrops
  or manually held positions are never touched.
- A rebalance aborts without trading when technical analysis is missing for
  any buyable asset, when all pairwise LLM evaluations failed, or when the
  market evaluation failed — no decisions on partial data.
- Sells always run before buys, and buys are clamped to the actually
  available quote balance.
- Every LLM response is schema-validated (action/assets/confidence/
  sentiment) before it can influence a trade.
- Binance orders are pre-checked against the pair's minimum notional and
  LOT_SIZE (Decimal-exact), and live sells are clamped to the free balance.
- Inflow detection is delta-based: only an actual increase of the quote
  balance since the previous cycle counts as a deposit, so the engine's own
  cash reserve can never trigger the inflow split.

Optional SMS alerts (sipgate) fire on executed loan repayments and failed
rebalance runs — never in dry-run mode.

## Functionality mapping (old → new)

| Old (Nexo + Selenium)             | New (API)                              |
|-----------------------------------|----------------------------------------|
| Login / TOTP / captcha solving    | API-key auth (gone entirely)           |
| Balance table scraping            | `GET /api/v3/account` + prices         |
| Swap page automation              | Market orders / eToro positions        |
| NEXO loyalty 10.3% maintenance    | Anchor asset target percent            |
| EURx inflow split                 | Quote-asset inflow split               |
| Loan repayment page               | Binance margin repay                   |
| Screenshots / log tail            | Web dashboard + structured event log   |
| Day/night randomised scheduler    | Same, runtime-adjustable via sentiment |
| Claude→OpenAI LLM fallback        | Same, keys configurable in the UI      |
| DEBUG response cache              | Same (`artifacts/cache`, dry-run only) |

## Quick start — one-liner podman deployment

On a machine with `podman` and `git` installed:

```bash
curl -fsSL https://raw.githubusercontent.com/mglaeser/trading-automator/HEAD/deploy.sh | bash
```

or, if you prefer cloning yourself:

```bash
git clone https://github.com/mglaeser/trading-automator.git && cd trading-automator && ./deploy.sh
```

Either command clones/updates the repo, builds the container image, starts
the container with `--restart=always`, enables boot persistence
(`podman-restart.service` + user lingering, rootless-friendly), and serves
the web UI on <http://localhost:8000>. Everything runs inside the container
automatically:

1. Open the web UI → **Settings** → enter exchange + LLM API keys → save.
2. The trading engine **starts itself** as soon as credentials exist
   (`AUTOSTART=true` inside the container) — in **dry-run mode**, so every
   decision is computed and logged but no order is sent.
3. Only after reviewing the logged behaviour, switch *Dry run* to off.

`deploy.sh` also handles day-2 operations:

```bash
./deploy.sh update      # git pull + rebuild + restart
./deploy.sh logs        # follow container logs
./deploy.sh status      # container state + app health
./deploy.sh stop        # stop the container
./deploy.sh uninstall   # remove container + image (config/ is kept)
```

Defaults can be overridden via environment variables: `PORT=9000 ./deploy.sh`
from a checkout, or on the **bash side of the pipe** for the one-liner:

```bash
curl -fsSL https://raw.githubusercontent.com/mglaeser/trading-automator/HEAD/deploy.sh \
  | INSTALL_DIR=/opt/trader PORT=9000 bash
```

The UI is bound to `127.0.0.1` because it has **no authentication** — set
`BIND_ADDR=0.0.0.0` only behind an authenticated reverse proxy. A
`compose.yaml` is included as an alternative (`podman compose up -d --build`;
see its header for the boot-persistence caveat).

### Running without a container

```bash
pip install -r requirements.txt
python -m src.main
# open http://localhost:8000 and press "Start engine" after configuring keys
```

Configuration is persisted to `config/config.json` (gitignored, bind-mounted
by the container so it survives redeploys). Environment variables (see
`.env.example`) **bootstrap** settings: they apply only to keys never saved
through the UI, so a stale `.env` can never silently revert a UI decision
(most importantly: it can never flip dry-run back off). Fully headless
deployments therefore work by providing all keys via `.env` and never
touching the UI.

An explicit *Stop* in the web UI is persisted (`runtime.engine_enabled`):
neither a container restart, a reboot, nor a later config save will
resurrect a deliberately stopped engine — only pressing *Start* does.
`./deploy.sh stop` likewise clears the container restart policy so the
container stays down across reboots.

## Exchange notes

- **Binance**: create API keys with *Enable Reading* and *Enable Spot &
  Margin Trading* only — **never enable withdrawals** — and restrict them to
  your server's IP. Swaps use direct pairs when available, otherwise two
  legs through the quote asset. Loan handling uses cross-margin repay.
- **eToro**: uses the developer-portal API (subscription key + user key).
  eToro is position-based, so "swaps" open/close positions settled in cash;
  there is no loan facility. Endpoint paths follow the public API portal and
  can be adjusted via `etoro.base_url` if eToro migrates versions.

## Security

- No credentials live in the repository. Keys are stored in
  `config/config.json` (gitignored) or supplied via environment variables,
  and are masked in every API response to the browser.
- If you previously used the Selenium version: the credentials that were in
  its `.env`/source (exchange login, TOTP secret, LLM keys, SMS token)
  should be considered exposed — **rotate all of them**.
- The web UI has no built-in authentication. Bind it to localhost or put it
  behind a reverse proxy with auth before exposing it.

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest tests/
```

The suite covers the trading maths (allocation scoring, anchor targeting,
inflow detection, funded rebalancing), config semantics (secret masking,
env bootstrap precedence, asset-universe replacement), LLM response
validation, Binance order mechanics, and the web API including the
autostart rules — all against an in-memory fake exchange, no network needed.

## Disclaimer

This software trades real money when dry-run is disabled. It is provided
as-is, without any warranty; use at your own risk.
