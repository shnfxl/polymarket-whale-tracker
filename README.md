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

Compatibility aliases still accepted:
- `MIN_WHALE_USD` -> `MIN_WHALE_BET_USD`
- `POLY_GAMMA_API` -> `POLYMARKET_GAMMA_API`
- `POLY_DATA_API` -> `POLYMARKET_DATA_API`

## Alert Shape
Each Telegram alert includes:
- market title
- side + price
- USD size
- shortened wallet
- same-side whale count (cluster signal)
- market link (when available)

## Notes
- `.env` is loaded automatically at startup.
- This project is alerting infrastructure; validate thresholds on paper trading data before acting on signals.
- Contributor onboarding docs: `CONTRIBUTING.md`, `MEMORY.md`.
- CI workflow: `.github/workflows/ci.yml`.
- Security policy: `SECURITY.md`.

## License
MIT
