from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import aiohttp

from .config import SETTINGS, Settings, utc_now

logger = logging.getLogger(__name__)

class PolymarketAPIClient:
    """Client for fetching real Polymarket data"""

    def __init__(self, api_key: Optional[str] = None, settings: Optional[Settings] = None, clob_client=None):
        self.api_key = api_key
        self.settings = settings or SETTINGS
        self.clob_client = clob_client if clob_client is not None else self.settings.CLOB_CLIENT
        self.session: Optional[aiohttp.ClientSession] = None
        self.market_cache: Dict[str, Dict] = {}
        self.volume_history: Dict[str, List[Tuple[datetime, float]]] = {}  # market_id -> [(timestamp, volume)]
        self.trader_stats_cache: Dict[str, Dict] = {}
        self._trade_error_logged = False  # Track if we've logged trade errors
        self._last_trade_fetch: Optional[datetime] = None
        self._trade_cache: List[Dict] = []  # Cache recent trades
        self._api_stats: Dict[str, object] = {
            "requests": 0,
            "retries": 0,
            "timeouts": 0,
            "http_errors": 0,
            "other_errors": 0,
            "by_endpoint": {},
        }

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def _debug(self, msg: str):
        if self.settings.DEBUG_LOG_API:
            logger.debug(msg)

    @staticmethod
    def _endpoint_key(url: str) -> str:
        try:
            path = url.split("://", 1)[-1].split("/", 1)[-1]
            return "/" + path.split("?", 1)[0]
        except Exception:
            return url

    def reset_api_stats(self):
        self._api_stats = {
            "requests": 0,
            "retries": 0,
            "timeouts": 0,
            "http_errors": 0,
            "other_errors": 0,
            "by_endpoint": {},
        }

    def snapshot_api_stats(self) -> Dict:
        return {
            "requests": int(self._api_stats.get("requests", 0)),
            "retries": int(self._api_stats.get("retries", 0)),
            "timeouts": int(self._api_stats.get("timeouts", 0)),
            "http_errors": int(self._api_stats.get("http_errors", 0)),
            "other_errors": int(self._api_stats.get("other_errors", 0)),
            "by_endpoint": dict(self._api_stats.get("by_endpoint", {})),
        }

    async def _get_json(self, url: str, params: Optional[Dict] = None) -> Dict:
        if not self.session:
            self.session = aiohttp.ClientSession()
        last_err = None
        retries = self.settings.API_RETRIES
        timeout_seconds = self.settings.API_TIMEOUT_SECONDS
        endpoint = self._endpoint_key(url)
        for attempt in range(retries + 1):
            self._api_stats["requests"] = int(self._api_stats.get("requests", 0)) + 1
            by_endpoint = self._api_stats.setdefault("by_endpoint", {})
            by_endpoint[endpoint] = int(by_endpoint.get(endpoint, 0)) + 1
            try:
                async with self.session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=timeout_seconds)
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        if resp.status == 429 or resp.status >= 500:
                            retry_after = resp.headers.get("retry-after")
                            if self.settings.DEBUG_LOG_API:
                                logger.debug(
                                    f"API {resp.status} {url} retry_after={retry_after} "
                                    f"(attempt {attempt + 1}/{retries + 1})"
                                )
                            if retry_after:
                                try:
                                    await asyncio.sleep(float(retry_after))
                                except Exception:
                                    await asyncio.sleep(1 + attempt)
                            else:
                                await asyncio.sleep(1 + attempt)
                            self._api_stats["http_errors"] = int(self._api_stats.get("http_errors", 0)) + 1
                            self._api_stats["retries"] = int(self._api_stats.get("retries", 0)) + 1
                            last_err = Exception(f"HTTP {resp.status} for {url} body={body[:500]}")
                            continue
                        self._api_stats["http_errors"] = int(self._api_stats.get("http_errors", 0)) + 1
                        raise Exception(f"HTTP {resp.status} for {url} body={body[:500]}")
                    data = await resp.json()
                    self._debug(f"DEBUG: GET {url} -> type={type(data).__name__}")
                    return data
            except asyncio.TimeoutError as e:
                last_err = e
                self._api_stats["timeouts"] = int(self._api_stats.get("timeouts", 0)) + 1
                self._api_stats["retries"] = int(self._api_stats.get("retries", 0)) + 1
                if self.settings.DEBUG_LOG_API:
                    logger.debug(
                        "API timeout after %ss for %s (attempt %s/%s)",
                        timeout_seconds,
                        url,
                        attempt + 1,
                        retries + 1,
                    )
                await asyncio.sleep(1 + attempt)
            except Exception as e:
                last_err = e
                self._api_stats["other_errors"] = int(self._api_stats.get("other_errors", 0)) + 1
                if attempt < retries:
                    self._api_stats["retries"] = int(self._api_stats.get("retries", 0)) + 1
                if self.settings.DEBUG_LOG_API:
                    logger.debug(
                        "API error for %s: %r (attempt %s/%s)",
                        url,
                        e,
                        attempt + 1,
                        retries + 1,
                    )
                await asyncio.sleep(1 + attempt)
        raise last_err

    def _extract_token_id(self, market: Dict, side: str) -> Optional[str]:
        """Extract outcome token id from market data for YES/NO."""
        # Common shapes in Gamma responses
        outcome_ids = market.get("outcomeTokenIds") or market.get("outcome_token_ids")
        if isinstance(outcome_ids, list) and len(outcome_ids) >= 2:
            return outcome_ids[0] if side == "YES" else outcome_ids[1]

        tokens = market.get("tokens")
        if isinstance(tokens, list):
            # Try to match by outcome name if present
            for t in tokens:
                outcome = (t.get("outcome") or t.get("name") or "").upper()
                if side == "YES" and outcome == "YES":
                    return t.get("tokenId") or t.get("token_id")
                if side == "NO" and outcome == "NO":
                    return t.get("tokenId") or t.get("token_id")
            # Fallback: positional if two tokens
            if len(tokens) >= 2:
                return tokens[0].get("tokenId") if side == "YES" else tokens[1].get("tokenId")

        return None

    def _extract_outcome_price(self, market: Dict, side: str) -> Optional[float]:
        """Get cached outcome price from market if available."""
        prices = market.get("outcomePrices") or market.get("outcome_prices")
        if isinstance(prices, list) and len(prices) >= 2:
            try:
                return float(prices[0] if side == "YES" else prices[1])
            except Exception:
                return None
        return None

    def _orderbook_mid(self, token_id: str) -> Optional[float]:
        """Get mid price from CLOB orderbook for a token id."""
        if not self.clob_client or not token_id:
            return None
        try:
            if hasattr(self.clob_client, "get_orderbook"):
                ob = self.clob_client.get_orderbook(token_id)
            elif hasattr(self.clob_client, "get_order_book"):
                ob = self.clob_client.get_order_book(token_id)
            else:
                return None

            bids = ob.get("bids") or []
            asks = ob.get("asks") or []

            def _best(levels, key):
                if not levels:
                    return None
                level = levels[0]
                return float(level.get(key) or level.get("price") or 0)

            best_bid = _best(bids, "price")
            best_ask = _best(asks, "price")

            if best_bid and best_ask:
                return (best_bid + best_ask) / 2
            return best_bid or best_ask
        except Exception:
            return None

    async def get_net_position_change(self, address: str, market_id: str, minutes: int = 60) -> float:
        """Compute net YES/NO flow for a wallet in a market over a window (USD)."""
        trades = await self.fetch_recent_trades(
            since_minutes=minutes,
            user=address
        )
        net = 0.0
        for t in trades:
            if t.get("market") != market_id:
                continue
            amt = float(t.get("amount", 0) or 0)
            side = t.get("side")
            if side == "YES":
                net += amt
            elif side == "NO":
                net -= amt
        return net

    async def get_market_flow_stats(self, market_id: str, minutes: int) -> Dict:
        """Compute net inflow and simple price stats for a market window."""
        trades = await self.fetch_recent_trades(
            market_id=market_id,
            since_minutes=minutes
        )
        net_inflow = 0.0
        yes_prices = []
        for t in trades:
            amt = float(t.get("amount", 0) or 0)
            side = t.get("side")
            if side == "YES":
                net_inflow += amt
                if t.get("price"):
                    yes_prices.append(float(t["price"]))
            elif side == "NO":
                net_inflow -= amt

        avg_yes = sum(yes_prices) / len(yes_prices) if yes_prices else None
        last_yes = yes_prices[0] if yes_prices else None

        return {
            "net_inflow": net_inflow,
            "avg_yes_price": avg_yes,
            "last_yes_price": last_yes,
            "trade_count": len(trades)
        }

    async def fetch_closed_positions(self, address: str, since_days: int = 30) -> List[Dict]:
        """Fetch closed positions for a user from Data API and filter by time."""
        if not self.session:
            self.session = aiohttp.ClientSession()

        params = {
            "user": address,
            "limit": "200",
            "offset": "0"
        }
        try:
            raw = await self._get_json(f"{self.settings.POLYMARKET_DATA_API}/closed-positions", params=params)
            self._debug(f"DEBUG: closed-positions user={address[:6]}... raw={len(raw)}")
        except Exception as e:
            if not self._trade_error_logged:
                logger.warning("Error fetching closed positions: %s", e)
                self._trade_error_logged = True
            return []

        cutoff = utc_now() - timedelta(days=since_days)
        out = []
        for p in raw:
            ts = p.get("timestamp")
            if ts is None:
                continue
            try:
                closed_time = datetime.utcfromtimestamp(int(ts))
            except Exception:
                continue
            if closed_time < cutoff:
                continue
            out.append(p)
        return out

    async def fetch_markets(self, limit: int = 100, active: bool = True, sort_by: str = "none") -> List[Dict]:
        """Fetch active markets from Polymarket Gamma API (REST)"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        try:
            params = {
                "limit": limit,
                "active": str(active).lower(),
                "closed": "false"
            }
            data = await self._get_json(f"{self.settings.POLYMARKET_GAMMA_API}/markets", params=params)
            self._debug(f"DEBUG: markets raw={len(data)} limit={limit} active={active}")
            markets = []
            for idx, market in enumerate(data):
                market_id = market.get("conditionId") or market.get("id", "")
                mapped = {
                    "id": market_id,
                    "conditionId": market.get("conditionId"),
                    "title": market.get("question", ""),
                    "liquidity": float(market.get("liquidity", 0) or 0),
                    "volume24h": float(market.get("volume24h", market.get("volume24hr", 0)) or 0),
                    "outcomes": market.get("outcomes", []),
                    "outcomePrices": market.get("outcomePrices", []),
                    "endDate": market.get("endDate"),
                    "image": market.get("image"),
                    "slug": market.get("slug", "")
                }
                if self.settings.DEBUG_LOG_API and idx < 5:
                    logger.debug(
                        "DEBUG: market sample "
                        f"title={mapped['title']!r} "
                        f"liquidity={mapped['liquidity']} "
                        f"volume24h={mapped['volume24h']} "
                        f"raw_volume24h={market.get('volume24h')} "
                        f"raw_volume24hr={market.get('volume24hr')}"
                    )
                markets.append(mapped)
                # Keep both raw and lowercase keys; trade payloads can vary in casing.
                if market_id:
                    self.market_cache[market_id] = mapped
                    self.market_cache[str(market_id).lower()] = mapped
            if sort_by in ("volume", "liquidity"):
                key = "volume24h" if sort_by == "volume" else "liquidity"
                markets.sort(key=lambda m: float(m.get(key, 0) or 0), reverse=True)
            return markets
        except Exception as e:
            logger.warning("Error fetching markets: %s", e)
        return []

    async def fetch_recent_trades(
        self,
        market_id: Optional[str] = None,
        since_minutes: int = 30,
        min_cash: Optional[float] = None,
        user: Optional[str] = None,
    ) -> List[Dict]:
        """Fetch recent trades from Data API with pagination and filter by timestamp locally."""
        if not self.session:
            self.session = aiohttp.ClientSession()

        params_base: Dict[str, str] = {
            "limit": str(max(1, self.settings.TRADE_PAGE_SIZE)),
            "takerOnly": "true",
        }
        if market_id:
            params_base["market"] = market_id
        if user:
            params_base["user"] = user
        if min_cash is not None:
            params_base["filterType"] = "CASH"
            params_base["filterAmount"] = str(min_cash)

        now = utc_now()
        cutoff = now - timedelta(minutes=since_minutes)
        raw: List[Dict] = []

        page_size = max(1, self.settings.TRADE_PAGE_SIZE)
        for page_idx in range(max(1, self.settings.TRADE_MAX_PAGES)):
            offset = page_idx * page_size
            params = dict(params_base)
            params["offset"] = str(offset)
            try:
                page = await self._get_json(f"{self.settings.POLYMARKET_DATA_API}/trades", params=params)
                self._debug(
                    f"DEBUG: trades page={page_idx + 1} raw={len(page)} market={market_id} "
                    f"user={user} min_cash={min_cash}"
                )
            except Exception as e:
                if not self._trade_error_logged:
                    logger.warning("Error fetching trades from Data API: %s", e)
                    self._trade_error_logged = True
                break

            if not page:
                break

            raw.extend(page)

            oldest_ts = page[-1].get("timestamp")
            if oldest_ts is not None:
                try:
                    oldest_time = datetime.utcfromtimestamp(int(oldest_ts))
                    if oldest_time < cutoff:
                        break
                except Exception:
                    pass

            if len(page) < page_size:
                break

        trades: List[Dict] = []
        for t in raw:
            ts = t.get("timestamp")
            if ts is None:
                continue
            trade_time = datetime.utcfromtimestamp(int(ts))
            if trade_time < cutoff:
                continue

            price = float(t.get("price", 0) or 0)
            size = float(t.get("size", 0) or 0)
            usdc_size = t.get("usdcSize")
            if usdc_size is not None:
                amount = float(usdc_size)
            elif price and size:
                amount = price * size
            else:
                amount = size

            outcome_index = t.get("outcomeIndex")
            outcome_raw = str(t.get("outcome") or "").strip()
            outcome_lower = outcome_raw.lower()
            if outcome_index is not None:
                side = "YES" if int(outcome_index) == 0 else "NO"
            elif outcome_lower == "yes":
                side = "YES"
            elif outcome_lower == "no":
                side = "NO"
            else:
                side = "UNKNOWN"
            side_label = side
            if outcome_raw:
                side_label = outcome_raw if outcome_lower not in ("yes", "no") else outcome_lower.upper()

            trades.append({
                "id": t.get("transactionHash") or f"{t.get('proxyWallet','')}-{ts}",
                "user": (t.get("proxyWallet") or "").lower(),
                "market": t.get("conditionId"),
                "market_title": t.get("title", ""),
                "amount": amount,
                "price": price,
                "side": side,
                "side_label": side_label,
                "timestamp": trade_time,
                "tx_hash": t.get("transactionHash"),
                "outcome": t.get("outcome"),
            })

        self._debug(f"DEBUG: trades filtered={len(trades)} since_minutes={since_minutes}")
        return trades

    def _parse_clob_timestamp(self, trade: Dict) -> Optional[datetime]:
        """Parse timestamp from CLOB API trade data"""
        ts = trade.get("timestamp") or trade.get("createdAt") or trade.get("time")
        if not ts:
            return None

        try:
            if isinstance(ts, (int, float)):
                return datetime.utcfromtimestamp(ts / 1000 if ts > 1e10 else ts)
            elif isinstance(ts, str):
                return datetime.fromisoformat(ts.replace('Z', '+00:00'))
        except Exception:
            pass
        return None


    async def get_trader_stats(self, address: str) -> Dict:
        """Get trader statistics using credibility metrics instead of fake win rate"""

        # Cache check
        cached = self.trader_stats_cache.get(address)
        if cached:
            # Refresh every 6 hours
            if (datetime.now() - cached.get("last_updated", datetime.min)).total_seconds() < 21600:
                return cached

        # Pull last 7 days of trades
        trades = await self.fetch_recent_trades(
            since_minutes=60 * 24 * 7,
            user=address
        )
        self._debug(f"DEBUG: trader_stats {address[:6]}... recent_trades={len(trades)}")
        trader_trades = [
            t for t in trades
            if t.get("user", "").lower() == address.lower()
        ]

        trade_count = len(trader_trades)

        if trade_count == 0:
            stats = {
                "address": address,
                "total_volume": 0,
                "trade_count": 0,
                "avg_bet": 0,
                "credibility": 0,
                "last_updated": datetime.now()
            }
            self.trader_stats_cache[address] = stats
            return stats

        total_volume = sum(t.get("amount", 0) for t in trader_trades)
        avg_bet = total_volume / trade_count if trade_count > 0 else 0

        # Credibility score formula (tweakable)
        credibility_score = (
            (trade_count * 0.25) +           # experience
            (total_volume / 50000) +         # bankroll
            min(avg_bet / 2000, 5)           # bet confidence
        )

        # Closed positions stats (for win rate)
        closed = await self.fetch_closed_positions(address, since_days=self.settings.SMART_WINDOW_DAYS)
        closed_count = len(closed)
        wins = 0
        total_bought = 0.0
        total_pnl = 0.0
        for p in closed:
            pnl = float(p.get("realizedPnl", 0) or 0)
            bought = float(p.get("totalBought", 0) or 0)
            total_bought += bought
            total_pnl += pnl
            if pnl > 0:
                wins += 1

        win_rate = wins / closed_count if closed_count > 0 else 0
        avg_position = (total_bought / closed_count) if closed_count > 0 else 0

        stats = {
            "address": address,
            "total_volume": total_volume,
            "trade_count": trade_count,
            "avg_bet": avg_bet,
            "credibility": round(credibility_score, 2),
            "closed_positions": closed_count,
            "win_rate": round(win_rate, 3),
            "avg_position": avg_position,
            "realized_pnl": total_pnl,
            "last_updated": datetime.now()
        }

        self.trader_stats_cache[address] = stats

        return stats



    async def get_market_volume_history(self, market_id: str, hours: int = 24) -> List[float]:
        """Get volume history for a market"""
        if market_id not in self.volume_history:
            self.volume_history[market_id] = []

        # Fetch recent trades and calculate hourly volumes
        trades = await self.fetch_recent_trades(market_id=market_id, since_minutes=hours * 60)

        # Group by hour
        hourly_volumes = {}
        for trade in trades:
            hour_key = trade["timestamp"].replace(minute=0, second=0, microsecond=0)
            if hour_key not in hourly_volumes:
                hourly_volumes[hour_key] = 0
            hourly_volumes[hour_key] += trade.get("amount", 0)

        # Update cache
        existing_hours = {ts for ts, _ in self.volume_history[market_id]}
        for hour, volume in hourly_volumes.items():
            if hour not in existing_hours:
                self.volume_history[market_id].append((hour, volume))
                existing_hours.add(hour)


        # Keep only last 24 hours
        cutoff = utc_now() - timedelta(hours=hours)
        self.volume_history[market_id] = [
            (ts, vol) for ts, vol in self.volume_history[market_id]
            if ts >= cutoff
        ]

        return [vol for _, vol in self.volume_history[market_id]]
