from __future__ import annotations

import logging
from typing import Optional, Dict

import aiohttp

from .config import SETTINGS

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, dry_run: bool = False, settings=None):
        self._session: Optional[aiohttp.ClientSession] = None
        self.dry_run = dry_run
        self.settings = settings or SETTINGS

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    @staticmethod
    def _trader_url(wallet: str) -> str:
        return f"https://polymarket.com/profile/{wallet}"

    def _format_message(self, activity: Dict) -> str:
        market = activity.get("market") or {}
        whale = activity.get("whale") or {}
        wallet = str(whale.get("address") or "")
        market_title = market.get("title") or market.get("question") or "Unknown market"
        market_url = activity.get("market_url") or ""
        side = activity.get("side") or ""
        side_emoji = "🟢" if side == "YES" else "🔴" if side == "NO" else "⚪"
        amount = float(activity.get("amount") or 0)
        odds_after = activity.get("odds_after")
        odds_before = activity.get("odds_before")
        price_str = ""
        if odds_after is not None:
            price_str = f" @ {float(odds_after):.3f}"
        elif odds_before is not None:
            price_str = f" @ {float(odds_before):.3f}"
        same_side = int(activity.get("same_side_whales") or 0)
        same_side_other = int(activity.get("same_side_other_whales") or max(0, same_side - 1))
        same_side_notional = float(activity.get("same_side_notional") or amount)
        is_cluster = same_side_other > 0

        lines = [
            "🐋 Whale Alert",
            f"🎯 Market: {market_title}",
            f"{side_emoji} Side: {side}{price_str}",
            f"💵 Trade size: ${amount:,.0f}",
            f"🧾 Wallet: {wallet or 'unknown'}",
        ]
        if is_cluster:
            lines.append(f"👥 Cluster wallets (same side): {same_side} ({same_side_other} other)")
            lines.append(f"📦 Cluster notional (lookback): ${same_side_notional:,.0f}")
        if is_cluster and market_url:
            lines.append(f"🔗 Market: {market_url}")
        elif wallet:
            lines.append(f"🔗 Trader: {self._trader_url(wallet)}")
        elif market_url:
            lines.append(f"🔗 Market: {market_url}")
        return "\n".join(lines)

    async def send_telegram(self, message: str) -> bool:
        if not self.settings.TELEGRAM_BOT_TOKEN or not self.settings.TELEGRAM_CHAT_ID:
            logger.warning(
                "Telegram disabled: missing %s%s",
                "TELEGRAM_BOT_TOKEN" if not self.settings.TELEGRAM_BOT_TOKEN else "",
                " and TELEGRAM_CHAT_ID" if not self.settings.TELEGRAM_CHAT_ID else "",
            )
            return False
        session = await self._get_session()
        url = f"https://api.telegram.org/bot{self.settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": self.settings.TELEGRAM_CHAT_ID, "text": message}
        try:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning("Telegram error %s: %s", resp.status, body[:200])
                    return False
                return True
        except Exception as exc:
            logger.warning("Telegram send failed: %s", exc)
            return False

    async def notify(self, activity: Dict):
        msg = self._format_message(activity)
        if self.dry_run:
            logger.info("Dry run alert:\n%s", msg)
            return
        await self.send_telegram(msg)
