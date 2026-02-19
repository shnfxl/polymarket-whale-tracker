from __future__ import annotations

import logging
from typing import Optional

import aiohttp
import tweepy

from .config import SETTINGS
from .detector import WhaleSignal

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _format_message(self, signal: WhaleSignal) -> str:
        wallet_short = f"{signal.wallet[:6]}...{signal.wallet[-4:]}" if signal.wallet else "unknown"
        return (
            f"Whale trade detected\n"
            f"Market: {signal.market_question}\n"
            f"Side: {signal.side} @ {signal.price:.3f}\n"
            f"Size: ${signal.size_usd:,.0f}\n"
            f"Wallet: {wallet_short}\n"
            f"Same-side whales: {signal.same_side_whales}\n"
            f"Link: {signal.market_url}"
        )

    async def send_telegram(self, message: str):
        if not SETTINGS.telegram_bot_token or not SETTINGS.telegram_chat_id:
            return
        session = await self._get_session()
        url = f"https://api.telegram.org/bot{SETTINGS.telegram_bot_token}/sendMessage"
        payload = {"chat_id": SETTINGS.telegram_chat_id, "text": message}
        try:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning("Telegram error %s: %s", resp.status, body[:200])
        except Exception as exc:
            logger.warning("Telegram send failed: %s", exc)

    async def send_x(self, message: str):
        if not SETTINGS.x_post_enabled:
            return
        if not all([
            SETTINGS.x_consumer_key,
            SETTINGS.x_consumer_secret,
            SETTINGS.x_access_token,
            SETTINGS.x_access_token_secret,
        ]):
            logger.warning("X posting enabled but missing credentials")
            return
        try:
            auth = tweepy.OAuth1UserHandler(
                SETTINGS.x_consumer_key,
                SETTINGS.x_consumer_secret,
                SETTINGS.x_access_token,
                SETTINGS.x_access_token_secret,
            )
            api = tweepy.API(auth)
            api.update_status(message[:270])
        except Exception as exc:
            logger.warning("X post failed: %s", exc)

    async def notify(self, signal: WhaleSignal):
        msg = self._format_message(signal)
        await self.send_telegram(msg)
        if SETTINGS.x_post_enabled:
            await self.send_x(msg)
