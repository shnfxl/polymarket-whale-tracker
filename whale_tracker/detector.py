from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .api_client import PolymarketAPIClient
from .config import SETTINGS
from .data_generator import PolymarketDataGenerator
from .state_store import StateStore

logger = logging.getLogger(__name__)


class WhaleDetector:
    def __init__(
        self,
        api_client: Optional[PolymarketAPIClient] = None,
        settings=None,
        state_store: Optional[StateStore] = None,
    ):
        self.settings = settings or SETTINGS
        self.api_client = api_client or PolymarketAPIClient(settings=self.settings)
        self.data_generator = PolymarketDataGenerator(
            self.api_client,
            settings=self.settings,
            state_store=state_store,
        )

    async def close(self):
        if self.api_client:
            await self.api_client.__aexit__(None, None, None)
        if getattr(self.data_generator, "state_store", None):
            self.data_generator.state_store.close()

    async def scan(self) -> List[Dict]:
        # refresh market cache each cycle (keeps quality gates accurate)
        if self.api_client and not self.api_client.session:
            await self.api_client.__aenter__()
        await self.api_client.fetch_markets(
            limit=self.settings.MARKET_LIMIT,
            active=True,
            sort_by=self.settings.MARKET_SORT_BY,
        )
        self.data_generator.start_cycle()
        whale_bets = await self.data_generator.generate_whale_bets(limit=self.settings.MAX_CANDIDATES_PER_TYPE)
        gates = self.data_generator.snapshot_gate_counters()
        logger.info("Whale scan: candidates=%s gates=%s", len(whale_bets), gates)
        return whale_bets
