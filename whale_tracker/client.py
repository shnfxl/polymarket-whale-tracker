from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp

from .config import SETTINGS

logger = logging.getLogger(__name__)


class PolymarketClient:
    def __init__(self, gamma_api: Optional[str] = None, data_api: Optional[str] = None):
        self.gamma_api = gamma_api or SETTINGS.poly_gamma_api
        self.data_api = data_api or SETTINGS.poly_data_api
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": "whale-tracker/1.0"},
                timeout=aiohttp.ClientTimeout(total=20),
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get_json(self, url: str, params: Optional[Dict[str, Any]] = None):
        session = await self._get_session()
        for attempt in range(3):
            try:
                async with session.get(url, params=params) as resp:
                    if resp.status == 429:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    if resp.status != 200:
                        body = await resp.text()
                        logger.warning("HTTP %s for %s: %s", resp.status, url, body[:200])
                        return None
                    return await resp.json()
            except Exception as exc:
                logger.warning("request failed for %s: %s", url, exc)
                await asyncio.sleep(1 + attempt)
        return None

    async def get_active_markets(self, limit: int = 200) -> List[Dict[str, Any]]:
        params = {"limit": str(limit), "active": "true"}
        data = await self._get_json(f"{self.gamma_api}/markets", params=params)
        return data if isinstance(data, list) else []

    async def get_market_trades(self, market_id: str, limit: int = 200, order: str = "DESC") -> List[Dict[str, Any]]:
        params = {"market": market_id, "limit": str(limit), "order": order}
        data = await self._get_json(f"{self.data_api}/trades", params=params)
        return data if isinstance(data, list) else []
