from __future__ import annotations

import importlib
import os
import unittest
from unittest.mock import patch


class ConfigAliasTests(unittest.TestCase):
    def test_legacy_aliases_are_supported(self):
        with patch.dict(
            os.environ,
            {
                "MIN_WHALE_USD": "34567",
                "POLY_GAMMA_API": "https://gamma-alias.example",
                "POLY_DATA_API": "https://data-alias.example",
            },
            clear=False,
        ):
            os.environ.pop("MIN_WHALE_BET_USD", None)
            os.environ.pop("POLYMARKET_GAMMA_API", None)
            os.environ.pop("POLYMARKET_DATA_API", None)

            import whale_tracker.config as config

            config = importlib.reload(config)
            self.assertEqual(config.MIN_WHALE_BET_USD, 34567.0)
            self.assertEqual(config.POLYMARKET_GAMMA_API, "https://gamma-alias.example")
            self.assertEqual(config.POLYMARKET_DATA_API, "https://data-alias.example")


if __name__ == "__main__":
    unittest.main()
