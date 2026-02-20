# Polymarket Whale Tracker

Open-source bot that scans Polymarket for large trades and sends Telegram alerts.

## What It Does
- Polls Polymarket markets + recent trades
- Detects whale-sized bets with market-quality gates
- Enriches alerts with wallet/trade context
- Sends formatted alerts to Telegram

## What It Does Not Do
- No trading or order placement
- No X/Twitter posting

## Requirements
- Python 3.10+
- A Telegram bot token and destination chat ID

No Polymarket private key is required for core alerting. The tracker uses public Polymarket APIs for markets/trades.

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Populate `.env` with at least:
```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

Optional (price enrichment only):
```env
POLYMARKET_PRIVATE_KEY=...
POLYMARKET_FUNDER_ADDRESS=...
```
These are used only for optional CLOB orderbook enrichment (`odds_after` quality). Alerts work without them.

## Run
Start the loop:
```bash
python3 -m whale_tracker
```

Single scan, no outbound alerts:
```bash
python3 -m whale_tracker --once --dry-run
```

Send a Telegram test message and exit:
```bash
python3 -m whale_tracker --test-telegram --test-message "hello from whale tracker"
```

Debug gate tuning:
```bash
python3 -m whale_tracker --disable-market-gates --disable-wallet-gate
```

## Tests
Run the unit suite:
```bash
python3 -m unittest discover -s tests -v
```

## Key Config
- `POLL_INTERVAL_SECONDS`: scan frequency
- `MIN_WHALE_BET_USD`: absolute whale threshold
- `MIN_LIQUIDITY_USD`: market liquidity floor used by filters
- `MIN_MARKET_VOLUME_24H`: 24h volume floor used by filters
- `MARKET_CATEGORIES`: optional comma-separated scope (`crypto,stocks,...`)
- `DISABLE_*_GATE`: selectively disable filtering gates for debugging
- `BOT_STATE_FILE`: JSON state file for persistent dedupe/cooldown memory (default: `memory/polymarket_state.json`)

Compatibility aliases still accepted:
- `MIN_WHALE_USD` -> `MIN_WHALE_BET_USD`
- `POLY_GAMMA_API` -> `POLYMARKET_GAMMA_API`
- `POLY_DATA_API` -> `POLYMARKET_DATA_API`

## Alert Shape
Each Telegram alert includes:
- market title
- side + price
- trade size (current trade)
- full wallet address
- cluster context when applicable:
  - cluster wallet count (and other-wallet count)
  - cluster notional (same-side lookback sum)
- conditional link:
  - single-wallet signal: trader profile link
  - cluster signal: market link

## Notes
- `.env` is loaded automatically at startup.
- Persistent dedupe state is stored in a local JSON file so restarts are replay-safe without extra dependencies.
- Core detection uses public Gamma/Data APIs. CLOB credentials are optional and only affect orderbook-based price enrichment.
- This project is alerting infrastructure; validate thresholds on paper trading data before acting on signals.
- Contributor onboarding docs: `CONTRIBUTING.md`, `MEMORY.md`.
- CI workflow: `.github/workflows/ci.yml`.
- Security policy: `SECURITY.md`.

## License
MIT
