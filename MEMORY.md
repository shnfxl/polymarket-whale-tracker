# Memory for Agent Contributors

This file is a quick orientation map for coding agents and human contributors.

## Project Goal
Track whale-sized Polymarket trades and send actionable Telegram alerts.

## Runtime Entry Point
- `python3 -m whale_tracker`
- Main loop: `whale_tracker/runner.py`

## Core Modules
- `whale_tracker/config.py`: environment-backed runtime settings
- `whale_tracker/api_client.py`: Polymarket Gamma/Data API access
- `whale_tracker/data_generator.py`: whale detection + quality gates
- `whale_tracker/detector.py`: scan orchestration
- `whale_tracker/notifier.py`: Telegram delivery

## Non-Goals
- No auto-trading
- No X/Twitter posting

## Common Dev Commands
- One-cycle dry run: `python3 -m whale_tracker --once --dry-run`
- Disable strict gates while debugging:
  - `python3 -m whale_tracker --disable-market-gates --disable-wallet-gate`
- Run tests: `python3 -m unittest discover -s tests -v`

## Required Environment
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Important Config Notes
- Canonical whale threshold env var is `MIN_WHALE_BET_USD`
- Legacy aliases are still supported:
  - `MIN_WHALE_USD`
  - `POLY_GAMMA_API`
  - `POLY_DATA_API`

## Operational Notes
- Alerts are best-effort: Telegram errors are logged and do not crash the loop.
- In sandboxed/offline environments, API DNS/network failures are expected.

## Safe Change Checklist
1. Keep `Notifier` Telegram-only unless scope explicitly changes.
2. Preserve dry-run behavior (`--dry-run` must never send).
3. Ensure settings overrides in `runner` propagate into detector/client paths.
4. Add/update unit tests for new gates or message formatting changes.
