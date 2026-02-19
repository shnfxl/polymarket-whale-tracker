from __future__ import annotations

import asyncio
import logging

import argparse
from dotenv import load_dotenv

from .detector import WhaleDetector
from .notifier import Notifier
from .config import SETTINGS


async def run_loop(args):
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    overrides = {
        "DISABLE_MARKET_GATES": bool(args.disable_market_gates),
        "DISABLE_CLUSTER_GATE": bool(args.disable_cluster_gate),
        "DISABLE_WALLET_GATE": bool(args.disable_wallet_gate),
        "DISABLE_TREND_GATE": bool(args.disable_trend_gate),
        "DISABLE_IMPACT_GATE": bool(args.disable_impact_gate),
    }
    settings = SETTINGS.with_overrides(**overrides)

    logging.info(
        "Whale tracker starting (poll=%ss, min_whale=$%s)",
        settings.POLL_INTERVAL_SECONDS,
        int(settings.MIN_WHALE_BET_USD),
    )

    detector = WhaleDetector(settings=settings)
    notifier = Notifier(dry_run=args.dry_run)

    try:
        while True:
            signals = await detector.scan()
            logging.info("Scan complete: %s signals", len(signals))
            for sig in signals:
                await notifier.notify(sig)
            if args.once:
                break
            await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)
    finally:
        await detector.close()
        await notifier.close()


def main():
    parser = argparse.ArgumentParser(description="Polymarket whale tracker")
    parser.add_argument("--once", action="store_true", help="Run one scan and exit")
    parser.add_argument("--dry-run", action="store_true", help="Do not send alerts")
    parser.add_argument("--disable-market-gates", action="store_true")
    parser.add_argument("--disable-cluster-gate", action="store_true")
    parser.add_argument("--disable-wallet-gate", action="store_true")
    parser.add_argument("--disable-trend-gate", action="store_true")
    parser.add_argument("--disable-impact-gate", action="store_true")
    args = parser.parse_args()

    asyncio.run(run_loop(args))


if __name__ == "__main__":
    main()
