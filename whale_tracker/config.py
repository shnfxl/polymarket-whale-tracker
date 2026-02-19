#!/usr/bin/env python3
"""Runtime settings for the Polymarket whale tracker."""

from pathlib import Path
import random
import os
import json
import math
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
import asyncio
import aiohttp
import argparse

# Get API keys - only private key needed per Polymarket docs
POLYMARKET_PRIVATE_KEY = (os.getenv('POLYMARKET_PRIVATE_KEY') or '').strip()
POLYMARKET_FUNDER_ADDRESS = os.getenv('POLYMARKET_FUNDER_ADDRESS') or os.getenv('FUNDER_ADDRESS')
TELEGRAM_BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
    or os.getenv("TG_BOT_TOKEN")
)
TELEGRAM_CHAT_ID = (
    os.getenv("TELEGRAM_CHAT_ID")
    or os.getenv("TELEGRAM_CHANNEL_ID")
    or os.getenv("TELEGRAM_CHAT")
)
TELEGRAM_CONTEXT_MODE = (os.getenv("TELEGRAM_CONTEXT_MODE", "off") or "off").strip().lower()
BRAND_NAME = (os.getenv("BRAND_NAME", "PolyTheWhale") or "PolyTheWhale").strip()
LOG_FORMAT = (os.getenv("LOG_FORMAT", "text") or "text").strip().lower()
DEBUG_LOG_API = os.getenv("DEBUG_LOG_API", "").lower() in ("1", "true", "yes")
LOWER_THRESHOLDS = os.getenv("LOWER_THRESHOLDS", "").lower() in ("1", "true", "yes")
DRY_RUN_TEST_TELEGRAM = os.getenv("DRY_RUN_TEST_TELEGRAM", "").lower() in ("1", "true", "yes")
WHALE_LOOKBACK_MINUTES = int(os.getenv("WHALE_LOOKBACK_MINUTES", "5"))
SMART_LOOKBACK_MINUTES = int(os.getenv("SMART_LOOKBACK_MINUTES", "30"))
VOLUME_NOTABLE_LOOKBACK_MINUTES = int(os.getenv("VOLUME_NOTABLE_LOOKBACK_MINUTES", "60"))
MARKET_LIMIT = int(os.getenv("MARKET_LIMIT", "300"))
VOLUME_MARKET_SCAN_LIMIT = int(os.getenv("VOLUME_MARKET_SCAN_LIMIT", "120"))
MARKET_SORT_BY = os.getenv("MARKET_SORT_BY", "volume").lower()
MARKET_REFRESH_MINUTES = int(os.getenv("MARKET_REFRESH_MINUTES", "20"))
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
API_TIMEOUT_SECONDS = int(os.getenv("API_TIMEOUT_SECONDS", "45"))
API_RETRIES = int(os.getenv("API_RETRIES", "2"))
TRADE_PAGE_SIZE = int(os.getenv("TRADE_PAGE_SIZE", "200"))
TRADE_MAX_PAGES = int(os.getenv("TRADE_MAX_PAGES", "8"))
API_CONCURRENCY_LIMIT = int(os.getenv("API_CONCURRENCY_LIMIT", "8"))
MAX_WHALE_ENRICH_TRADES = int(os.getenv("MAX_WHALE_ENRICH_TRADES", "20"))
DISABLE_NOVELTY_GATE = os.getenv("DISABLE_NOVELTY_GATE", "").lower() in ("1", "true", "yes")
DISABLE_DAILY_CAPS = os.getenv("DISABLE_DAILY_CAPS", "").lower() in ("1", "true", "yes")
DISABLE_COOLDOWN = os.getenv("DISABLE_COOLDOWN", "").lower() in ("1", "true", "yes")
DISABLE_MARKET_GATES = os.getenv("DISABLE_MARKET_GATES", "").lower() in ("1", "true", "yes")
DISABLE_CLUSTER_GATE = os.getenv("DISABLE_CLUSTER_GATE", "").lower() in ("1", "true", "yes")
DISABLE_WALLET_GATE = os.getenv("DISABLE_WALLET_GATE", "").lower() in ("1", "true", "yes")
DISABLE_TREND_GATE = os.getenv("DISABLE_TREND_GATE", "").lower() in ("1", "true", "yes")
DISABLE_IMPACT_GATE = os.getenv("DISABLE_IMPACT_GATE", "").lower() in ("1", "true", "yes")
MIN_MARKET_VOLUME_24H = float(os.getenv("MIN_MARKET_VOLUME_24H", "50000"))
REL_WHALE_VOLUME_PCT = float(os.getenv("REL_WHALE_VOLUME_PCT", "0.02"))  # 2% of 24h volume
REL_WHALE_LIQUIDITY_PCT = float(os.getenv("REL_WHALE_LIQUIDITY_PCT", "0.03"))  # 3% of liquidity
MIN_VOLUME_SPIKE_1H_USD = float(os.getenv("MIN_VOLUME_SPIKE_1H_USD", "4000"))
LOW_LIQUIDITY_WHALE_LIQ_PCT = float(os.getenv("LOW_LIQUIDITY_WHALE_LIQ_PCT", "0.10"))  # 10% of liquidity
LOW_LIQUIDITY_WHALE_VOL_PCT = float(os.getenv("LOW_LIQUIDITY_WHALE_VOL_PCT", "0.05"))  # 5% of 24h volume
ALERT_SCORE_MIN = float(os.getenv("ALERT_SCORE_MIN", "5.0"))
MIN_PRICE_BAND = float(os.getenv("MIN_PRICE_BAND", "0.08"))
MAX_PRICE_BAND = float(os.getenv("MAX_PRICE_BAND", "0.92"))
# Market duration filter - skip short-lived markets (5-min binaries, etc)
MIN_MARKET_DURATION_HOURS = int(os.getenv("MIN_MARKET_DURATION_HOURS", "8"))
# Sports market multiplier - sports have more retail noise
SPORTS_THRESHOLD_MULTIPLIER = float(os.getenv("SPORTS_THRESHOLD_MULTIPLIER", "1.35"))
EXCLUDE_SPORTS_MARKETS = os.getenv("EXCLUDE_SPORTS_MARKETS", "false").lower() in ("1", "true", "yes")
PREFER_NON_SPORTS = os.getenv("PREFER_NON_SPORTS", "true").lower() in ("1", "true", "yes")
ENABLE_SPORTS_DRAFT_CAP = os.getenv("ENABLE_SPORTS_DRAFT_CAP", "true").lower() in ("1", "true", "yes")
MAX_SPORTS_DRAFTS_PER_CYCLE = int(os.getenv("MAX_SPORTS_DRAFTS_PER_CYCLE", "1"))
MARKET_QUALITY_LOOKBACK_MINUTES = int(os.getenv("MARKET_QUALITY_LOOKBACK_MINUTES", "60"))
MIN_MARKET_QUALITY_TRADES = int(os.getenv("MIN_MARKET_QUALITY_TRADES", "2"))
MIN_MARKET_QUALITY_UNIQUE_TRADERS = int(os.getenv("MIN_MARKET_QUALITY_UNIQUE_TRADERS", "1"))
REQUIRE_TWO_SIDED_QUALITY = os.getenv("REQUIRE_TWO_SIDED_QUALITY", "false").lower() in ("1", "true", "yes")
HARD_MIN_LIQUIDITY_USD = float(os.getenv("HARD_MIN_LIQUIDITY_USD", "20000"))
HARD_MIN_VOLUME_24H_USD = float(os.getenv("HARD_MIN_VOLUME_24H_USD", "10000"))
MIN_MARKET_TARGET_SCORE = float(os.getenv("MIN_MARKET_TARGET_SCORE", "1.6"))
MARKET_TARGET_OVERRIDE_MULTIPLIER = float(os.getenv("MARKET_TARGET_OVERRIDE_MULTIPLIER", "1.7"))
REQUIRE_POPULAR_CATEGORY = os.getenv("REQUIRE_POPULAR_CATEGORY", "false").lower() in ("1", "true", "yes")
HIGH_SIGNAL_MARKET_VOLUME_MULTIPLIER = float(os.getenv("HIGH_SIGNAL_MARKET_VOLUME_MULTIPLIER", "2.0"))
HIGH_SIGNAL_MARKET_LIQUIDITY_MULTIPLIER = float(os.getenv("HIGH_SIGNAL_MARKET_LIQUIDITY_MULTIPLIER", "2.0"))
ADAPTIVE_WHALE_THRESHOLD_ENABLED = os.getenv("ADAPTIVE_WHALE_THRESHOLD_ENABLED", "true").lower() in ("1", "true", "yes")
ADAPTIVE_WHALE_PERCENTILE = float(os.getenv("ADAPTIVE_WHALE_PERCENTILE", "0.90"))
ADAPTIVE_WHALE_MIN_SAMPLES = int(os.getenv("ADAPTIVE_WHALE_MIN_SAMPLES", "12"))
ADAPTIVE_WHALE_FLOOR_USD = float(os.getenv("ADAPTIVE_WHALE_FLOOR_USD", "12000"))
ADAPTIVE_WHALE_CAP_USD = float(os.getenv("ADAPTIVE_WHALE_CAP_USD", "50000"))  # Raised from 20000
FLOW_GATE_NET_POSITION_USD = float(os.getenv("FLOW_GATE_NET_POSITION_USD", "10000"))  # Raised from 8000
FLOW_GATE_MARKET_INFLOW_USD = float(os.getenv("FLOW_GATE_MARKET_INFLOW_USD", "10000"))  # Raised from 8000
FLOW_GATE_CLUSTER_MIN = int(os.getenv("FLOW_GATE_CLUSTER_MIN", "3"))
ALLOW_SPARSE_FLOW_BYPASS = os.getenv("ALLOW_SPARSE_FLOW_BYPASS", "true").lower() in ("1", "true", "yes")
SPARSE_FLOW_MIN_TRADES = int(os.getenv("SPARSE_FLOW_MIN_TRADES", "3"))
IMPACT_GATE_MIN_ABS = float(os.getenv("IMPACT_GATE_MIN_ABS", "0.003"))
IMPACT_GATE_MIN_PCT = float(os.getenv("IMPACT_GATE_MIN_PCT", "0.008"))
EDGE_SCORE_MIN = float(os.getenv("EDGE_SCORE_MIN", "6.0"))
# Processed trades cache management
PROCESSED_TRADES_MAX = int(os.getenv("PROCESSED_TRADES_MAX", "10000"))
PROCESSED_TRADES_TRIM_TO = int(os.getenv("PROCESSED_TRADES_TRIM_TO", "5000"))
SIGNAL_GATES_LOG_FILE = Path(os.getenv("SIGNAL_GATES_LOG_FILE", "logs/signal_quality_gates.jsonl"))
STATE_FILE = Path(os.getenv("BOT_STATE_FILE", "memory/polymarket_semi_auto_state.json"))
MANUAL_REVIEW_ONLY = os.getenv("MANUAL_REVIEW_ONLY", "true").lower() in ("1", "true", "yes")
MAX_CANDIDATES_PER_TYPE = int(os.getenv("MAX_CANDIDATES_PER_TYPE", "5"))
MAX_DRAFTS_PER_CYCLE = int(os.getenv("MAX_DRAFTS_PER_CYCLE", "4"))
MAX_ALERTS_PER_DAY = int(os.getenv("MAX_ALERTS_PER_DAY", "12"))

# Build ClobClient from private key (creds generated from key per docs)
CLOB_CLIENT = None
HAS_CLOB_AUTH = False
if POLYMARKET_PRIVATE_KEY:
    try:
        from py_clob_client.client import ClobClient
        from eth_account import Account

        host = "https://clob.polymarket.com"
        chain_id = 137  # Polygon mainnet
        # Step 1: create client with key, derive API creds
        _temp = ClobClient(host=host, chain_id=chain_id, key=POLYMARKET_PRIVATE_KEY)
        api_creds = _temp.create_or_derive_api_creds()
        # Step 2: funder = address that holds funds (EOA = same as signer; proxy = from env)
        funder = POLYMARKET_FUNDER_ADDRESS
        if not funder:
            account = Account.from_key(POLYMARKET_PRIVATE_KEY)
            funder = account.address
        # signature_type: 0=EOA, 1=email/Magic, 2=Gnosis Safe. Default 0 for direct wallet.
        signature_type = 1 if POLYMARKET_FUNDER_ADDRESS else 0
        CLOB_CLIENT = ClobClient(
            host=host,
            chain_id=chain_id,
            key=POLYMARKET_PRIVATE_KEY,
            creds=api_creds,
            signature_type=signature_type,
            funder=funder,
        )

        HAS_CLOB_AUTH = True
        pass
    except ImportError:
        pass
    except Exception:
        pass

if not POLYMARKET_PRIVATE_KEY:
    pass

if not TELEGRAM_BOT_TOKEN:
    pass

if not HAS_CLOB_AUTH:
    pass


def utc_now() -> datetime:
    """Return UTC now as naive datetime for compatibility with existing comparisons."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

# Polymarket API endpoints
POLYMARKET_GAMMA_API = (
    os.getenv("POLYMARKET_GAMMA_API")
    or os.getenv("POLY_GAMMA_API")
    or "https://gamma-api.polymarket.com"
)
POLYMARKET_CLOB_API = "https://clob.polymarket.com"
POLYMARKET_DATA_API = (
    os.getenv("POLYMARKET_DATA_API")
    or os.getenv("POLY_DATA_API")
    or "https://data-api.polymarket.com"
)

# Thresholds for whale detection
MIN_WHALE_BET_USD = float(
    os.getenv("MIN_WHALE_BET_USD")
    or os.getenv("MIN_WHALE_USD")
    or "20000"
)
MIN_VOLUME_SPIKE_MULTIPLIER = 5  # 5x normal volume
MIN_SMART_TRADER_WIN_RATE = 0.65
MIN_SMART_TRADER_TRADES = 20


#MIN_SMART_TRADERS = 3
#MIN_SMART_TRADER_BET = 5000
SMART_WINDOW_MINUTES = 15
MIN_LIFETIME_TRADES = 30
#MIN_CONSENSUS_TOTAL = 20000


MIN_SMART_TRADERS = 1
MIN_SMART_TRADER_BET = 100
MIN_CONSENSUS_TOTAL = 200

# Liquidity filter (skip thin markets when liquidity is known)
MIN_LIQUIDITY_USD = float(os.getenv("MIN_LIQUIDITY_USD", "10000"))
ALERT_COOLDOWN_MINUTES = 120

# Smart money thresholds (closed positions)
SMART_WINDOW_DAYS = 30
SMART_MIN_CLOSED_POSITIONS = 10
SMART_MIN_AVG_POSITION_USD = 500
SMART_MIN_REALIZED_PNL_USD = 5000

# Novelty gate thresholds
MIN_ODDS_MOVE_PCT = 0.05  # 5%
MIN_NET_INFLOW_1H_USD = 20000
NOVELTY_MIN_SIGNALS_SMART = int(os.getenv("NOVELTY_MIN_SIGNALS_SMART", "2"))
NOVELTY_MIN_SIGNALS_VOLUME = int(os.getenv("NOVELTY_MIN_SIGNALS_VOLUME", "1"))

# Daily caps per alert type
DAILY_CAP_BY_TYPE = {
    "whale_bet": int(os.getenv("WHALE_CAP_PER_DAY", "10")),
    "smart_money": int(os.getenv("SMART_CAP_PER_DAY", "6")),
    "volume_spike": int(os.getenv("VOLUME_CAP_PER_DAY", "4"))
}

# Optional debug-friendly thresholds for faster alerting during tests
if LOWER_THRESHOLDS:
    MIN_WHALE_BET_USD = 1000
    MIN_VOLUME_SPIKE_MULTIPLIER = 2
    MIN_SMART_TRADER_BET = 100
    MIN_CONSENSUS_TOTAL = 200
    MIN_LIQUIDITY_USD = 5000
    MIN_NET_INFLOW_1H_USD = 5000
    MIN_ODDS_MOVE_PCT = 0.02
    SMART_MIN_CLOSED_POSITIONS = 3
    SMART_MIN_AVG_POSITION_USD = 100
    SMART_MIN_REALIZED_PNL_USD = 500
    pass
# Simple keyword filters to focus on popular categories
CATEGORY_KEYWORDS = {
    "sports": ["nfl", "nba", "mlb", "nhl", "soccer", "football", "ufc", "boxing", "tennis", "golf", "f1", "formula 1", "premier league", "champions league", "world cup", "olympics"],
    "crypto": ["btc", "bitcoin", "eth", "ethereum", "sol", "solana", "xrp", "doge", "crypto", "memecoin", "stablecoin"],
    "stocks": ["stock", "stocks", "nasdaq", "nyse", "sp500", "s&p", "dow", "earnings", "sec", "ipo"],
    "politics": ["election", "president", "senate", "house", "congress", "governor", "parliament", "prime minister", "referendum", "vote", "campaign", "poll", "approval"]
}

MARKET_CATEGORIES = [
    c.strip().lower()
    for c in (os.getenv("MARKET_CATEGORIES", "") or "").split(",")
    if c.strip()
]


class Settings:
    """
    Lightweight settings proxy.
    Defaults to module globals, with optional per-instance overrides.
    """

    def __init__(self, overrides: Optional[Dict[str, Any]] = None):
        self._overrides = dict(overrides or {})

    def with_overrides(self, **kwargs: Any) -> "Settings":
        merged = dict(self._overrides)
        merged.update(kwargs)
        return Settings(merged)

    def __getattr__(self, name: str) -> Any:
        if name in self._overrides:
            return self._overrides[name]
        if name in globals():
            return globals()[name]
        raise AttributeError(f"Unknown setting: {name}")


SETTINGS = Settings()
