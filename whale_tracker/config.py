#!/usr/bin/env python3
"""Typed runtime settings for the Polymarket whale tracker."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def _env_first(*names: str) -> Optional[str]:
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return None


def _env_str(default: str, *names: str) -> str:
    return _env_first(*names) or default


def _env_int(default: int, *names: str) -> int:
    raw = _env_first(*names)
    if raw is None:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _env_float(default: float, *names: str) -> float:
    raw = _env_first(*names)
    if raw is None:
        return default
    try:
        return float(raw)
    except Exception:
        return default


def _env_bool(default: bool, *names: str) -> bool:
    raw = _env_first(*names)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes")


def _env_csv(*names: str) -> List[str]:
    raw = _env_first(*names) or ""
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


def _build_clob_client(private_key: str, funder_address: Optional[str]):
    if not private_key:
        return None
    try:
        from py_clob_client.client import ClobClient
        from eth_account import Account

        host = "https://clob.polymarket.com"
        chain_id = 137
        temp_client = ClobClient(host=host, chain_id=chain_id, key=private_key)
        api_creds = temp_client.create_or_derive_api_creds()

        funder = funder_address
        if not funder:
            account = Account.from_key(private_key)
            funder = account.address

        signature_type = 1 if funder_address else 0
        return ClobClient(
            host=host,
            chain_id=chain_id,
            key=private_key,
            creds=api_creds,
            signature_type=signature_type,
            funder=funder,
        )
    except Exception:
        logger.debug("CLOB client unavailable; continuing without orderbook enrichment", exc_info=True)
        return None


CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "sports": [
        "nfl", "nba", "mlb", "nhl", "soccer", "football", "ufc", "boxing", "tennis", "golf",
        "f1", "formula 1", "premier league", "champions league", "world cup", "olympics",
    ],
    "crypto": [
        "btc", "bitcoin", "eth", "ethereum", "sol", "solana", "xrp", "doge", "crypto", "memecoin", "stablecoin",
    ],
    "stocks": [
        "stock", "stocks", "nasdaq", "nyse", "sp500", "s&p", "dow", "earnings", "sec", "ipo",
    ],
    "politics": [
        "election", "president", "senate", "house", "congress", "governor", "parliament",
        "prime minister", "referendum", "vote", "campaign", "poll", "approval",
    ],
}


@dataclass(frozen=True)
class Settings:
    LOG_LEVEL: str
    TELEGRAM_BOT_TOKEN: Optional[str]
    TELEGRAM_CHAT_ID: Optional[str]

    POLYMARKET_PRIVATE_KEY: str
    POLYMARKET_FUNDER_ADDRESS: Optional[str]
    CLOB_CLIENT: object

    POLYMARKET_GAMMA_API: str
    POLYMARKET_DATA_API: str

    POLL_INTERVAL_SECONDS: int
    API_TIMEOUT_SECONDS: int
    API_RETRIES: int
    API_CONCURRENCY_LIMIT: int
    TRADE_PAGE_SIZE: int
    TRADE_MAX_PAGES: int
    TRADER_STATS_CACHE_TTL_SECONDS: int

    WHALE_LOOKBACK_MINUTES: int
    SMART_LOOKBACK_MINUTES: int
    SMART_WINDOW_MINUTES: int
    SMART_WINDOW_DAYS: int
    VOLUME_NOTABLE_LOOKBACK_MINUTES: int

    MARKET_LIMIT: int
    VOLUME_MARKET_SCAN_LIMIT: int
    MARKET_SORT_BY: str

    MIN_WHALE_BET_USD: float
    MIN_LIQUIDITY_USD: float
    MIN_MARKET_VOLUME_24H: float
    MIN_VOLUME_SPIKE_1H_USD: float
    MIN_VOLUME_SPIKE_MULTIPLIER: float
    MIN_PRICE_BAND: float
    MAX_PRICE_BAND: float

    REL_WHALE_VOLUME_PCT: float
    REL_WHALE_LIQUIDITY_PCT: float
    LOW_LIQUIDITY_WHALE_LIQ_PCT: float
    LOW_LIQUIDITY_WHALE_VOL_PCT: float

    HARD_MIN_LIQUIDITY_USD: float
    HARD_MIN_VOLUME_24H_USD: float

    MIN_MARKET_DURATION_HOURS: int
    SPORTS_THRESHOLD_MULTIPLIER: float
    EXCLUDE_SPORTS_MARKETS: bool

    MARKET_QUALITY_LOOKBACK_MINUTES: int
    MIN_MARKET_QUALITY_TRADES: int
    MIN_MARKET_QUALITY_UNIQUE_TRADERS: int
    REQUIRE_TWO_SIDED_QUALITY: bool

    MIN_MARKET_TARGET_SCORE: float
    MARKET_TARGET_OVERRIDE_MULTIPLIER: float
    REQUIRE_POPULAR_CATEGORY: bool
    HIGH_SIGNAL_MARKET_VOLUME_MULTIPLIER: float
    HIGH_SIGNAL_MARKET_LIQUIDITY_MULTIPLIER: float

    ADAPTIVE_WHALE_THRESHOLD_ENABLED: bool
    ADAPTIVE_WHALE_PERCENTILE: float
    ADAPTIVE_WHALE_MIN_SAMPLES: int
    ADAPTIVE_WHALE_FLOOR_USD: float
    ADAPTIVE_WHALE_CAP_USD: float

    FLOW_GATE_NET_POSITION_USD: float
    FLOW_GATE_MARKET_INFLOW_USD: float
    FLOW_GATE_CLUSTER_MIN: int
    ALLOW_SPARSE_FLOW_BYPASS: bool
    SPARSE_FLOW_MIN_TRADES: int

    IMPACT_GATE_MIN_ABS: float
    IMPACT_GATE_MIN_PCT: float

    MIN_SMART_TRADERS: int
    MIN_SMART_TRADER_BET: float
    MIN_CONSENSUS_TOTAL: float
    SMART_MIN_CLOSED_POSITIONS: int
    SMART_MIN_AVG_POSITION_USD: float
    SMART_MIN_REALIZED_PNL_USD: float

    MAX_CANDIDATES_PER_TYPE: int
    MAX_WHALE_ENRICH_TRADES: int

    PROCESSED_TRADES_MAX: int
    PROCESSED_TRADES_TRIM_TO: int
    STATE_FILE: Path

    DISABLE_MARKET_GATES: bool
    DISABLE_CLUSTER_GATE: bool
    DISABLE_WALLET_GATE: bool
    DISABLE_TREND_GATE: bool
    DISABLE_IMPACT_GATE: bool

    DEBUG_LOG_API: bool
    CATEGORY_KEYWORDS: Dict[str, List[str]]
    MARKET_CATEGORIES: List[str]

    @classmethod
    def from_env(cls) -> "Settings":
        private_key = _env_str("", "POLYMARKET_PRIVATE_KEY")
        funder_address = _env_first("POLYMARKET_FUNDER_ADDRESS", "FUNDER_ADDRESS")
        lower_thresholds = _env_bool(False, "LOWER_THRESHOLDS")

        min_whale_bet = _env_float(20000.0, "MIN_WHALE_BET_USD", "MIN_WHALE_USD")
        min_volume_spike_multiplier = _env_float(5.0, "MIN_VOLUME_SPIKE_MULTIPLIER")
        min_smart_trader_bet = _env_float(100.0, "MIN_SMART_TRADER_BET")
        min_consensus_total = _env_float(200.0, "MIN_CONSENSUS_TOTAL")
        min_liquidity_usd = _env_float(10000.0, "MIN_LIQUIDITY_USD")
        smart_min_closed_positions = _env_int(10, "SMART_MIN_CLOSED_POSITIONS")
        smart_min_avg_position_usd = _env_float(500.0, "SMART_MIN_AVG_POSITION_USD")
        smart_min_realized_pnl_usd = _env_float(5000.0, "SMART_MIN_REALIZED_PNL_USD")

        if lower_thresholds:
            min_whale_bet = 1000.0
            min_volume_spike_multiplier = 2.0
            min_smart_trader_bet = 100.0
            min_consensus_total = 200.0
            min_liquidity_usd = 5000.0
            smart_min_closed_positions = 3
            smart_min_avg_position_usd = 100.0
            smart_min_realized_pnl_usd = 500.0

        settings = cls(
            LOG_LEVEL=_env_str("INFO", "LOG_LEVEL").upper(),
            TELEGRAM_BOT_TOKEN=_env_first("TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN", "TG_BOT_TOKEN"),
            TELEGRAM_CHAT_ID=_env_first("TELEGRAM_CHAT_ID", "TELEGRAM_CHANNEL_ID", "TELEGRAM_CHAT"),
            POLYMARKET_PRIVATE_KEY=private_key,
            POLYMARKET_FUNDER_ADDRESS=funder_address,
            CLOB_CLIENT=_build_clob_client(private_key, funder_address),
            POLYMARKET_GAMMA_API=_env_str("https://gamma-api.polymarket.com", "POLYMARKET_GAMMA_API", "POLY_GAMMA_API"),
            POLYMARKET_DATA_API=_env_str("https://data-api.polymarket.com", "POLYMARKET_DATA_API", "POLY_DATA_API"),
            POLL_INTERVAL_SECONDS=_env_int(60, "POLL_INTERVAL_SECONDS"),
            API_TIMEOUT_SECONDS=_env_int(45, "API_TIMEOUT_SECONDS"),
            API_RETRIES=_env_int(2, "API_RETRIES"),
            API_CONCURRENCY_LIMIT=_env_int(8, "API_CONCURRENCY_LIMIT"),
            TRADE_PAGE_SIZE=_env_int(200, "TRADE_PAGE_SIZE"),
            TRADE_MAX_PAGES=_env_int(8, "TRADE_MAX_PAGES"),
            TRADER_STATS_CACHE_TTL_SECONDS=_env_int(300, "TRADER_STATS_CACHE_TTL_SECONDS"),
            WHALE_LOOKBACK_MINUTES=_env_int(5, "WHALE_LOOKBACK_MINUTES"),
            SMART_LOOKBACK_MINUTES=_env_int(30, "SMART_LOOKBACK_MINUTES"),
            SMART_WINDOW_MINUTES=_env_int(15, "SMART_WINDOW_MINUTES"),
            SMART_WINDOW_DAYS=_env_int(30, "SMART_WINDOW_DAYS"),
            VOLUME_NOTABLE_LOOKBACK_MINUTES=_env_int(60, "VOLUME_NOTABLE_LOOKBACK_MINUTES"),
            MARKET_LIMIT=_env_int(300, "MARKET_LIMIT"),
            VOLUME_MARKET_SCAN_LIMIT=_env_int(120, "VOLUME_MARKET_SCAN_LIMIT"),
            MARKET_SORT_BY=_env_str("volume", "MARKET_SORT_BY").lower(),
            MIN_WHALE_BET_USD=min_whale_bet,
            MIN_LIQUIDITY_USD=min_liquidity_usd,
            MIN_MARKET_VOLUME_24H=_env_float(50000.0, "MIN_MARKET_VOLUME_24H"),
            MIN_VOLUME_SPIKE_1H_USD=_env_float(4000.0, "MIN_VOLUME_SPIKE_1H_USD"),
            MIN_VOLUME_SPIKE_MULTIPLIER=min_volume_spike_multiplier,
            MIN_PRICE_BAND=_env_float(0.08, "MIN_PRICE_BAND"),
            MAX_PRICE_BAND=_env_float(0.92, "MAX_PRICE_BAND"),
            REL_WHALE_VOLUME_PCT=_env_float(0.02, "REL_WHALE_VOLUME_PCT"),
            REL_WHALE_LIQUIDITY_PCT=_env_float(0.03, "REL_WHALE_LIQUIDITY_PCT"),
            LOW_LIQUIDITY_WHALE_LIQ_PCT=_env_float(0.10, "LOW_LIQUIDITY_WHALE_LIQ_PCT"),
            LOW_LIQUIDITY_WHALE_VOL_PCT=_env_float(0.05, "LOW_LIQUIDITY_WHALE_VOL_PCT"),
            HARD_MIN_LIQUIDITY_USD=_env_float(20000.0, "HARD_MIN_LIQUIDITY_USD"),
            HARD_MIN_VOLUME_24H_USD=_env_float(10000.0, "HARD_MIN_VOLUME_24H_USD"),
            MIN_MARKET_DURATION_HOURS=_env_int(8, "MIN_MARKET_DURATION_HOURS"),
            SPORTS_THRESHOLD_MULTIPLIER=_env_float(1.35, "SPORTS_THRESHOLD_MULTIPLIER"),
            EXCLUDE_SPORTS_MARKETS=_env_bool(False, "EXCLUDE_SPORTS_MARKETS"),
            MARKET_QUALITY_LOOKBACK_MINUTES=_env_int(60, "MARKET_QUALITY_LOOKBACK_MINUTES"),
            MIN_MARKET_QUALITY_TRADES=_env_int(2, "MIN_MARKET_QUALITY_TRADES"),
            MIN_MARKET_QUALITY_UNIQUE_TRADERS=_env_int(1, "MIN_MARKET_QUALITY_UNIQUE_TRADERS"),
            REQUIRE_TWO_SIDED_QUALITY=_env_bool(False, "REQUIRE_TWO_SIDED_QUALITY"),
            MIN_MARKET_TARGET_SCORE=_env_float(1.6, "MIN_MARKET_TARGET_SCORE"),
            MARKET_TARGET_OVERRIDE_MULTIPLIER=_env_float(1.7, "MARKET_TARGET_OVERRIDE_MULTIPLIER"),
            REQUIRE_POPULAR_CATEGORY=_env_bool(False, "REQUIRE_POPULAR_CATEGORY"),
            HIGH_SIGNAL_MARKET_VOLUME_MULTIPLIER=_env_float(2.0, "HIGH_SIGNAL_MARKET_VOLUME_MULTIPLIER"),
            HIGH_SIGNAL_MARKET_LIQUIDITY_MULTIPLIER=_env_float(2.0, "HIGH_SIGNAL_MARKET_LIQUIDITY_MULTIPLIER"),
            ADAPTIVE_WHALE_THRESHOLD_ENABLED=_env_bool(True, "ADAPTIVE_WHALE_THRESHOLD_ENABLED"),
            ADAPTIVE_WHALE_PERCENTILE=_env_float(0.90, "ADAPTIVE_WHALE_PERCENTILE"),
            ADAPTIVE_WHALE_MIN_SAMPLES=_env_int(12, "ADAPTIVE_WHALE_MIN_SAMPLES"),
            ADAPTIVE_WHALE_FLOOR_USD=_env_float(12000.0, "ADAPTIVE_WHALE_FLOOR_USD"),
            ADAPTIVE_WHALE_CAP_USD=_env_float(50000.0, "ADAPTIVE_WHALE_CAP_USD"),
            FLOW_GATE_NET_POSITION_USD=_env_float(10000.0, "FLOW_GATE_NET_POSITION_USD"),
            FLOW_GATE_MARKET_INFLOW_USD=_env_float(10000.0, "FLOW_GATE_MARKET_INFLOW_USD"),
            FLOW_GATE_CLUSTER_MIN=_env_int(3, "FLOW_GATE_CLUSTER_MIN"),
            ALLOW_SPARSE_FLOW_BYPASS=_env_bool(True, "ALLOW_SPARSE_FLOW_BYPASS"),
            SPARSE_FLOW_MIN_TRADES=_env_int(3, "SPARSE_FLOW_MIN_TRADES"),
            IMPACT_GATE_MIN_ABS=_env_float(0.003, "IMPACT_GATE_MIN_ABS"),
            IMPACT_GATE_MIN_PCT=_env_float(0.008, "IMPACT_GATE_MIN_PCT"),
            MIN_SMART_TRADERS=_env_int(1, "MIN_SMART_TRADERS"),
            MIN_SMART_TRADER_BET=min_smart_trader_bet,
            MIN_CONSENSUS_TOTAL=min_consensus_total,
            SMART_MIN_CLOSED_POSITIONS=smart_min_closed_positions,
            SMART_MIN_AVG_POSITION_USD=smart_min_avg_position_usd,
            SMART_MIN_REALIZED_PNL_USD=smart_min_realized_pnl_usd,
            MAX_CANDIDATES_PER_TYPE=_env_int(5, "MAX_CANDIDATES_PER_TYPE"),
            MAX_WHALE_ENRICH_TRADES=_env_int(20, "MAX_WHALE_ENRICH_TRADES"),
            PROCESSED_TRADES_MAX=_env_int(10000, "PROCESSED_TRADES_MAX"),
            PROCESSED_TRADES_TRIM_TO=_env_int(5000, "PROCESSED_TRADES_TRIM_TO"),
            STATE_FILE=Path(_env_str("memory/polymarket_state.json", "BOT_STATE_FILE")),
            DISABLE_MARKET_GATES=_env_bool(False, "DISABLE_MARKET_GATES"),
            DISABLE_CLUSTER_GATE=_env_bool(False, "DISABLE_CLUSTER_GATE"),
            DISABLE_WALLET_GATE=_env_bool(False, "DISABLE_WALLET_GATE"),
            DISABLE_TREND_GATE=_env_bool(False, "DISABLE_TREND_GATE"),
            DISABLE_IMPACT_GATE=_env_bool(False, "DISABLE_IMPACT_GATE"),
            DEBUG_LOG_API=_env_bool(False, "DEBUG_LOG_API"),
            CATEGORY_KEYWORDS=CATEGORY_KEYWORDS,
            MARKET_CATEGORIES=_env_csv("MARKET_CATEGORIES"),
        )
        settings._validate()
        return settings

    def _validate(self):
        if self.POLL_INTERVAL_SECONDS <= 0:
            raise ValueError("POLL_INTERVAL_SECONDS must be > 0")
        if self.TRADE_PAGE_SIZE <= 0 or self.TRADE_MAX_PAGES <= 0:
            raise ValueError("TRADE_PAGE_SIZE and TRADE_MAX_PAGES must be > 0")
        if not (0.0 <= self.MIN_PRICE_BAND <= 1.0 and 0.0 <= self.MAX_PRICE_BAND <= 1.0):
            raise ValueError("MIN_PRICE_BAND/MAX_PRICE_BAND must be within [0,1]")
        if self.MIN_PRICE_BAND >= self.MAX_PRICE_BAND:
            raise ValueError("MIN_PRICE_BAND must be less than MAX_PRICE_BAND")
        if self.PROCESSED_TRADES_TRIM_TO > self.PROCESSED_TRADES_MAX:
            raise ValueError("PROCESSED_TRADES_TRIM_TO must be <= PROCESSED_TRADES_MAX")
        if self.MARKET_SORT_BY not in ("volume", "liquidity", "none"):
            raise ValueError("MARKET_SORT_BY must be one of: volume, liquidity, none")
        if self.LOG_LEVEL not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            raise ValueError("LOG_LEVEL must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL")

    def with_overrides(self, **kwargs) -> "Settings":
        updated = replace(self, **kwargs)
        updated._validate()
        return updated


def utc_now() -> datetime:
    """Return UTC now as naive datetime for compatibility with existing comparisons."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


SETTINGS = Settings.from_env()

# Backwards-compatible module-level aliases used by tests and external scripts.
MIN_WHALE_BET_USD = SETTINGS.MIN_WHALE_BET_USD
POLYMARKET_GAMMA_API = SETTINGS.POLYMARKET_GAMMA_API
POLYMARKET_DATA_API = SETTINGS.POLYMARKET_DATA_API
