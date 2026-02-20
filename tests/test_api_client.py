from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from whale_tracker.api_client import PolymarketAPIClient


class StubAPIClient(PolymarketAPIClient):
    def __init__(self, pages):
        settings = SimpleNamespace(
            CLOB_CLIENT=None,
            API_RETRIES=0,
            API_TIMEOUT_SECONDS=5,
            DEBUG_LOG_API=False,
            POLYMARKET_DATA_API="https://data-api.polymarket.com",
            TRADE_PAGE_SIZE=50,
            TRADE_MAX_PAGES=2,
        )
        super().__init__(settings=settings)
        self._pages = pages
        self.session = object()  # prevent aiohttp session creation in tests

    async def _get_json(self, url, params=None):
        offset = int((params or {}).get("offset", "0"))
        page_index = offset // self.settings.TRADE_PAGE_SIZE
        if page_index < len(self._pages):
            return self._pages[page_index]
        return []


class APIClientTradeParsingTests(unittest.IsolatedAsyncioTestCase):
    async def test_malformed_outcome_index_falls_back_to_outcome_text(self):
        now_ts = int(datetime.now(timezone.utc).timestamp())
        pages = [[{
            "timestamp": now_ts,
            "price": 0.71,
            "size": 100,
            "outcomeIndex": "not-a-number",
            "outcome": "NO",
            "proxyWallet": "0xabc",
            "conditionId": "m1",
            "title": "Suns vs. Spurs",
            "transactionHash": "0xtx1",
        }]]
        client = StubAPIClient(pages)

        trades = await client.fetch_recent_trades(since_minutes=5)

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["side"], "NO")
        self.assertEqual(trades[0]["side_label"], "NO")

    async def test_categorical_outcome_keeps_label(self):
        now_ts = int(datetime.now(timezone.utc).timestamp())
        pages = [[{
            "timestamp": now_ts,
            "price": 0.71,
            "size": 100,
            "outcome": "Spurs",
            "proxyWallet": "0xabc",
            "conditionId": "m1",
            "title": "Suns vs. Spurs",
            "transactionHash": "0xtx2",
        }]]
        client = StubAPIClient(pages)

        trades = await client.fetch_recent_trades(since_minutes=5)

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["side"], "UNKNOWN")
        self.assertEqual(trades[0]["side_label"], "Spurs")


class TraderStatsCacheFreshnessTests(unittest.IsolatedAsyncioTestCase):
    async def test_force_refresh_bypasses_cache(self):
        class StatsClient(PolymarketAPIClient):
            def __init__(self):
                settings = SimpleNamespace(
                    CLOB_CLIENT=None,
                    API_RETRIES=0,
                    API_TIMEOUT_SECONDS=5,
                    DEBUG_LOG_API=False,
                    POLYMARKET_DATA_API="https://data-api.polymarket.com",
                    TRADE_PAGE_SIZE=50,
                    TRADE_MAX_PAGES=2,
                    TRADER_STATS_CACHE_TTL_SECONDS=3600,
                )
                super().__init__(settings=settings)
                self.calls = 0
                self.session = object()

            async def fetch_recent_trades(self, **kwargs):
                self.calls += 1
                return [{
                    "user": (kwargs.get("user") or "").lower(),
                    "amount": 100.0,
                }]

            async def fetch_closed_positions(self, address: str, since_days: int = 30):
                return []

        client = StatsClient()
        addr = "0xabc"
        _ = await client.get_trader_stats(addr)
        self.assertEqual(client.calls, 1)

        _ = await client.get_trader_stats(addr)
        self.assertEqual(client.calls, 1)

        _ = await client.get_trader_stats(addr, force_refresh=True)
        self.assertEqual(client.calls, 2)


if __name__ == "__main__":
    unittest.main()
