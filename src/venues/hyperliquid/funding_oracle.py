"""
Hyperliquid Funding Rate Oracle.

Provides funding rate data and predictions for Hyperliquid perpetuals.
Funding on Hyperliquid:
- Paid every 8 hours (at 00:00, 08:00, 16:00 UTC)
- Rate = premium + clamp(interest_rate, -0.0001, 0.0001)
- Premium = 1-hour TWAP of (mark_price - index_price) / index_price

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

from src.utils.logger import get_logger

from .client import HyperliquidClient

logger = get_logger(__name__)


@dataclass
class FundingRate:
    """Funding rate data for a specific time period."""
    coin: str
    funding_rate: float  # 8-hour rate (e.g., -0.0001 = -0.01%)
    timestamp_ms: int
    annualized_rate: float  # Annualized rate (funding_rate * 3 * 365)
    
    @property
    def hourly_rate(self) -> float:
        """Hourly funding rate (8hr / 8)."""
        return self.funding_rate / 8
    
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
    - Fetch current funding rates
    - Get historical funding data
    - Predict next funding rate
    - Calculate funding volatility
    
    Usage:
        async with HyperliquidFundingOracle() as oracle:
            # Get current funding
            rates = await oracle.get_current_funding_rates()
            
            # Predict next funding
            prediction = await oracle.predict_next_funding("SOL")
            
            # Calculate volatility
            volatility = await oracle.calculate_funding_volatility("SOL")
    """
    
    # Funding interval in milliseconds (8 hours)
    FUNDING_INTERVAL_MS = 8 * 60 * 60 * 1000
    
    # Volatility calculation window (1 week in hours)
    VOLATILITY_LOOKBACK_HOURS = 168
    
    # Maximum acceptable volatility (50%)
    MAX_VOLATILITY = 0.50
    
    def __init__(self, client: Optional[HyperliquidClient] = None):
        """
        Initialize funding oracle.
        
        Args:
            client: HyperliquidClient instance. If None, creates new one.
        """
        self.client = client or HyperliquidClient()
        self._cache: Dict[str, List[FundingRate]] = {}
    
    async def __aenter__(self) -> "HyperliquidFundingOracle":
        """Async context manager entry."""
        if not self.client._session or self.client._session.closed:
            await self.client._init_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.client.close()
    
    async def get_current_funding_rates(self) -> Dict[str, FundingRate]:
        """
        Get current funding rates for all perpetuals.
        
        Returns:
            Dict mapping coin symbols to FundingRate objects
            
        Example:
            {"SOL": FundingRate(coin="SOL", funding_rate=-0.0001, ...)}
        """
        try:
            response = await self.client.get_meta_and_asset_contexts()
            
            # Response is a list: [meta, asset_ctxs]
            if isinstance(response, list) and len(response) == 2:
                meta, asset_ctxs = response
            elif isinstance(response, dict):
                # Fallback for older API format
                meta = response.get("meta", {})
                asset_ctxs = response.get("assetCtxs", [])
            else:
                raise ValueError(f"Unexpected response format: {type(response)}")
            
            funding_rates = {}
            universe = meta.get("universe", [])
            
            # Zip universe (coin names) with asset contexts (funding data)
            for i, asset_info in enumerate(universe):
                if i >= len(asset_ctxs):
                    break
                
                coin = asset_info.get("name")
                if not coin:
                    continue
                
                ctx = asset_ctxs[i]
                
                # Funding rate from context (this is the HOURLY rate)
                funding_rate = float(ctx.get("funding", 0))
                
                # Current timestamp
                timestamp_ms = int(time.time() * 1000)
                
                # Annualize: hourly rate * 24 hours * 365 days
                # Hyperliquid UI shows annualized from hourly rate
                annualized = funding_rate * 24 * 365
                
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
    
    async def get_funding_history(
        self,
        coin: str,
        hours: int = 168,  # Default 1 week
    ) -> List[FundingRate]:
        """
        Get historical funding rates for a coin.
        
        Args:
            coin: Coin symbol (e.g., "SOL")
            hours: Number of hours of history to fetch
            
        Returns:
            List of FundingRate objects
        """
        cache_key = f"{coin}_{hours}"
        
        # Check cache
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            end_time = int(time.time() * 1000)
            start_time = end_time - (hours * 60 * 60 * 1000)
            
            history = await self.client.get_funding_history(coin, start_time, end_time)
            
            funding_rates = []
            for entry in history:
                rate = FundingRate(
                    coin=coin,
                    funding_rate=float(entry.get("fundingRate", 0)),
                    timestamp_ms=entry.get("time", 0),
                    annualized_rate=float(entry.get("fundingRate", 0)) * 3 * 365,
                )
                funding_rates.append(rate)
            
            # Sort by timestamp (oldest first)
            funding_rates.sort(key=lambda x: x.timestamp_ms)
            
            # Cache results
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
        
        Formula from spec:
        premium = (mark_price - index_price) / index_price
        
        Args:
            mark_price: Current mark price
            index_price: Current index/oracle price
            
        Returns:
            Premium as a fraction (e.g., 0.001 = 0.1%)
        """
        if index_price == 0:
            return 0.0
        return (mark_price - index_price) / index_price
    
    def _calculate_interest_rate(self) -> float:
        """
        Get interest rate component.
        
        Hyperliquid uses a fixed 0.01% (0.0001) interest rate,
        clamped between -0.0001 and 0.0001.
        
        Returns:
            Interest rate as a fraction
        """
        # Fixed rate of 0.01% per 8 hours
        return 0.0001
    
    async def predict_next_funding(self, coin: str) -> FundingPrediction:
        """
        Predict the next funding rate for a coin.
        
        Formula from spec 4.2:
        funding = premium + clamp(interest_rate, -0.0001, 0.0001)
        premium = 1-hour TWAP of (mark_price - index_price) / index_price
        
        Args:
            coin: Coin symbol (e.g., "SOL")
            
        Returns:
            FundingPrediction with predicted rate and components
        """
        try:
            # Get current asset context
            response = await self.client.get_meta_and_asset_contexts()
            
            asset_ctxs = response.get("assetCtxs", [])
            ctx = next((c for c in asset_ctxs if c.get("coin") == coin), None)
            
            if not ctx:
                raise ValueError(f"Coin {coin} not found in asset contexts")
            
            # Get mark and index prices
            mark_price = float(ctx.get("markPx", 0))
            index_price = float(ctx.get("oraclePx", mark_price))  # Fallback to mark
            
            # Calculate premium (current instant, not 1h TWAP - approximation)
            premium = self._calculate_premium(mark_price, index_price)
            
            # Interest rate component
            interest_rate = self._calculate_interest_rate()
            
            # Clamp interest rate
            clamped_interest = max(-0.0001, min(0.0001, interest_rate))
            
            # Predict funding rate
            predicted_rate = premium + clamped_interest
            
            # Calculate confidence based on time until next funding
            now = datetime.utcnow()
            # Funding times: 00:00, 08:00, 16:00 UTC
            funding_hours = [0, 8, 16]
            current_hour = now.hour
            
            # Find next funding hour
            next_funding_hour = None
            for fh in funding_hours:
                if fh > current_hour:
                    next_funding_hour = fh
                    break
            if next_funding_hour is None:
                next_funding_hour = 0  # Next day
            
            hours_until_funding = (next_funding_hour - current_hour) % 24
            
            # Confidence based on time until funding
            if hours_until_funding <= 1:
                confidence = "high"
            elif hours_until_funding <= 4:
                confidence = "medium"
            else:
                confidence = "low"
            
            return FundingPrediction(
                coin=coin,
                predicted_rate=predicted_rate,
                confidence=confidence,
                premium=premium,
                interest_rate=clamped_interest,
            )
            
        except Exception as e:
            logger.error(f"Failed to predict funding for {coin}: {e}")
            raise
    
    async def calculate_funding_volatility(
        self,
        coin: str,
        hours: int = 168,  # Default 1 week
    ) -> float:
        """
        Calculate funding rate volatility over a period.
        
        Volatility is calculated as the coefficient of variation (CV):
        CV = standard_deviation / mean_absolute_value
        
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
            
            # Extract rates
            rates = [r.funding_rate for r in history]
            
            # Calculate mean
            mean_rate = sum(abs(r) for r in rates) / len(rates)
            
            if mean_rate == 0:
                return 0.0
            
            # Calculate standard deviation
            variance = sum((r - sum(rates)/len(rates)) ** 2 for r in rates) / len(rates)
            std_dev = variance ** 0.5
            
            # Coefficient of variation
            volatility = std_dev / mean_rate if mean_rate != 0 else 0.0
            
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
        
        Entry criteria from spec:
        1. Current funding < 0 (shorts paid)
        2. Predicted next funding < 0 (shorts will be paid)
        3. Funding volatility < 50%
        
        Args:
            coin: Coin symbol
            
        Returns:
            Tuple of (should_enter, details_dict)
        """
        try:
            # Get current funding
            current_rates = await self.get_current_funding_rates()
            current = current_rates.get(coin)
            
            if not current:
                return False, {"error": f"No funding data for {coin}"}
            
            # Predict next funding
            prediction = await self.predict_next_funding(coin)
            
            # Calculate volatility
            volatility = await self.calculate_funding_volatility(coin)
            
            # Check criteria
            criteria = {
                "current_negative": current.funding_rate < 0,
                "predicted_negative": prediction.predicted_rate < 0,
                "volatility_acceptable": volatility < self.MAX_VOLATILITY,
                "current_rate": current.funding_rate,
                "predicted_rate": prediction.predicted_rate,
                "volatility": volatility,
                "confidence": prediction.confidence,
            }
            
            # All criteria must be met
            should_enter = (
                criteria["current_negative"] and
                criteria["predicted_negative"] and
                criteria["volatility_acceptable"]
            )
            
            criteria["should_enter"] = should_enter
            
            if should_enter:
                logger.info(
                    f"Entry criteria met for {coin}: "
                    f"current={current.funding_rate:.4%}, "
                    f"predicted={prediction.predicted_rate:.4%}, "
                    f"volatility={volatility:.1%}"
                )
            else:
                logger.debug(
                    f"Entry criteria not met for {coin}: {criteria}"
                )
            
            return should_enter, criteria
            
        except Exception as e:
            logger.error(f"Failed to check entry criteria for {coin}: {e}")
            return False, {"error": str(e)}
    
    def clear_cache(self) -> None:
        """Clear cached funding history."""
        self._cache.clear()
        logger.debug("Funding oracle cache cleared")
