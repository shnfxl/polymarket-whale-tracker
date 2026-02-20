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
            "whale": {
                "address": "0x1234567890abcdef1234567890abcdef12345678",
                "total_volume": 52041,
            },
            "side": "YES",
            "amount": 25000,
            "odds_after": 0.734,
            "same_side_whales": 2,
            "same_side_other_whales": 1,
            "same_side_notional": 47000,
            "market_position_size_usd": 52000,
        }

        msg = notifier._format_message(activity)

        self.assertIn("🐋 Whale Alert", msg)
        self.assertIn("🎯 Market: Will BTC exceed $100k?", msg)
        self.assertIn("🟢 Side: YES @ 0.734", msg)
        self.assertIn("💵 Trade size: $25,000", msg)
        self.assertIn("🧾 Wallet: 0x1234567890abcdef1234567890abcdef12345678", msg)
        self.assertIn("📊 Wallet volume (7d): $52,041", msg)
        self.assertIn("🎒 Market position size: $52,000", msg)
        self.assertIn("👥 Cluster wallets (same side): 2 (1 other)", msg)
        self.assertIn("📦 Cluster notional (lookback): $47,000", msg)
        self.assertIn("🔗 Market: https://polymarket.com/market/btc-100k", msg)
        self.assertNotIn("🔗 Trader:", msg)

    def test_format_message_single_links_trader(self):
        notifier = Notifier(dry_run=True)
        activity = {
            "market": {"title": "Will ETH exceed $8k?"},
            "market_url": "https://polymarket.com/market/eth-8k",
            "whale": {
                "address": "0xaabbccddeeff00112233445566778899aabbccdd",
                "total_volume": 68123,
            },
            "side": "NO",
            "side_label": "NO",
            "amount": 18000,
            "odds_after": 0.321,
            "same_side_whales": 1,
        }

        msg = notifier._format_message(activity)

        self.assertIn("🔴 Side: NO @ 0.321", msg)
        self.assertIn("🧾 Wallet: 0xaabbccddeeff00112233445566778899aabbccdd", msg)
        self.assertIn("📊 Wallet volume (7d): $68,123", msg)
        self.assertIn("🔗 Trader: https://polymarket.com/profile/0xaabbccddeeff00112233445566778899aabbccdd", msg)
        self.assertNotIn("🔗 Market: https://polymarket.com/market/eth-8k", msg)

    def test_format_message_cluster_without_market_url_does_not_link_trader(self):
        notifier = Notifier(dry_run=True)
        activity = {
            "market": {"title": "Suns vs. Spurs"},
            "whale": {"address": "0x07b8e44b90cc3e91b8d5fe60ea810d2534638e25"},
            "side": "NO",
            "side_label": "Spurs",
            "amount": 19176,
            "odds_after": 0.710,
            "same_side_whales": 7,
            "same_side_other_whales": 6,
            "same_side_notional": 52041,
        }

        msg = notifier._format_message(activity)

        self.assertIn("⚪ Side: Spurs @ 0.710", msg)
        self.assertIn("🔗 Market: unavailable (missing market slug)", msg)
        self.assertNotIn("🔗 Trader:", msg)

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
