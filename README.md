# Polymarket Whale Tracker

A focused, open-source tracker that watches Polymarket markets for large whale trades and sends alerts to Telegram or X.

## Features
- Detects large trades ("whale" threshold) from Polymarket data
- Simple, readable codebase
- Optional wallet allowlist/blocklist
- Alerts to Telegram and/or X

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` (optional) or export env vars:

```bash
# Polymarket APIs (public, no key required)
export POLY_GAMMA_API=https://gamma-api.polymarket.com
export POLY_DATA_API=https://data-api.polymarket.com

# Alerting
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
# X posting (optional)
export X_POST_ENABLED=false
export X_CONSUMER_KEY=...
export X_CONSUMER_SECRET=...
export X_ACCESS_TOKEN=...
export X_ACCESS_TOKEN_SECRET=...

# Whale detection tuning
export MIN_WHALE_USD=20000
export MIN_LIQUIDITY_USD=10000
export MIN_MARKET_VOLUME_24H=25000
export POLL_INTERVAL_SECONDS=60

# Optional wallet filters
export WALLET_ALLOWLIST=0xabc...,0xdef...
export WALLET_BLOCKLIST=0x123...
```

Run:

```bash
python -m whale_tracker
```

## Output
Alerts include:
- market title + link
- side and price
- size in USD
- wallet address (short)
- same-side whale count (basic cluster signal)

## Notes
This project only tracks and alerts. It does **not** place trades.

X posting uses Tweepy (OAuth1). If you don’t want X support, leave `X_POST_ENABLED=false`.

## License
MIT
