from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from whale_tracker.notifier import Notifier


class NotifierTests(unittest.IsolatedAsyncioTestCase):
    def test_format_message_cluster_links_market(self):
        notifier = Notifier(dry_run=True)
        activity = {
            "market": {"title": "Will BTC exceed $100k?"},
            "market_url": "https://polymarket.com/market/btc-100k",
            "whale": {"address": "0x1234567890abcdef1234567890abcdef12345678"},
            "side": "YES",
            "amount": 25000,
            "odds_after": 0.734,
            "same_side_whales": 2,
        }

        msg = notifier._format_message(activity)

        self.assertIn("🐋 Whale Alert", msg)
        self.assertIn("🎯 Market: Will BTC exceed $100k?", msg)
        self.assertIn("🟢 Side: YES @ 0.734", msg)
        self.assertIn("💵 Size: $25,000", msg)
        self.assertIn("🧾 Wallet: 0x1234567890abcdef1234567890abcdef12345678", msg)
        self.assertIn("👥 Same-side whales: 2", msg)
        self.assertIn("🔗 Market: https://polymarket.com/market/btc-100k", msg)
        self.assertNotIn("🔗 Trader:", msg)

    def test_format_message_single_links_trader(self):
        notifier = Notifier(dry_run=True)
        activity = {
            "market": {"title": "Will ETH exceed $8k?"},
            "market_url": "https://polymarket.com/market/eth-8k",
            "whale": {"address": "0xaabbccddeeff00112233445566778899aabbccdd"},
            "side": "NO",
            "amount": 18000,
            "odds_after": 0.321,
            "same_side_whales": 1,
        }

        msg = notifier._format_message(activity)

        self.assertIn("🔴 Side: NO @ 0.321", msg)
        self.assertIn("🧾 Wallet: 0xaabbccddeeff00112233445566778899aabbccdd", msg)
        self.assertIn("🔗 Trader: https://polymarket.com/profile/0xaabbccddeeff00112233445566778899aabbccdd", msg)
        self.assertNotIn("🔗 Market: https://polymarket.com/market/eth-8k", msg)

    async def test_notify_dry_run_does_not_send(self):
        notifier = Notifier(dry_run=True)
        notifier.send_telegram = AsyncMock()

        await notifier.notify({"amount": 1})

        notifier.send_telegram.assert_not_awaited()

    async def test_notify_sends_telegram_when_enabled(self):
        notifier = Notifier(dry_run=False)
        notifier.send_telegram = AsyncMock()

        await notifier.notify({"amount": 1})

        notifier.send_telegram.assert_awaited_once()

    async def test_send_telegram_returns_false_when_credentials_missing(self):
        settings = SimpleNamespace(TELEGRAM_BOT_TOKEN="", TELEGRAM_CHAT_ID="")
        notifier = Notifier(dry_run=False, settings=settings)
        ok = await notifier.send_telegram("x")
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
