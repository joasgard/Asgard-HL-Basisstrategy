"""
Hyperliquid Funding Rate Oracle.

Provides funding rate data and predictions for Hyperliquid perpetuals.
Funding on Hyperliquid:
- Paid every 1 hour
- Rate = premium + clamp(interest_rate, -0.0005%, 0.0005%)
- Premium based on mark vs oracle price deviation

The API returns hourly rates in both metaAndAssetCtxs and fundingHistory.
Annualization: hourly_rate * 24 * 365.

Strategy Entry Criteria (from spec 4.1, 4.2):
- Current funding < 0 (shorts paid)
- Predicted next funding < 0 (shorts will be paid)
- Total APY > 0 after all costs
- Funding volatility < 50% (1-week lookback)
"""
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from shared.utils.logger import get_logger

from .client import HyperliquidClient

logger = get_logger(__name__)

# Annualization factor: 24 hours/day * 365 days/year
ANNUALIZE_FACTOR = 24 * 365


@dataclass
class FundingRate:
    """Funding rate data for a specific time period."""
    coin: str
    funding_rate: float  # Hourly rate (e.g., -0.00001 = -0.001%)
    timestamp_ms: int
    annualized_rate: float  # Annualized rate (funding_rate * 24 * 365)

    @property
    def rate_8hr(self) -> float:
        """8-hour equivalent rate (hourly * 8)."""
        return self.funding_rate * 8

    @property
    def timestamp(self) -> datetime:
        """Convert milliseconds timestamp to datetime."""
        return datetime.fromtimestamp(self.timestamp_ms / 1000)


@dataclass
class FundingPrediction:
    """Prediction for next funding rate."""
    coin: str
    predicted_rate: float
    confidence: str  # "high", "medium", "low" based on time until funding
    premium: float
    interest_rate: float


class HyperliquidFundingOracle:
    """
    Oracle for Hyperliquid funding rates.

    Features:
    - Fetch current funding rates for all perpetuals
    - Get historical funding data
    - Predict next funding rate
    - Calculate funding volatility

    Usage:
        async with HyperliquidFundingOracle() as oracle:
            rates = await oracle.get_current_funding_rates()
            prediction = await oracle.predict_next_funding("SOL")
            volatility = await oracle.calculate_funding_volatility("SOL")
    """

    # Volatility calculation window (1 week in hours)
    VOLATILITY_LOOKBACK_HOURS = 168

    # Maximum acceptable volatility (50%)
    MAX_VOLATILITY = 0.50

    def __init__(self, client: Optional[HyperliquidClient] = None):
        self.client = client or HyperliquidClient()
        self._cache: Dict[str, List[FundingRate]] = {}

    async def __aenter__(self) -> "HyperliquidFundingOracle":
        if not self.client._session or self.client._session.closed:
            await self.client._init_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.client.close()

    async def get_current_funding_rates(self) -> Dict[str, FundingRate]:
        """
        Get current funding rates for all perpetuals.

        Returns:
            Dict mapping coin symbols to FundingRate objects.
            The funding_rate field is the hourly rate from the API.

        Example:
            {"SOL": FundingRate(coin="SOL", funding_rate=-0.00001, ...)}
        """
        try:
            response = await self.client.get_meta_and_asset_contexts()

            # Response is a 2-element list: [meta, assetCtxs]
            if isinstance(response, list) and len(response) == 2:
                meta, asset_ctxs = response
            elif isinstance(response, dict):
                meta = response.get("meta", {})
                asset_ctxs = response.get("assetCtxs", [])
            else:
                raise ValueError(f"Unexpected response format: {type(response)}")

            funding_rates = {}
            universe = meta.get("universe", [])

            for i, asset_info in enumerate(universe):
                if i >= len(asset_ctxs):
                    break

                coin = asset_info.get("name")
                if not coin:
                    continue

                ctx = asset_ctxs[i]

                # funding field is the hourly rate (string)
                funding_rate = float(ctx.get("funding", 0))
                timestamp_ms = int(time.time() * 1000)

                # Annualize from hourly
                annualized = funding_rate * ANNUALIZE_FACTOR

                funding_rates[coin] = FundingRate(
                    coin=coin,
                    funding_rate=funding_rate,
                    timestamp_ms=timestamp_ms,
                    annualized_rate=annualized,
                )

            logger.debug(f"Fetched funding rates for {len(funding_rates)} coins")
            return funding_rates

        except Exception as e:
            logger.error(f"Failed to fetch funding rates: {e}")
            raise

    def _parse_meta_and_ctxs(self, response) -> Tuple[dict, list]:
        """Parse metaAndAssetCtxs response into (meta, asset_ctxs)."""
        if isinstance(response, list) and len(response) == 2:
            return response[0], response[1]
        elif isinstance(response, dict):
            return response.get("meta", {}), response.get("assetCtxs", [])
        raise ValueError(f"Unexpected metaAndAssetCtxs format: {type(response)}")

    def _find_coin_ctx(self, meta: dict, asset_ctxs: list, coin: str) -> Optional[dict]:
        """Find asset context for a coin by looking up its index in the universe."""
        universe = meta.get("universe", [])
        for i, asset_info in enumerate(universe):
            if asset_info.get("name") == coin and i < len(asset_ctxs):
                return asset_ctxs[i]
        return None

    async def get_funding_history(
        self,
        coin: str,
        hours: int = 168,
    ) -> List[FundingRate]:
        """
        Get historical funding rates for a coin.

        Args:
            coin: Coin symbol (e.g., "SOL")
            hours: Number of hours of history to fetch

        Returns:
            List of FundingRate objects (hourly entries)
        """
        cache_key = f"{coin}_{hours}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            end_time = int(time.time() * 1000)
            start_time = end_time - (hours * 60 * 60 * 1000)

            history = await self.client.get_funding_history(coin, start_time, end_time)

            funding_rates = []
            for entry in history:
                # fundingHistory returns hourly rates (entries spaced 1 hour apart)
                rate = float(entry.get("fundingRate", 0))
                funding_rates.append(FundingRate(
                    coin=coin,
                    funding_rate=rate,
                    timestamp_ms=entry.get("time", 0),
                    annualized_rate=rate * ANNUALIZE_FACTOR,
                ))

            funding_rates.sort(key=lambda x: x.timestamp_ms)

            self._cache[cache_key] = funding_rates

            logger.debug(f"Fetched {len(funding_rates)} funding history entries for {coin}")
            return funding_rates

        except Exception as e:
            logger.error(f"Failed to fetch funding history for {coin}: {e}")
            raise

    def _calculate_premium(
        self,
        mark_price: float,
        index_price: float,
    ) -> float:
        """
        Calculate premium component of funding rate.

        premium = (mark_price - index_price) / index_price
        """
        if index_price == 0:
            return 0.0
        return (mark_price - index_price) / index_price

    async def predict_next_funding(self, coin: str) -> FundingPrediction:
        """
        Predict the next funding rate for a coin.

        Uses current mark/oracle price spread as an approximation
        for the premium component.

        Args:
            coin: Coin symbol (e.g., "SOL")

        Returns:
            FundingPrediction with predicted rate and components
        """
        try:
            response = await self.client.get_meta_and_asset_contexts()
            meta, asset_ctxs = self._parse_meta_and_ctxs(response)

            ctx = self._find_coin_ctx(meta, asset_ctxs, coin)
            if not ctx:
                raise ValueError(f"Coin {coin} not found in asset contexts")

            mark_price = float(ctx.get("markPx", 0))
            index_price = float(ctx.get("oraclePx", mark_price))

            # Current premium (instant, not 1h TWAP — approximation)
            premium = self._calculate_premium(mark_price, index_price)

            # Interest rate component (fixed, clamped)
            interest_rate = max(-0.0005, min(0.0005, 0.0001))

            # Predicted hourly funding rate
            predicted_rate = premium + interest_rate

            # Confidence based on premium field from API (already a TWAP)
            api_premium = float(ctx.get("premium", 0))
            # If API premium and our calculation agree on sign, higher confidence
            if (api_premium < 0) == (premium < 0):
                confidence = "high" if abs(premium) > 0.0005 else "medium"
            else:
                confidence = "low"

            return FundingPrediction(
                coin=coin,
                predicted_rate=predicted_rate,
                confidence=confidence,
                premium=premium,
                interest_rate=interest_rate,
            )

        except Exception as e:
            logger.error(f"Failed to predict funding for {coin}: {e}")
            raise

    async def calculate_funding_volatility(
        self,
        coin: str,
        hours: int = 168,
    ) -> float:
        """
        Calculate funding rate volatility over a period.

        Volatility = coefficient of variation = std_dev / mean_abs_value

        Args:
            coin: Coin symbol
            hours: Lookback period in hours

        Returns:
            Volatility as a fraction (e.g., 0.5 = 50%)
        """
        try:
            history = await self.get_funding_history(coin, hours)

            if len(history) < 2:
                logger.warning(f"Insufficient funding history for {coin}")
                return 0.0

            rates = [r.funding_rate for r in history]

            mean_abs = sum(abs(r) for r in rates) / len(rates)
            if mean_abs == 0:
                return 0.0

            mean = sum(rates) / len(rates)
            variance = sum((r - mean) ** 2 for r in rates) / len(rates)
            std_dev = variance ** 0.5

            volatility = std_dev / mean_abs
            logger.debug(f"Funding volatility for {coin}: {volatility:.2%}")
            return volatility

        except Exception as e:
            logger.error(f"Failed to calculate funding volatility for {coin}: {e}")
            raise

    async def check_entry_criteria(
        self,
        coin: str,
    ) -> Tuple[bool, Dict[str, any]]:
        """
        Check if funding conditions meet entry criteria.

        Criteria:
        1. Current funding < 0 (shorts paid)
        2. Predicted next funding < 0 (shorts will be paid)
        3. Funding volatility < 50%
        """
        try:
            current_rates = await self.get_current_funding_rates()
            current = current_rates.get(coin)

            if not current:
                return False, {"error": f"No funding data for {coin}"}

            prediction = await self.predict_next_funding(coin)
            volatility = await self.calculate_funding_volatility(coin)

            criteria = {
                "current_negative": current.funding_rate < 0,
                "predicted_negative": prediction.predicted_rate < 0,
                "volatility_acceptable": volatility < self.MAX_VOLATILITY,
                "current_rate": current.funding_rate,
                "current_annualized": current.annualized_rate,
                "predicted_rate": prediction.predicted_rate,
                "volatility": volatility,
                "confidence": prediction.confidence,
            }

            should_enter = (
                criteria["current_negative"] and
                criteria["predicted_negative"] and
                criteria["volatility_acceptable"]
            )
            criteria["should_enter"] = should_enter

            if should_enter:
                logger.info(
                    f"Entry criteria met for {coin}: "
                    f"current={current.annualized_rate:.2%} ann, "
                    f"predicted={prediction.predicted_rate:.6f}/hr, "
                    f"volatility={volatility:.1%}"
                )

            return should_enter, criteria

        except Exception as e:
            logger.error(f"Failed to check entry criteria for {coin}: {e}")
            return False, {"error": str(e)}

    def clear_cache(self) -> None:
        """Clear cached funding history."""
        self._cache.clear()
        logger.debug("Funding oracle cache cleared")
