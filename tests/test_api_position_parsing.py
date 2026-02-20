from __future__ import annotations

import unittest

from whale_tracker.api_client import PolymarketAPIClient


class APIPositionParsingTests(unittest.TestCase):
    def test_parse_position_size_usd_prefers_known_numeric_fields(self):
        item = {"positionValue": "52000.25"}
        self.assertEqual(PolymarketAPIClient._parse_position_size_usd(item), 52000.25)

    def test_parse_position_size_usd_handles_missing_fields(self):
        item = {"foo": "bar"}
        self.assertIsNone(PolymarketAPIClient._parse_position_size_usd(item))

    def test_matches_market_on_common_keys(self):
        item = {"conditionId": "abc123"}
        self.assertTrue(PolymarketAPIClient._matches_market(item, "abc123"))
        self.assertFalse(PolymarketAPIClient._matches_market(item, "zzz"))


if __name__ == "__main__":
    unittest.main()
