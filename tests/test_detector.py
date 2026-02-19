from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from whale_tracker.detector import WhaleDetector


class FakeAPIClient:
    def __init__(self):
        self.session = None
        self.fetch_markets_calls = []

    async def __aenter__(self):
        self.session = object()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.session = None

    async def fetch_markets(self, *, limit: int, active: bool, sort_by: str):
        self.fetch_markets_calls.append((limit, active, sort_by))
        return []


class FakeDataGenerator:
    def __init__(self, api_client, settings=None):
        self.api_client = api_client
        self.settings = settings
        self.started = False

    def start_cycle(self):
        self.started = True

    async def generate_whale_bets(self, limit=None):
        return [{"amount": 123, "limit": limit}]

    def snapshot_gate_counters(self):
        return {"accepted": 1}


class DetectorSettingsTests(unittest.IsolatedAsyncioTestCase):
    async def test_scan_uses_injected_settings(self):
        settings = SimpleNamespace(
            MARKET_LIMIT=11,
            MARKET_SORT_BY="liquidity",
            MAX_CANDIDATES_PER_TYPE=7,
        )
        api_client = FakeAPIClient()

        with patch("whale_tracker.detector.PolymarketDataGenerator", FakeDataGenerator):
            detector = WhaleDetector(api_client=api_client, settings=settings)
            signals = await detector.scan()

        self.assertEqual(api_client.fetch_markets_calls, [(11, True, "liquidity")])
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["limit"], 7)


if __name__ == "__main__":
    unittest.main()
