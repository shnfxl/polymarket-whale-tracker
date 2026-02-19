from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional, Set


def _split_set(value: Optional[str]) -> Set[str]:
    if not value:
        return set()
    return {v.strip().lower() for v in value.split(",") if v.strip()}


@dataclass
class Settings:
    poly_gamma_api: str = os.getenv("POLY_GAMMA_API", "https://gamma-api.polymarket.com")
    poly_data_api: str = os.getenv("POLY_DATA_API", "https://data-api.polymarket.com")

    poll_interval_seconds: int = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
    min_whale_usd: float = float(os.getenv("MIN_WHALE_USD", "20000"))
    min_market_volume_24h: float = float(os.getenv("MIN_MARKET_VOLUME_24H", "25000"))
    min_liquidity_usd: float = float(os.getenv("MIN_LIQUIDITY_USD", "10000"))
    min_price_band: float = float(os.getenv("MIN_PRICE_BAND", "0.05"))
    max_price_band: float = float(os.getenv("MAX_PRICE_BAND", "0.95"))

    wallet_allowlist: Set[str] = field(default_factory=lambda: _split_set(os.getenv("WALLET_ALLOWLIST")))
    wallet_blocklist: Set[str] = field(default_factory=lambda: _split_set(os.getenv("WALLET_BLOCKLIST")))

    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    x_post_enabled: bool = os.getenv("X_POST_ENABLED", "false").lower() == "true"
    x_consumer_key: str = os.getenv("X_CONSUMER_KEY", "")
    x_consumer_secret: str = os.getenv("X_CONSUMER_SECRET", "")
    x_access_token: str = os.getenv("X_ACCESS_TOKEN", "")
    x_access_token_secret: str = os.getenv("X_ACCESS_TOKEN_SECRET", "")

    max_markets: int = int(os.getenv("MAX_MARKETS", "200"))
    trades_per_market: int = int(os.getenv("TRADES_PER_MARKET", "120"))

    def allow_wallet(self, address: str) -> bool:
        addr = (address or "").lower()
        if not addr:
            return False
        if addr in self.wallet_blocklist:
            return False
        if self.wallet_allowlist:
            return addr in self.wallet_allowlist
        return True


SETTINGS = Settings()
