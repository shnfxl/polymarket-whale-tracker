from __future__ import annotations

import asyncio
import logging

from dotenv import load_dotenv

from .detector import WhaleDetector
from .notifier import Notifier
from .config import SETTINGS


async def run_loop():
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    logging.info(
        "Whale tracker starting (poll=%ss, min_whale=$%s)",
        SETTINGS.POLL_INTERVAL_SECONDS,
        int(SETTINGS.MIN_WHALE_BET_USD),
    )

    detector = WhaleDetector()
    notifier = Notifier()

    try:
        while True:
            signals = await detector.scan()
            logging.info("Scan complete: %s signals", len(signals))
            for sig in signals:
                await notifier.notify(sig)
            await asyncio.sleep(SETTINGS.POLL_INTERVAL_SECONDS)
    finally:
        await detector.close()
        await notifier.close()


def main():
    asyncio.run(run_loop())


if __name__ == "__main__":
    main()
