from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set

from .client import PolymarketClient
from .config import SETTINGS

logger = logging.getLogger(__name__)


@dataclass
class WhaleSignal:
    market_id: str
    market_slug: str
    market_question: str
    side: str
    price: float
    size_usd: float
    wallet: str
    same_side_whales: int
    trade_ts: int

    @property
    def market_url(self) -> str:
        return f"https://polymarket.com/market/{self.market_slug}"


class WhaleDetector:
    def __init__(self, client: Optional[PolymarketClient] = None):
        self.client = client or PolymarketClient()
        self._seen: Set[str] = set()

    async def close(self):
        await self.client.close()

    def _market_ok(self, market: Dict) -> bool:
        volume_24h = float(market.get("volume24h") or 0)
        liquidity = float(market.get("liquidity") or 0)
        return volume_24h >= SETTINGS.min_market_volume_24h and liquidity >= SETTINGS.min_liquidity_usd

    def _trade_usd(self, trade: Dict) -> float:
        size = float(trade.get("size") or 0)
        price = float(trade.get("price") or 0)
        return size * price

    def _trade_uid(self, trade: Dict) -> str:
        return str(trade.get("transactionHash") or trade.get("id") or trade.get("timestamp") or "")

    def _within_price_band(self, price: float) -> bool:
        return SETTINGS.min_price_band <= price <= SETTINGS.max_price_band

    def _count_same_side_whales(self, trades: Iterable[Dict], side: str, min_usd: float) -> int:
        wallets = set()
        for t in trades:
            if str(t.get("side") or "").upper() != "BUY":
                continue
            outcome = str(t.get("outcome") or "").upper()
            if outcome != side:
                continue
            if self._trade_usd(t) < min_usd:
                continue
            wallet = str(t.get("proxyWallet") or "").lower().strip()
            if wallet:
                wallets.add(wallet)
        return len(wallets)

    async def scan(self) -> List[WhaleSignal]:
        markets = await self.client.get_active_markets(limit=SETTINGS.max_markets)
        signals: List[WhaleSignal] = []
        now_ts = int(time.time())

        for market in markets:
            if not self._market_ok(market):
                continue
            market_id = str(market.get("conditionId") or market.get("id") or "")
            if not market_id:
                continue

            trades = await self.client.get_market_trades(market_id, limit=SETTINGS.trades_per_market)
            if not trades:
                continue

            for trade in trades:
                if str(trade.get("side") or "").upper() != "BUY":
                    continue
                trade_uid = self._trade_uid(trade)
                if trade_uid in self._seen:
                    continue
                self._seen.add(trade_uid)

                size_usd = self._trade_usd(trade)
                if size_usd < SETTINGS.min_whale_usd:
                    continue

                price = float(trade.get("price") or 0)
                if not self._within_price_band(price):
                    continue

                wallet = str(trade.get("proxyWallet") or "").lower().strip()
                if not SETTINGS.allow_wallet(wallet):
                    continue

                outcome = str(trade.get("outcome") or "").upper()
                if outcome not in {"YES", "NO"}:
                    continue

                same_side = self._count_same_side_whales(trades, outcome, SETTINGS.min_whale_usd)

                signals.append(
                    WhaleSignal(
                        market_id=market_id,
                        market_slug=str(market.get("slug") or ""),
                        market_question=str(market.get("question") or market.get("title") or ""),
                        side=outcome,
                        price=price,
                        size_usd=size_usd,
                        wallet=wallet,
                        same_side_whales=same_side,
                        trade_ts=int(trade.get("timestamp") or now_ts),
                    )
                )

        return signals
