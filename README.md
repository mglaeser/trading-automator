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

## Quick start

```bash
pip install -r requirements.txt
python -m src.main
# open http://localhost:8000
```

Or with Docker:

```bash
docker build -t trading-automator .
docker run -p 8000:8000 -v "$PWD/config:/app/config" trading-automator
```

Then in the web UI:

1. **Settings** → enter exchange API keys, LLM keys, trading parameters.
2. **Test exchange connection.**
3. **Dashboard** → *Start engine*. The app starts in **dry-run mode**:
   every decision is computed and logged but no order is sent.
4. Only after reviewing the logged behaviour, switch *Dry run* to off.

Configuration is persisted to `config/config.json` (gitignored); environment
variables (see `.env.example`) override it, so headless/container deployments
need no UI interaction (`AUTOSTART=true` starts the engine on boot).

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

## Disclaimer

This software trades real money when dry-run is disabled. It is provided
as-is, without any warranty; use at your own risk.
