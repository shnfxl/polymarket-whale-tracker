import asyncio
import logging
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from .config import SETTINGS, Settings, utc_now
from .api_client import PolymarketAPIClient
from .state_store import InMemoryStateStore, StateStore

logger = logging.getLogger(__name__)


class PolymarketDataGenerator:
    """Generates activity data from real Polymarket API"""

    def __init__(
        self,
        api_client: PolymarketAPIClient,
        settings: Optional[Settings] = None,
        state_store: Optional[StateStore] = None,
    ):
        self.api_client = api_client
        self.settings = settings or SETTINGS
        self.last_check_time: Dict[str, datetime] = {}
        self.state_store = state_store or InMemoryStateStore()
        self.market_quality_cache: Dict[str, Tuple[datetime, Dict]] = {}
        self.api_semaphore = asyncio.Semaphore(max(1, self.settings.API_CONCURRENCY_LIMIT))
        self._cycle_trader_stats_cache: Dict[str, Dict] = {}
        self._cycle_trader_recent_cache: Dict[Tuple[str, int], List[Dict]] = {}
        self._cycle_market_flow_cache: Dict[Tuple[str, int], Dict] = {}
        self._cycle_net_position_cache: Dict[Tuple[str, str, int], float] = {}
        self._cycle_market_position_cache: Dict[Tuple[str, str], Optional[float]] = {}
        self.gate_counters: Dict[str, int] = {}
        self.reset_gate_counters()

    def start_cycle(self):
        """Reset short-lived caches used only within one processing cycle."""
        self._cycle_trader_stats_cache.clear()
        self._cycle_trader_recent_cache.clear()
        self._cycle_market_flow_cache.clear()
        self._cycle_net_position_cache.clear()
        self._cycle_market_position_cache.clear()

    async def _run_limited(self, coro):
        async with self.api_semaphore:
            return await coro

    async def _cached_get_trader_stats(self, address: str) -> Dict:
        key = (address or "").lower()
        if key in self._cycle_trader_stats_cache:
            return self._cycle_trader_stats_cache[key]
        result = await self._run_limited(self.api_client.get_trader_stats(address))
        self._cycle_trader_stats_cache[key] = result
        return result

    async def _cached_fetch_recent_trades(self, *, user: Optional[str] = None, market_id: Optional[str] = None, since_minutes: int = 60, min_cash: Optional[float] = None) -> List[Dict]:
        # Cache only query shapes we call repeatedly in-cycle.
        if user and not market_id and min_cash is None:
            key = ((user or "").lower(), int(since_minutes))
            if key in self._cycle_trader_recent_cache:
                return self._cycle_trader_recent_cache[key]
            result = await self._run_limited(
                self.api_client.fetch_recent_trades(since_minutes=since_minutes, user=user)
            )
            self._cycle_trader_recent_cache[key] = result
            return result
        return await self._run_limited(
            self.api_client.fetch_recent_trades(
                since_minutes=since_minutes,
                user=user,
                market_id=market_id,
                min_cash=min_cash
            )
        )

    async def _cached_get_market_flow(self, market_id: str, minutes: int) -> Dict:
        key = (market_id, int(minutes))
        if key in self._cycle_market_flow_cache:
            return self._cycle_market_flow_cache[key]
        result = await self._run_limited(self.api_client.get_market_flow_stats(market_id, minutes=minutes))
        self._cycle_market_flow_cache[key] = result
        return result

    async def _cached_get_net_position_change(self, address: str, market_id: str, minutes: int = 60) -> float:
        key = ((address or "").lower(), market_id, int(minutes))
        if key in self._cycle_net_position_cache:
            return self._cycle_net_position_cache[key]
        result = await self._run_limited(
            self.api_client.get_net_position_change(address, market_id, minutes=minutes)
        )
        self._cycle_net_position_cache[key] = result
        return result

    async def _cached_get_market_position_size(self, address: str, market_id: str) -> Optional[float]:
        key = ((address or "").lower(), market_id)
        if key in self._cycle_market_position_cache:
            return self._cycle_market_position_cache[key]
        result = await self._run_limited(self.api_client.get_market_position_size_usd(address, market_id))
        self._cycle_market_position_cache[key] = result
        return result

    def reset_gate_counters(self):
        self.gate_counters = {
            "input_trades": 0,
            "accepted": 0,
            "reject_duplicate": 0,
            "reject_missing_market": 0,
            "reject_market_liquidity": 0,
            "reject_market_volume": 0,
            "reject_relative_size": 0,
            "reject_not_popular": 0,
            "reject_market_target": 0,
            "reject_market_quality": 0,
            "reject_tail_price": 0,
            "reject_wallet_quality": 0,
            "reject_flow_quality": 0,
            "reject_impact_quality": 0,
            "reject_short_duration": 0,  # New: 5-min binaries, etc
            "reject_sports_threshold": 0,  # New: sports didn't meet higher bar
        }

    def _count_gate(self, key: str, amount: int = 1):
        self.gate_counters[key] = self.gate_counters.get(key, 0) + amount

    def snapshot_gate_counters(self) -> Dict[str, int]:
        return dict(self.gate_counters)

    def _is_popular_category(self, market: Dict) -> bool:
        """Filter markets to popular categories via keyword match."""
        title = (market.get("title") or "").lower()
        slug = (market.get("slug") or "").lower()
        text = f"{title} {slug}"
        for keywords in self.settings.CATEGORY_KEYWORDS.values():
            for kw in keywords:
                if kw in text:
                    return True
        return False

    def _is_high_signal_market(self, market: Dict) -> bool:
        """Allow high-depth markets even when category keywords are missing."""
        volume_24h = float(market.get("volume24h") or 0)
        liquidity = float(market.get("liquidity") or 0)
        return (
            volume_24h >= self.settings.MIN_MARKET_VOLUME_24H * self.settings.HIGH_SIGNAL_MARKET_VOLUME_MULTIPLIER
            or liquidity >= self.settings.MIN_LIQUIDITY_USD * self.settings.HIGH_SIGNAL_MARKET_LIQUIDITY_MULTIPLIER
        )

    def _market_in_scope(self, market: Dict) -> bool:
        """Toggleable category gate for smart-money/volume pipelines."""
        if self.settings.MARKET_CATEGORIES:
            return self._market_category(market) in self.settings.MARKET_CATEGORIES
        if not self.settings.REQUIRE_POPULAR_CATEGORY:
            return True
        return self._is_popular_category(market) or self._is_high_signal_market(market)

    @staticmethod
    def _percentile(values: List[float], q: float) -> Optional[float]:
        """Compute percentile with linear interpolation for small samples."""
        if not values:
            return None
        q = min(max(float(q or 0.0), 0.0), 1.0)
        arr = sorted(float(v) for v in values if v is not None)
        if not arr:
            return None
        if len(arr) == 1:
            return arr[0]
        pos = (len(arr) - 1) * q
        lo = int(math.floor(pos))
        hi = int(math.ceil(pos))
        if lo == hi:
            return arr[lo]
        weight = pos - lo
        return arr[lo] * (1.0 - weight) + arr[hi] * weight

    def _market_target_score(
        self,
        market: Dict,
        trade_count: int,
        unique_wallets: int,
        large_trade_count: int,
    ) -> float:
        """
        Market targeting score balances depth (vol/liq) and live whale activity.
        This avoids over-relying on static keyword category filters.
        """
        volume_24h = float(market.get("volume24h") or 0)
        liquidity = float(market.get("liquidity") or 0)
        vol_score = min(volume_24h / max(self.settings.MIN_MARKET_VOLUME_24H, 1.0), 3.0)
        liq_score = min(liquidity / max(self.settings.MIN_LIQUIDITY_USD, 1.0), 3.0)
        activity_score = min(float(trade_count) / 6.0, 2.0)
        unique_score = min(float(unique_wallets) / 4.0, 2.0)
        cluster_score = min(float(large_trade_count) / 2.0, 1.5)
        category_bonus = 0.5 if self._is_popular_category(market) else 0.0

        return (
            0.9 * vol_score
            + 0.8 * liq_score
            + 0.7 * activity_score
            + 0.6 * unique_score
            + 0.8 * cluster_score
            + category_bonus
        )

    def _market_url(self, market: Dict) -> Optional[str]:
        slug = market.get("slug")
        if not slug:
            return None
        return f"https://polymarket.com/market/{slug}"

    def _in_tail_price_band(self, price: Optional[float]) -> bool:
        if price is None:
            return False
        return float(price) < self.settings.MIN_PRICE_BAND or float(price) > self.settings.MAX_PRICE_BAND

    @staticmethod
    def _market_hours_remaining(market: Dict) -> Optional[float]:
        """Return hours until market ends, or None if unknown."""
        end_date = market.get("endDate")
        if not end_date:
            return None
        try:
            # Handle ISO format with or without timezone
            if isinstance(end_date, str):
                end_date = end_date.replace('Z', '+00:00')
                end_time = datetime.fromisoformat(end_date).replace(tzinfo=None)
            else:
                return None
            return (end_time - utc_now()).total_seconds() / 3600
        except Exception:
            return None

    def _is_short_duration_market(self, market: Dict) -> bool:
        """Check if market resolves too soon (e.g., 5-min binaries)."""
        hours = self._market_hours_remaining(market)
        if hours is None:
            return False  # Unknown duration, don't filter
        return hours < self.settings.MIN_MARKET_DURATION_HOURS

    def _is_sports_market(self, market: Dict) -> bool:
        """Check if market is sports-related (higher noise threshold)."""
        title = (market.get("title") or "").lower()
        slug = (market.get("slug") or "").lower()
        text = f"{title} {slug}"
        for kw in self.settings.CATEGORY_KEYWORDS.get("sports", []):
            if kw in text:
                return True
        return False

    def _market_category(self, market: Dict) -> str:
        title = (market.get("title") or "").lower()
        slug = (market.get("slug") or "").lower()
        text = f"{title} {slug}"
        for category, keywords in self.settings.CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    return category
        return "other"

    def _get_effective_whale_threshold(self, market: Dict, base_threshold: float) -> float:
        """Apply category-specific multipliers to whale threshold."""
        threshold = base_threshold
        if self._is_sports_market(market):
            threshold *= self.settings.SPORTS_THRESHOLD_MULTIPLIER
        return threshold

    async def _get_market_quality(self, market_id: str) -> Dict:
        """Basic anti-noise market quality metrics from recent trade flow."""
        now = utc_now()
        cached = self.market_quality_cache.get(market_id)
        if cached:
            ts, stats = cached
            if (now - ts).total_seconds() < 120:
                return stats

        recent = await self._cached_fetch_recent_trades(
            market_id=market_id,
            since_minutes=self.settings.MARKET_QUALITY_LOOKBACK_MINUTES,
            min_cash=None
        )
        wallets = {t.get("user") for t in recent if t.get("user")}
        sides = {t.get("side") for t in recent if t.get("side") in ("YES", "NO")}
        stats = {
            "trade_count": len(recent),
            "unique_traders": len(wallets),
            "two_sided": ("YES" in sides and "NO" in sides),
            "volume": sum(float(t.get("amount", 0) or 0) for t in recent),
        }
        self.market_quality_cache[market_id] = (now, stats)
        return stats

    def _passes_market_quality(self, stats: Dict) -> bool:
        if stats.get("trade_count", 0) < self.settings.MIN_MARKET_QUALITY_TRADES:
            return False
        if stats.get("unique_traders", 0) < self.settings.MIN_MARKET_QUALITY_UNIQUE_TRADERS:
            return False
        if self.settings.REQUIRE_TWO_SIDED_QUALITY and not stats.get("two_sided", False):
            return False
        return True

    @staticmethod
    def _wallet_tier(lifetime_volume: float) -> str:
        if lifetime_volume > 1_000_000:
            return "legend"
        if lifetime_volume > 250_000:
            return "pro"
        if lifetime_volume > 50_000:
            return "semi-pro"
        return "retail"

    def _classify_trader(self, trades: List[Dict]) -> Dict:
        """Classify trader by category concentration across markets."""
        if not trades:
            return {"label": "unknown", "markets": 0}

        market_titles = {}
        category_counts = {k: 0 for k in self.settings.CATEGORY_KEYWORDS.keys()}

        for t in trades:
            title = (t.get("market_title") or "").lower()
            market_titles[t.get("market") or title] = title
            for cat, keywords in self.settings.CATEGORY_KEYWORDS.items():
                if any(kw in title for kw in keywords):
                    category_counts[cat] += 1
                    break

        total = sum(category_counts.values())
        distinct_markets = len(market_titles)

        if total == 0:
            return {"label": "generalist", "markets": distinct_markets}

        top_cat = max(category_counts.items(), key=lambda x: x[1])
        if top_cat[1] / total >= 0.6 and distinct_markets >= 3:
            return {"label": f"{top_cat[0]} specialist", "markets": distinct_markets}

        if distinct_markets >= 4:
            return {"label": "event-driven", "markets": distinct_markets}

        return {"label": "generalist", "markets": distinct_markets}

    async def generate_whale_bets(self, limit: Optional[int] = None) -> List[Dict]:
        """Detect multiple whale bets from recent trades."""
        if limit is None:
            limit = self.settings.MAX_CANDIDATES_PER_TYPE
        self.reset_gate_counters()
        whale_min_fetch = min(self.settings.MIN_WHALE_BET_USD, self.settings.MIN_MARKET_VOLUME_24H * self.settings.REL_WHALE_VOLUME_PCT)
        trades = await self._cached_fetch_recent_trades(
            since_minutes=self.settings.WHALE_LOOKBACK_MINUTES,
            min_cash=whale_min_fetch
        )
        self._count_gate("input_trades", len(trades))
        if self.settings.DEBUG_LOG_API:
            logger.debug("DEBUG: whale_bet trades=%s min_cash=%s", len(trades), whale_min_fetch)

        if not trades:
            return []

        same_side_trade_details: Dict[Tuple[str, str], List[Dict[str, float]]] = {}
        market_trade_counts: Dict[str, int] = {}
        market_unique_wallets: Dict[str, set] = {}
        market_large_trade_counts: Dict[str, int] = {}
        market_amounts: Dict[str, List[float]] = {}
        all_amounts: List[float] = []
        for t in trades:
            m_id = t.get("market")
            side = t.get("side")
            user = t.get("user")
            amount = float(t.get("amount", 0) or 0)
            if not m_id or side not in ("YES", "NO") or not user:
                continue
            cluster_key = (m_id, side)
            same_side_trade_details.setdefault(cluster_key, []).append({
                "user": user,
                "amount": amount,
            })
            market_trade_counts[m_id] = market_trade_counts.get(m_id, 0) + 1
            market_unique_wallets.setdefault(m_id, set()).add(user)
            if amount >= self.settings.MIN_WHALE_BET_USD:
                market_large_trade_counts[m_id] = market_large_trade_counts.get(m_id, 0) + 1
            market_amounts.setdefault(m_id, []).append(amount)
            all_amounts.append(amount)

        global_adaptive_threshold = None
        if self.settings.ADAPTIVE_WHALE_THRESHOLD_ENABLED and len(all_amounts) >= max(3, self.settings.ADAPTIVE_WHALE_MIN_SAMPLES):
            global_adaptive_threshold = self._percentile(all_amounts, self.settings.ADAPTIVE_WHALE_PERCENTILE)

        candidates: List[Dict] = []
        for trade in sorted(trades, key=lambda t: float(t.get("amount", 0) or 0), reverse=True)[:max(1, self.settings.MAX_WHALE_ENRICH_TRADES)]:
            trade_id = trade.get("id", "")
            if self.state_store.is_processed_trade(trade_id):
                self._count_gate("reject_duplicate")
                continue

            amount_usd = float(trade.get("amount", 0) or 0)

            # Use market title from trade, or try to match by condition ID
            market_condition_id = trade.get("market", "")
            market_title = trade.get("market_title", "")

            if not market_condition_id:
                self._count_gate("reject_missing_market")
                continue

            # Resolve market from cache, preferring exact condition-id match.
            market = (
                self.api_client.market_cache.get(market_condition_id)
                or self.api_client.market_cache.get(str(market_condition_id).lower())
            )
            if not market and market_title:
                wanted_title = " ".join(str(market_title).split()).lower()
                for cached_market in self.api_client.market_cache.values():
                    cached_title = " ".join(str(cached_market.get("title", "")).split()).lower()
                    if cached_title and cached_title == wanted_title:
                        market = cached_market
                        break

            # If not found, create a basic market object from trade data
            if not market:
                market = {
                    "id": market_condition_id,
                    "title": market_title or f"Market {market_condition_id[:8]}",
                    "liquidity": 0,  # Unknown from trade data
                    "volume24h": 0
                }

            market_gates_enabled = not self.settings.DISABLE_MARKET_GATES

            # Gate 0: Short-duration market filter (5-min binaries, etc)
            if market_gates_enabled and self._is_short_duration_market(market):
                if self.settings.DEBUG_LOG_API:
                    hours = self._market_hours_remaining(market)
                    logger.debug("DEBUG: short duration filtered market=%s hours=%.1f", market_condition_id, hours)
                self._count_gate("reject_short_duration")
                continue

            # Check if sports market (will apply higher threshold)
            is_sports = self._is_sports_market(market)
            if self.settings.EXCLUDE_SPORTS_MARKETS and is_sports:
                self._count_gate("reject_not_popular")
                continue
            market_category = self._market_category(market)

            volume_24h = float(market.get("volume24h") or 0)
            liquidity = float(market.get("liquidity") or 0)
            market_amount_sample = market_amounts.get(market_condition_id, [])
            market_adaptive_threshold = None
            if self.settings.ADAPTIVE_WHALE_THRESHOLD_ENABLED and len(market_amount_sample) >= max(3, self.settings.ADAPTIVE_WHALE_MIN_SAMPLES):
                market_adaptive_threshold = self._percentile(market_amount_sample, self.settings.ADAPTIVE_WHALE_PERCENTILE)
            adaptive_abs_threshold_raw = market_adaptive_threshold if market_adaptive_threshold is not None else global_adaptive_threshold
            adaptive_abs_threshold = self.settings.MIN_WHALE_BET_USD
            if adaptive_abs_threshold_raw is not None:
                adaptive_abs_threshold = min(
                    self.settings.ADAPTIVE_WHALE_CAP_USD,
                    max(self.settings.ADAPTIVE_WHALE_FLOOR_USD, float(adaptive_abs_threshold_raw))
                )

            # Apply sports multiplier - sports markets have more retail noise
            effective_threshold = self._get_effective_whale_threshold(market, adaptive_abs_threshold)
            if market_gates_enabled and is_sports and amount_usd < effective_threshold:
                if self.settings.DEBUG_LOG_API:
                    logger.debug(
                        "DEBUG: sports threshold filtered amount=%.0f < threshold=%.0f",
                        amount_usd,
                        effective_threshold,
                    )
                self._count_gate("reject_sports_threshold")
                continue

            # Gate 1: Market quality (hard filters + tail filter)
            # Treat unknown market stats as "unknown", not "bad", so sparse API payloads
            # don't kill all candidates before downstream quality checks.
            liquidity_known = liquidity > 0
            volume_known = volume_24h > 0

            if market_gates_enabled:
                if liquidity_known and liquidity < self.settings.HARD_MIN_LIQUIDITY_USD:
                    self._count_gate("reject_market_liquidity")
                    continue
                if volume_known and volume_24h < self.settings.HARD_MIN_VOLUME_24H_USD:
                    self._count_gate("reject_market_volume")
                    continue
                meets_abs = amount_usd >= adaptive_abs_threshold
                meets_rel_vol = volume_known and amount_usd >= (volume_24h * self.settings.REL_WHALE_VOLUME_PCT)
                meets_rel_liq = liquidity_known and amount_usd >= (liquidity * self.settings.REL_WHALE_LIQUIDITY_PCT)
                meets_basic = meets_abs or meets_rel_vol or meets_rel_liq

                low_liquidity = liquidity_known and liquidity < self.settings.MIN_LIQUIDITY_USD
                low_volume = volume_known and volume_24h < self.settings.MIN_MARKET_VOLUME_24H
                if (low_liquidity or low_volume):
                    # Allow only if trade is exceptionally large relative to market
                    meets_low_liq_override = (
                        (liquidity_known and amount_usd >= liquidity * self.settings.LOW_LIQUIDITY_WHALE_LIQ_PCT) or
                        (volume_known and amount_usd >= volume_24h * self.settings.LOW_LIQUIDITY_WHALE_VOL_PCT) or
                        (amount_usd >= adaptive_abs_threshold * 2)
                    )
                    if not meets_low_liq_override:
                        self._count_gate("reject_relative_size")
                        continue

                if not meets_basic:
                    self._count_gate("reject_relative_size")
                    continue
                market_target_score = self._market_target_score(
                    market=market,
                    trade_count=market_trade_counts.get(market_condition_id, 0),
                    unique_wallets=len(market_unique_wallets.get(market_condition_id, set())),
                    large_trade_count=market_large_trade_counts.get(market_condition_id, 0),
                )
                if market_target_score < self.settings.MIN_MARKET_TARGET_SCORE and amount_usd < (adaptive_abs_threshold * self.settings.MARKET_TARGET_OVERRIDE_MULTIPLIER):
                    self._count_gate("reject_market_target")
                    self._count_gate("reject_not_popular")
                    continue

                market_quality = await self._get_market_quality(market_condition_id)
                if not self._passes_market_quality(market_quality):
                    if self.settings.DEBUG_LOG_API:
                        logger.debug(
                            "DEBUG: market quality filtered "
                            f"{market_condition_id} stats={market_quality}"
                        )
                    self._count_gate("reject_market_quality")
                    continue
            else:
                market_target_score = self._market_target_score(
                    market=market,
                    trade_count=market_trade_counts.get(market_condition_id, 0),
                    unique_wallets=len(market_unique_wallets.get(market_condition_id, set())),
                    large_trade_count=market_large_trade_counts.get(market_condition_id, 0),
                )
                market_quality = None

            # Get trader stats
            trader_address = trade.get("user", "")
            trader_stats, trader_recent, net_change, flow_1h, flow_24h, market_position_size = await asyncio.gather(
                self._cached_get_trader_stats(trader_address),
                self._cached_fetch_recent_trades(since_minutes=60 * 24, user=trader_address),
                self._cached_get_net_position_change(trader_address, market_condition_id, minutes=60),
                self._cached_get_market_flow(market_condition_id, minutes=60),
                self._cached_get_market_flow(market_condition_id, minutes=60 * 24),
                self._cached_get_market_position_size(trader_address, market_condition_id),
            )
            wallet_tier = self._wallet_tier(float(trader_stats.get("total_volume", 0) or 0))
            trader_class = self._classify_trader(trader_recent)

            # Odds before/after: use cached outcome price as baseline, then CLOB mid if available
            price = trade.get("price", 0.5)
            odds_before = self.api_client._extract_outcome_price(market, trade.get("side", "YES")) or price
            token_id = self.api_client._extract_token_id(market, trade.get("side", "YES"))
            odds_after = self.api_client._orderbook_mid(token_id) or odds_before
            reference_price = odds_after if odds_after is not None else odds_before
            if market_gates_enabled and self._in_tail_price_band(reference_price):
                if self.settings.DEBUG_LOG_API:
                    logger.debug(
                        "DEBUG: tail price filtered "
                        f"market={market_condition_id} price={reference_price:.4f}"
                    )
                self._count_gate("reject_tail_price")
                continue

            cluster_key = (market_condition_id, trade.get("side", "YES"))
            cluster_trades = same_side_trade_details.get(cluster_key, [])
            qualified_cluster_trades = [
                t for t in cluster_trades
                if float(t.get("amount", 0) or 0) >= effective_threshold
            ]
            cluster_wallets = {str(t.get("user") or "") for t in qualified_cluster_trades if t.get("user")}
            same_side_cluster_notional = sum(float(t.get("amount", 0) or 0) for t in qualified_cluster_trades)
            if trader_address and trader_address not in cluster_wallets:
                # Always include the alerting trade in cluster context.
                cluster_wallets.add(trader_address)
                same_side_cluster_notional += amount_usd
            same_side_whales = len(cluster_wallets)
            same_side_other_whales = max(0, same_side_whales - 1)
            if self.settings.DISABLE_CLUSTER_GATE:
                same_side_whales = 0
                same_side_cluster_notional = amount_usd
                same_side_other_whales = 0
            # Gate 2: Wallet quality
            if not self.settings.DISABLE_WALLET_GATE:
                if wallet_tier == "retail" and float(trader_stats.get("credibility", 0) or 0) < 4 and same_side_whales < 3:
                    self._count_gate("reject_wallet_quality")
                    continue

            odds_move_1h = None
            odds_move_24h = None
            odds_move_pct_1h = None
            odds_move_pct_24h = None
            if flow_1h.get("avg_yes_price") is not None:
                base_1h = flow_1h.get("avg_yes_price")
                odds_move_1h = odds_after - base_1h
                if base_1h:
                    odds_move_pct_1h = odds_move_1h / max(base_1h, 0.01)
            if flow_24h.get("avg_yes_price") is not None:
                base_24h = flow_24h.get("avg_yes_price")
                odds_move_24h = odds_after - base_24h
                if base_24h:
                    odds_move_pct_24h = odds_move_24h / max(base_24h, 0.01)

            # Gate 3: Flow quality
            flow_1h_trade_count = int(flow_1h.get("trade_count") or 0)
            sparse_flow = flow_1h_trade_count < max(1, self.settings.SPARSE_FLOW_MIN_TRADES)
            flow_signal = (
                abs(float(net_change or 0)) >= self.settings.FLOW_GATE_NET_POSITION_USD or
                abs(float(flow_1h.get("net_inflow") or 0)) >= self.settings.FLOW_GATE_MARKET_INFLOW_USD or
                (same_side_whales >= self.settings.FLOW_GATE_CLUSTER_MIN if not self.settings.DISABLE_CLUSTER_GATE else False)
            )
            if not self.settings.DISABLE_TREND_GATE:
                if not flow_signal and not (self.settings.ALLOW_SPARSE_FLOW_BYPASS and sparse_flow and amount_usd >= adaptive_abs_threshold):
                    self._count_gate("reject_flow_quality")
                    continue

            # Gate 4: Impact quality
            odds_impact = abs(float(odds_after or 0) - float(odds_before or 0))
            impact_signal = (
                odds_impact >= self.settings.IMPACT_GATE_MIN_ABS or
                (odds_move_pct_1h is not None and abs(float(odds_move_pct_1h)) >= self.settings.IMPACT_GATE_MIN_PCT)
            )
            if not self.settings.DISABLE_IMPACT_GATE:
                if not impact_signal and not (self.settings.ALLOW_SPARSE_FLOW_BYPASS and sparse_flow and same_side_whales >= self.settings.FLOW_GATE_CLUSTER_MIN):
                    self._count_gate("reject_impact_quality")
                    continue
            self.state_store.remember_processed_trade(
                trade_id,
                max_size=self.settings.PROCESSED_TRADES_MAX,
                trim_to=self.settings.PROCESSED_TRADES_TRIM_TO,
            )

            candidates.append({
                "type": "whale_bet",
                "market": market,
                "market_url": self._market_url(market),
                "whale": {
                    "address": trader_address,
                    "total_volume": trader_stats.get("total_volume", amount_usd),
                    "credibility": trader_stats.get("credibility", 0),
                    "avg_bet": trader_stats.get("avg_bet", 0),
                    "trade_count": trader_stats.get("trade_count", 0),
                    "tier": wallet_tier,
                    "profile": trader_class.get("label"),
                    "active_markets": trader_class.get("markets"),
                    "nickname": trader_address[:8] + "..." if len(trader_address) > 8 else trader_address
                },
                "amount": amount_usd,
                "side": trade.get("side", "YES"),
                "side_label": trade.get("side_label", trade.get("side", "YES")),
                "same_side_whales": same_side_whales,
                "same_side_other_whales": same_side_other_whales,
                "same_side_notional": same_side_cluster_notional,
                "is_new_trader": trader_stats.get("trade_count", 0) <= 3,
                "is_sports_market": is_sports,
                "market_category": market_category,
                "market_position_size_usd": market_position_size,
                "odds_before": odds_before,
                "odds_after": odds_after,
                "net_position_1h": net_change,
                "market_net_inflow_1h": flow_1h.get("net_inflow"),
                "market_net_inflow_24h": flow_24h.get("net_inflow"),
                "market_avg_yes_1h": flow_1h.get("avg_yes_price"),
                "market_avg_yes_24h": flow_24h.get("avg_yes_price"),
                "market_odds_move_1h": odds_move_1h,
                "market_odds_move_24h": odds_move_24h,
                "market_odds_move_pct_1h": odds_move_pct_1h,
                "market_odds_move_pct_24h": odds_move_pct_24h,
                "market_quality": market_quality,
                "market_target_score": market_target_score,
                "adaptive_abs_threshold": adaptive_abs_threshold,
                "effective_threshold": effective_threshold,
                "market_live_trade_count": market_trade_counts.get(market_condition_id, 0),
                "timestamp": trade.get("timestamp", utc_now())
            })
            self._count_gate("accepted")

            if len(candidates) >= max(1, limit):
                break

        return candidates

    async def generate_whale_bet(self) -> Optional[Dict]:
        candidates = await self.generate_whale_bets(limit=1)
        return candidates[0] if candidates else None

    async def generate_smart_money_moves(self, limit: Optional[int] = None) -> List[Dict]:
        """Detect coordinated smart money activity."""
        if limit is None:
            limit = self.settings.MAX_CANDIDATES_PER_TYPE
        logger.info("Running smart money detection...")

        trades = await self._cached_fetch_recent_trades(
            since_minutes=self.settings.SMART_LOOKBACK_MINUTES,
            min_cash=self.settings.MIN_SMART_TRADER_BET
        )
        if self.settings.DEBUG_LOG_API:
            logger.debug(
                "DEBUG: smart_money trades=%s min_cash=%s",
                len(trades),
                self.settings.MIN_SMART_TRADER_BET,
            )
        recent_cutoff = utc_now() - timedelta(minutes=self.settings.SMART_WINDOW_MINUTES)

        market_trades: Dict[str, Dict[str, List[Dict]]] = {}

        for trade in trades:
            market_id = trade.get("market", "")
            side = trade.get("side", "")
            trader = trade.get("user", "")

            if not market_id or not trader:
                continue

            if side not in ("YES", "NO"):
                continue

            if market_id not in market_trades:
                market_trades[market_id] = {"YES": [], "NO": []}

            market_trades[market_id][side].append(trade)

        candidates: List[Dict] = []
        for market_id, sides in market_trades.items():
            for side, side_trades in sides.items():

                if len(side_trades) < self.settings.MIN_SMART_TRADERS:
                    continue

                traders_by_address: Dict[str, List[Dict]] = {}
                for trade in side_trades:
                    addr = trade.get("user", "")
                    traders_by_address.setdefault(addr, []).append(trade)

                smart_traders = []

                for addr, trader_trades in traders_by_address.items():
                    stats = await self._cached_get_trader_stats(addr)

                    total_amount = sum(t.get("amount", 0) for t in trader_trades)

                    if (
                        stats.get("closed_positions", 0) >= self.settings.SMART_MIN_CLOSED_POSITIONS and
                        stats.get("avg_position", 0) >= self.settings.SMART_MIN_AVG_POSITION_USD and
                        stats.get("realized_pnl", 0) >= self.settings.SMART_MIN_REALIZED_PNL_USD and
                        total_amount >= self.settings.MIN_SMART_TRADER_BET
                    ):
                        smart_traders.append({
                            "address": addr,
                            "total_volume": stats.get("total_volume", 0),
                            "trade_count": stats.get("trade_count", 0),
                            "avg_bet": stats.get("avg_bet", 0),
                            "credibility": stats.get("credibility", 0),
                            "win_rate": stats.get("win_rate", 0),
                            "avg_position": stats.get("avg_position", 0),
                            "realized_pnl": stats.get("realized_pnl", 0),
                            "closed_positions": stats.get("closed_positions", 0),
                            "amount": total_amount,
                            "nickname": addr[:8] + "..." if len(addr) > 8 else addr
                        })

                if len(smart_traders) < self.settings.MIN_SMART_TRADERS:
                    continue

                total_amount = sum(t["amount"] for t in smart_traders)
                if total_amount < self.settings.MIN_CONSENSUS_TOTAL:
                    continue

                # Distinct smart wallets active recently
                smart_addresses = {t["address"] for t in smart_traders}
                recent_wallets = {
                    t.get("user")
                    for t in side_trades
                    if t.get("timestamp") and t["timestamp"] >= recent_cutoff
                    and t.get("user") in smart_addresses
                }

                if len(recent_wallets) < 2:
                    continue

                # Market lookup
                market = self.api_client.market_cache.get(market_id)
                if not market:
                    first_trade = side_trades[0]
                    market_title = first_trade.get("market_title", "")
                    market = {
                        "id": market_id,
                        "title": market_title or f"Market {market_id[:8]}",
                        "liquidity": 0,
                        "volume24h": 0
                    }
                is_sports = self._is_sports_market(market)
                if self.settings.EXCLUDE_SPORTS_MARKETS and is_sports:
                    continue
                market_category = self._market_category(market)

                if market.get("liquidity") and market["liquidity"] < self.settings.MIN_LIQUIDITY_USD:
                    continue
                if float(market.get("volume24h") or 0) < self.settings.MIN_MARKET_VOLUME_24H:
                    continue
                if not self._market_in_scope(market):
                    continue
                # Skip short-duration markets
                if self._is_short_duration_market(market):
                    continue

                flow_1h, flow_24h = await asyncio.gather(
                    self._cached_get_market_flow(market_id, minutes=60),
                    self._cached_get_market_flow(market_id, minutes=60 * 24),
                )
                if self._in_tail_price_band(flow_1h.get("avg_yes_price")):
                    continue
                yes_token = self.api_client._extract_token_id(market, "YES")
                current_yes = self.api_client._orderbook_mid(yes_token) or flow_1h.get("avg_yes_price")
                if self._in_tail_price_band(current_yes):
                    continue
                odds_move_pct_1h = None
                odds_move_pct_24h = None
                if current_yes and flow_1h.get("avg_yes_price"):
                    base_1h = flow_1h.get("avg_yes_price")
                    odds_move_pct_1h = (current_yes - base_1h) / max(base_1h, 0.01)
                if current_yes and flow_24h.get("avg_yes_price"):
                    base_24h = flow_24h.get("avg_yes_price")
                    odds_move_pct_24h = (current_yes - base_24h) / max(base_24h, 0.01)

                candidates.append({
                    "type": "smart_money",
                    "market": market,
                    "market_url": self._market_url(market),
                    "is_sports_market": is_sports,
                    "market_category": market_category,
                    "traders": smart_traders,
                    "total_amount": total_amount,
                    "consensus_side": side,
                    "market_net_inflow_1h": flow_1h.get("net_inflow"),
                    "market_net_inflow_24h": flow_24h.get("net_inflow"),
                    "market_avg_yes_1h": flow_1h.get("avg_yes_price"),
                    "market_avg_yes_24h": flow_24h.get("avg_yes_price"),
                    "market_odds_move_pct_1h": odds_move_pct_1h,
                    "market_odds_move_pct_24h": odds_move_pct_24h,
                    "timestamp": utc_now()
                })

        candidates.sort(
            key=lambda x: float(x.get("total_amount", 0) or 0),
            reverse=True
        )
        return candidates[:max(1, limit)]

    async def generate_smart_money_move(self) -> Optional[Dict]:
        candidates = await self.generate_smart_money_moves(limit=1)
        return candidates[0] if candidates else None

    async def generate_volume_spikes(self, limit: Optional[int] = None) -> List[Dict]:
        """Detect multiple volume spikes."""
        if limit is None:
            limit = self.settings.MAX_CANDIDATES_PER_TYPE
        if self.api_client.market_cache:
            deduped: Dict[str, Dict] = {}
            for market in self.api_client.market_cache.values():
                market_id = str(market.get("id") or "")
                if market_id and market_id not in deduped:
                    deduped[market_id] = market
            markets = list(deduped.values())
        else:
            markets = await self._run_limited(
                self.api_client.fetch_markets(limit=self.settings.MARKET_LIMIT, sort_by=self.settings.MARKET_SORT_BY)
            )
        markets.sort(
            key=lambda m: (
                float(m.get("volume24h") or 0),
                float(m.get("liquidity") or 0),
            ),
            reverse=True,
        )
        scan_cap = max(0, int(self.settings.VOLUME_MARKET_SCAN_LIMIT or 0))
        if scan_cap:
            markets = markets[:scan_cap]
        logger.info("Markets scanned for volume spikes: %s", len(markets))
        if self.settings.DEBUG_LOG_API:
            logger.debug("DEBUG: volume_spike markets=%s", len(markets))

        candidates: List[Dict] = []
        for market in markets:
            market_id = market.get("id", "")
            if not market_id:
                continue
            is_sports = self._is_sports_market(market)
            if self.settings.EXCLUDE_SPORTS_MARKETS and is_sports:
                continue
            market_category = self._market_category(market)
            if market.get("liquidity") and market["liquidity"] < self.settings.MIN_LIQUIDITY_USD:
                continue
            if float(market.get("volume24h") or 0) < self.settings.MIN_MARKET_VOLUME_24H:
                continue
            if not self._market_in_scope(market):
                continue
            # Skip short-duration markets (5-min binaries, etc)
            if self._is_short_duration_market(market):
                continue

            # Get volume history
            volume_history = await self._run_limited(self.api_client.get_market_volume_history(market_id, hours=24))

            if len(volume_history) < 2:
                continue

            # Calculate average hourly volume (last 24h)
            avg_hourly = sum(volume_history[:-1]) / max(len(volume_history) - 1, 1)
            current_hour_volume = volume_history[-1] if volume_history else 0

            if avg_hourly == 0:
                continue

            if current_hour_volume < self.settings.MIN_VOLUME_SPIKE_1H_USD:
                continue

            multiplier = current_hour_volume / avg_hourly if avg_hourly > 0 else 0

            if multiplier >= self.settings.MIN_VOLUME_SPIKE_MULTIPLIER:
                # Get notable trades in the spike
                recent_trades = await self._cached_fetch_recent_trades(
                    market_id=market_id,
                    since_minutes=self.settings.VOLUME_NOTABLE_LOOKBACK_MINUTES
                )

                trader_addresses = sorted({
                    str(trade.get("user", "")).strip()
                    for trade in recent_trades
                    if trade.get("amount", 0) >= self.settings.MIN_WHALE_BET_USD and trade.get("user")
                })
                stats_pairs = await asyncio.gather(
                    *(self._cached_get_trader_stats(addr) for addr in trader_addresses)
                ) if trader_addresses else []
                trader_stats_map = dict(zip(trader_addresses, stats_pairs))
                notable_trades = []
                for trade in recent_trades:
                    if trade.get("amount", 0) >= self.settings.MIN_WHALE_BET_USD:
                        trader_address = trade.get("user", "")
                        stats = trader_stats_map.get(trader_address) or {}
                        notable_trades.append({
                            "whale": {
                                "address": trader_address,
                                "total_volume": stats.get("total_volume", 0),
                                "credibility": stats.get("credibility", 0),
                                "nickname": trader_address[:8] + "..." if len(trader_address) > 8 else trader_address
                            },
                            "amount": trade.get("amount", 0),
                            "side": trade.get("side", "YES")
                        })

                volume_24h = market.get("volume24h", 0)
                flow_1h, flow_24h = await asyncio.gather(
                    self._cached_get_market_flow(market_id, minutes=60),
                    self._cached_get_market_flow(market_id, minutes=60 * 24),
                )
                yes_token = self.api_client._extract_token_id(market, "YES")
                current_yes = self.api_client._orderbook_mid(yes_token) or flow_1h.get("avg_yes_price")
                if self._in_tail_price_band(current_yes):
                    continue
                odds_move_pct_1h = None
                odds_move_pct_24h = None
                if current_yes and flow_1h.get("avg_yes_price"):
                    base_1h = flow_1h.get("avg_yes_price")
                    odds_move_pct_1h = (current_yes - base_1h) / max(base_1h, 0.01)
                if current_yes and flow_24h.get("avg_yes_price"):
                    base_24h = flow_24h.get("avg_yes_price")
                    odds_move_pct_24h = (current_yes - base_24h) / max(base_24h, 0.01)

                candidates.append({
                    "type": "volume_spike",
                    "market": market,
                    "market_url": self._market_url(market),
                    "is_sports_market": is_sports,
                    "market_category": market_category,
                    "volume_24h": volume_24h,
                    "volume_1h": current_hour_volume,
                    "notable_trades": notable_trades,
                    "market_net_inflow_1h": flow_1h.get("net_inflow"),
                    "market_net_inflow_24h": flow_24h.get("net_inflow"),
                    "market_avg_yes_1h": flow_1h.get("avg_yes_price"),
                    "market_avg_yes_24h": flow_24h.get("avg_yes_price"),
                    "market_odds_move_pct_1h": odds_move_pct_1h,
                    "market_odds_move_pct_24h": odds_move_pct_24h,
                    "timestamp": utc_now()
                })

                if len(candidates) >= max(1, limit):
                    break

        candidates.sort(
            key=lambda x: (
                float(x.get("volume_1h", 0) or 0),
                float(x.get("volume_24h", 0) or 0),
            ),
            reverse=True
        )
        return candidates[:max(1, limit)]

    async def generate_volume_spike(self) -> Optional[Dict]:
        candidates = await self.generate_volume_spikes(limit=1)
        return candidates[0] if candidates else None
