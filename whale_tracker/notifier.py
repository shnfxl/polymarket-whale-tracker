from __future__ import annotations

import logging
from typing import Optional, Dict

import aiohttp
import tweepy

from .config import SETTINGS

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

    def _format_message(self, activity: Dict) -> str:
        market = activity.get("market") or {}
        whale = activity.get("whale") or {}
        wallet = str(whale.get("address") or "")
        wallet_short = f"{wallet[:6]}...{wallet[-4:]}" if wallet else "unknown"
        market_title = market.get("title") or market.get("question") or "Unknown market"
        market_url = activity.get("market_url") or ""
        side = activity.get("side") or ""
        amount = float(activity.get("amount") or 0)
        odds_after = activity.get("odds_after")
        odds_before = activity.get("odds_before")
        price_str = ""
        if odds_after is not None:
            price_str = f" @ {float(odds_after):.3f}"
        elif odds_before is not None:
            price_str = f" @ {float(odds_before):.3f}"
        same_side = activity.get("same_side_whales")

        lines = [
            "Whale trade detected",
            f"Market: {market_title}",
            f"Side: {side}{price_str}",
            f"Size: ${amount:,.0f}",
            f"Wallet: {wallet_short}",
        ]
        if same_side is not None:
            lines.append(f"Same-side whales: {same_side}")
        if market_url:
            lines.append(f"Link: {market_url}")
        return "\n".join(lines)

    async def send_telegram(self, message: str):
        if not SETTINGS.TELEGRAM_BOT_TOKEN or not SETTINGS.TELEGRAM_CHAT_ID:
            return
        session = await self._get_session()
        url = f"https://api.telegram.org/bot{SETTINGS.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": SETTINGS.TELEGRAM_CHAT_ID, "text": message}
        try:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning("Telegram error %s: %s", resp.status, body[:200])
        except Exception as exc:
            logger.warning("Telegram send failed: %s", exc)

    async def send_x(self, message: str):
        if not SETTINGS.X_POST_ENABLED:
            return
        if not all([
            SETTINGS.X_CONSUMER_KEY,
            SETTINGS.X_CONSUMER_SECRET,
            SETTINGS.X_ACCESS_TOKEN,
            SETTINGS.X_ACCESS_TOKEN_SECRET,
        ]):
            logger.warning("X posting enabled but missing credentials")
            return
        try:
            auth = tweepy.OAuth1UserHandler(
                SETTINGS.X_CONSUMER_KEY,
                SETTINGS.X_CONSUMER_SECRET,
                SETTINGS.X_ACCESS_TOKEN,
                SETTINGS.X_ACCESS_TOKEN_SECRET,
            )
            api = tweepy.API(auth)
            api.update_status(message[:270])
        except Exception as exc:
            logger.warning("X post failed: %s", exc)

    async def notify(self, activity: Dict):
        msg = self._format_message(activity)
        await self.send_telegram(msg)
        if SETTINGS.X_POST_ENABLED:
            await self.send_x(msg)
