from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from whale_tracker.state_store import JsonFileStateStore


class JsonFileStateStoreTests(unittest.TestCase):
    def test_persists_processed_trade_ids(self):
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "state.json"
            store = JsonFileStateStore(state_path)
            store.remember_processed_trade("tx1", max_size=10, trim_to=5)
            store.remember_processed_trade("tx2", max_size=10, trim_to=5)
            store.close()

            reloaded = JsonFileStateStore(state_path)
            self.assertTrue(reloaded.is_processed_trade("tx1"))
            self.assertTrue(reloaded.is_processed_trade("tx2"))

    def test_trims_deterministically(self):
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "state.json"
            store = JsonFileStateStore(state_path)
            for i in range(1, 8):
                store.remember_processed_trade(f"tx{i}", max_size=6, trim_to=3)

            self.assertFalse(store.is_processed_trade("tx1"))
            self.assertFalse(store.is_processed_trade("tx2"))
            self.assertFalse(store.is_processed_trade("tx3"))
            self.assertFalse(store.is_processed_trade("tx4"))
            self.assertTrue(store.is_processed_trade("tx5"))
            self.assertTrue(store.is_processed_trade("tx6"))
            self.assertTrue(store.is_processed_trade("tx7"))


if __name__ == "__main__":
    unittest.main()
