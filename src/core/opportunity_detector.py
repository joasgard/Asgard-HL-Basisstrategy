"""
Opportunity Detector for Delta Neutral Funding Rate Arbitrage.

This module provides the core strategy logic for detecting funding rate arbitrage
opportunities between:
- Long spot/margin positions on Asgard Finance (Solana)
- Short perpetual positions on Hyperliquid (Arbitrum)

Key Formula:
    Total APY = |funding_rate| + net_carry_apy
    
Net Carry (on deployed capital):
    Net_Carry = (Leverage × Lending) - ((Leverage - 1) × Borrowing)

Entry Criteria:
1. Current funding rate < 0 (shorts paid)
2. Predicted next funding < 0 (shorts will be paid)
3. Total expected APY > 0 after all costs
4. Funding volatility < 50% (based on 1-week lookback)
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Tuple
from uuid import uuid4

from src.config.assets import Asset, get_mint, get_asset_metadata
from src.config.assets import AssetMetadata
from src.models.common import Protocol
from src.models.funding import FundingRate, AsgardRates
from src.models.opportunity import ArbitrageOpportunity, OpportunityScore
from src.utils.logger import get_logger
from src.venues.asgard.market_data import AsgardMarketData, NetCarryResult
from src.venues.hyperliquid.funding_oracle import HyperliquidFundingOracle, FundingPrediction

logger = get_logger(__name__)


class OpportunityDetector:
    """
    Detects funding rate arbitrage opportunities across multiple assets.
    
    Scans both Asgard and Hyperliquid to find profitable delta-neutral
    positions that earn funding payments while maintaining market-neutral exposure.
    
    Usage:
        async with OpportunityDetector() as detector:
            opportunities = await detector.scan_opportunities()
            for opp in opportunities:
                if opp.meets_entry_criteria:
                    print(f"Found opportunity: {opp.total_expected_apy:.2%} APY")
    """
    
    # Supported assets
    ALLOWED_ASSETS = [Asset.SOL, Asset.JITOSOL, Asset.JUPSOL, Asset.INF]
    LST_ASSETS = [Asset.JITOSOL, Asset.JUPSOL, Asset.INF]
    
    # Configuration
    FUNDING_LOOKBACK_HOURS = 168  # 1 week
    MIN_FUNDING_HISTORY_HOURS = 24
    MAX_FUNDING_VOLATILITY = Decimal("0.5")  # 50%
    
    # Leverage configuration
    DEFAULT_LEVERAGE = Decimal("3")
    MIN_LEVERAGE = Decimal("2")
    MAX_LEVERAGE = Decimal("4")
    
    # Position sizing
    DEFAULT_DEPLOYED_CAPITAL_USD = Decimal("50000")  # $50k default
    
    def __init__(
        self,
        asgard_market_data: Optional[AsgardMarketData] = None,
        hyperliquid_oracle: Optional[HyperliquidFundingOracle] = None,
        leverage: Decimal = DEFAULT_LEVERAGE,
        deployed_capital_usd: Decimal = DEFAULT_DEPLOYED_CAPITAL_USD,
    ):
        """
        Initialize the opportunity detector.
        
        Args:
            asgard_market_data: AsgardMarketData instance. Creates new if None.
            hyperliquid_oracle: HyperliquidFundingOracle instance. Creates new if None.
            leverage: Position leverage (2-4x, default 3x)
            deployed_capital_usd: Capital to deploy per opportunity
        """
        self.asgard = asgard_market_data
        self.hyperliquid = hyperliquid_oracle
        self.leverage = leverage
        self.deployed_capital_usd = deployed_capital_usd
        
        # Validate leverage
        if not self.MIN_LEVERAGE <= leverage <= self.MAX_LEVERAGE:
            raise ValueError(f"Leverage must be between {self.MIN_LEVERAGE} and {self.MAX_LEVERAGE}")
        
        # Track which clients we own (for cleanup)
        self._own_asgard = asgard_market_data is None
        self._own_hyperliquid = hyperliquid_oracle is None
    
    async def __aenter__(self) -> "OpportunityDetector":
        """Async context manager entry."""
        if self._own_asgard and self.asgard is None:
            self.asgard = AsgardMarketData()
        if self._own_hyperliquid and self.hyperliquid is None:
            self.hyperliquid = HyperliquidFundingOracle()
        
        # Initialize sessions
        if self.asgard and self.asgard.client._session is None:
            await self.asgard.client._init_session()
        if self.hyperliquid and self.hyperliquid.client._session is None:
            await self.hyperliquid.client._init_session()
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        if self._own_asgard and self.asgard:
            await self.asgard.close()
        if self._own_hyperliquid and self.hyperliquid:
            await self.hyperliquid.client.close()
    
    async def scan_opportunities(
        self,
        assets: Optional[List[Asset]] = None,
    ) -> List[ArbitrageOpportunity]:
        """
        Scan for arbitrage opportunities across supported assets.
        
        For each asset:
        1. Get best protocol from Asgard with lending/borrowing rates
        2. Get current and predicted funding rates from Hyperliquid
        3. Calculate total APY: |funding| + net_carry
        4. Apply filters (funding < 0, predicted < 0, volatility < 50%)
        5. Create ArbitrageOpportunity if all criteria met
        
        Args:
            assets: List of assets to scan. Defaults to all supported assets.
            
        Returns:
            List of ArbitrageOpportunity objects, sorted by total APY (descending)
        """
        assets = assets or self.ALLOWED_ASSETS
        opportunities: List[ArbitrageOpportunity] = []
        
        # Get current funding rates for all coins (single API call)
        current_funding_rates = await self.hyperliquid.get_current_funding_rates()
        
        for asset in assets:
            try:
                # Convert Hyperliquid FundingRate to model FundingRate
                hl_funding = current_funding_rates.get("SOL")  # Always SOL-PERP
                if hl_funding:
                    from src.models.funding import FundingRate as ModelFundingRate
                    model_funding = ModelFundingRate(
                        timestamp=datetime.utcnow(),
                        coin="SOL",
                        rate_8hr=Decimal(str(hl_funding.funding_rate)),
                    )
                else:
                    model_funding = None
                
                opportunity = await self._analyze_asset(asset, model_funding)
                if opportunity:
                    opportunities.append(opportunity)
            except Exception as e:
                logger.warning(f"Failed to analyze {asset.value}: {e}")
                continue
        
        # Sort by total APY (descending)
        opportunities.sort(key=lambda x: x.total_expected_apy, reverse=True)
        
        logger.info(f"Found {len(opportunities)} opportunities across {len(assets)} assets")
        return opportunities
    
    async def _analyze_asset(
        self,
        asset: Asset,
        current_funding: Optional[FundingRate],
    ) -> Optional[ArbitrageOpportunity]:
        """
        Analyze a single asset for arbitrage opportunity.
        
        Args:
            asset: Asset to analyze
            current_funding: Current SOL-PERP funding rate
            
        Returns:
            ArbitrageOpportunity if criteria met, None otherwise
        """
        # Step 1: Check if current funding is negative (shorts paid)
        if current_funding is None:
            logger.debug(f"No funding data for SOL-PERP")
            return None
        
        if current_funding.rate_8hr >= 0:
            logger.debug(f"Funding not negative: {current_funding.rate_8hr:.4%}")
            return None
        
        # Step 2: Get best protocol from Asgard
        position_size = self.deployed_capital_usd * self.leverage
        best_protocol = await self.asgard.select_best_protocol(
            asset=asset,
            size_usd=float(position_size),
            leverage=float(self.leverage),
        )
        
        if best_protocol is None:
            logger.debug(f"No suitable protocol found for {asset.value}")
            return None
        
        # Step 3: Predict next funding rate
        prediction = await self.hyperliquid.predict_next_funding("SOL")
        
        # Check predicted funding is negative
        if prediction.predicted_rate >= 0:
            logger.debug(f"Predicted funding not negative: {prediction.predicted_rate:.4%}")
            return None
        
        # Step 4: Calculate funding volatility
        volatility = await self.hyperliquid.calculate_funding_volatility(
            "SOL", 
            hours=self.FUNDING_LOOKBACK_HOURS
        )
        
        if volatility > float(self.MAX_FUNDING_VOLATILITY):
            logger.debug(f"Funding volatility too high: {volatility:.1%}")
            return None
        
        # Step 5: Calculate opportunity metrics
        return await self._create_opportunity(
            asset=asset,
            protocol_result=best_protocol,
            current_funding=current_funding,
            prediction=prediction,
            volatility=Decimal(str(volatility)),
        )
    
    async def _create_opportunity(
        self,
        asset: Asset,
        protocol_result: NetCarryResult,
        current_funding: FundingRate,
        prediction: FundingPrediction,
        volatility: Decimal,
    ) -> ArbitrageOpportunity:
        """
        Create an ArbitrageOpportunity from analyzed data.
        
        Args:
            asset: Asset being analyzed
            protocol_result: Best protocol selection result
            current_funding: Current SOL-PERP funding rate
            prediction: Predicted next funding rate
            volatility: Funding volatility measure
            
        Returns:
            ArbitrageOpportunity with all calculated fields
        """
        # Calculate position size
        position_size_usd = self.deployed_capital_usd * self.leverage
        
        # Calculate funding APY (absolute value since shorts receive payment)
        funding_apy = abs(Decimal(str(current_funding.rate_annual)))
        
        # Calculate net carry APY from Asgard
        net_carry_apy = Decimal(str(protocol_result.net_carry_apy))
        
        # Add LST staking yield for LST assets
        lst_staking_apy = Decimal("0")
        asset_metadata = get_asset_metadata(asset)
        if asset_metadata.is_lst:
            lst_staking_apy = Decimal(str(asset_metadata.staking_apy))
        
        # Create opportunity score
        score = OpportunityScore(
            funding_apy=funding_apy,
            net_carry_apy=net_carry_apy,
            lst_staking_apy=lst_staking_apy,
        )
        
        # Create AsgardRates model
        asgard_rates = AsgardRates(
            protocol_id=protocol_result.protocol.value,
            token_a_mint=get_mint(asset),
            token_b_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
            token_a_lending_apy=Decimal(str(protocol_result.lending_rate)),
            token_b_borrowing_apy=Decimal(str(protocol_result.borrowing_rate)),
            token_b_max_borrow_capacity=Decimal("0"),  # Already checked in select_best_protocol
        )
        
        # Create predicted funding rate model
        predicted_funding = FundingRate(
            timestamp=datetime.utcnow(),
            coin="SOL",
            rate_8hr=Decimal(str(prediction.predicted_rate)),
        )
        
        # Create opportunity
        opportunity = ArbitrageOpportunity(
            id=str(uuid4()),
            asset=asset,
            selected_protocol=protocol_result.protocol,
            asgard_rates=asgard_rates,
            hyperliquid_coin="SOL",
            current_funding=current_funding,
            predicted_funding=predicted_funding,
            funding_volatility=volatility,
            leverage=self.leverage,
            deployed_capital_usd=self.deployed_capital_usd,
            position_size_usd=position_size_usd,
            score=score,
            price_deviation=Decimal("0"),  # Will be updated by price consensus
            preflight_checks_passed=False,  # Will be set after preflight
        )
        
        logger.debug(
            f"Created opportunity for {asset.value}: "
            f"APY={opportunity.total_expected_apy:.2%}, "
            f"funding={funding_apy:.2%}, "
            f"net_carry={net_carry_apy:.2%}"
        )
        
        return opportunity
    
    async def calculate_total_apy(
        self,
        asset: Asset,
        protocol: Protocol,
        funding_rate: Decimal,
    ) -> Tuple[Decimal, Decimal, Decimal]:
        """
        Calculate total expected APY breakdown for an asset/protocol combination.
        
        Args:
            asset: Asset to calculate for
            protocol: Protocol to use
            funding_rate: Current funding rate (annual)
            
        Returns:
            Tuple of (funding_apy, net_carry_apy, lst_staking_apy)
        """
        # Get net carry from Asgard
        token_mint = get_mint(asset)
        net_carry_result = await self.asgard.calculate_net_carry_apy(
            protocol=protocol,
            token_a_mint=token_mint,
            leverage=float(self.leverage),
        )
        
        if net_carry_result is None:
            return Decimal("0"), Decimal("0"), Decimal("0")
        
        # Calculate components
        funding_apy = abs(funding_rate)  # Shorts receive |funding|
        net_carry_apy = Decimal(str(net_carry_result.net_carry_apy))
        
        # Add LST staking yield
        asset_metadata = get_asset_metadata(asset)
        lst_staking_apy = Decimal(str(asset_metadata.staking_apy)) if asset_metadata.is_lst else Decimal("0")
        
        return funding_apy, net_carry_apy, lst_staking_apy
    
    def filter_opportunities(
        self,
        opportunities: List[ArbitrageOpportunity],
        min_total_apy: Decimal = Decimal("0"),
        max_volatility: Optional[Decimal] = None,
        require_predicted_negative: bool = True,
    ) -> List[ArbitrageOpportunity]:
        """
        Filter opportunities based on criteria.
        
        Args:
            opportunities: List of opportunities to filter
            min_total_apy: Minimum total APY (default 0 for any profit)
            max_volatility: Maximum funding volatility (default MAX_FUNDING_VOLATILITY)
            require_predicted_negative: Require predicted funding < 0
            
        Returns:
            Filtered list of opportunities
        """
        max_volatility = max_volatility or self.MAX_FUNDING_VOLATILITY
        filtered: List[ArbitrageOpportunity] = []
        
        for opp in opportunities:
            # Check minimum APY
            if opp.total_expected_apy < min_total_apy:
                continue
            
            # Check volatility
            if opp.funding_volatility > max_volatility:
                continue
            
            # Check predicted funding is negative
            if require_predicted_negative and opp.predicted_funding:
                if not opp.predicted_funding.is_negative:
                    continue
            
            filtered.append(opp)
        
        return filtered
    
    def get_best_opportunity(
        self,
        opportunities: List[ArbitrageOpportunity],
    ) -> Optional[ArbitrageOpportunity]:
        """
        Get the single best opportunity from a list.
        
        Selects based on:
        1. Highest total APY
        2. If tie: prefer lower volatility
        3. If still tie: prefer native SOL over LSTs
        
        Args:
            opportunities: List of opportunities
            
        Returns:
            Best opportunity or None if list is empty
        """
        if not opportunities:
            return None
        
        # Sort by: APY (desc), volatility (asc), is_lst (asc)
        sorted_opps = sorted(
            opportunities,
            key=lambda x: (
                x.total_expected_apy,
                -x.funding_volatility,  # Negative for ascending
                0 if x.asset == Asset.SOL else 1,  # SOL preferred
            ),
            reverse=True,
        )
        
        return sorted_opps[0]
    
    async def check_entry_criteria(
        self,
        opportunity: ArbitrageOpportunity,
    ) -> Tuple[bool, dict]:
        """
        Check if an opportunity meets all entry criteria.
        
        Entry Criteria:
        1. Current funding < 0 (shorts paid)
        2. Predicted funding < 0 (shorts will be paid)
        3. Total APY > 0
        4. Funding volatility < 50%
        5. Price deviation < 0.5% (if available)
        6. Protocol has sufficient capacity
        
        Args:
            opportunity: Opportunity to check
            
        Returns:
            Tuple of (should_enter, details_dict)
        """
        criteria = {
            "current_funding_negative": opportunity.current_funding.is_negative,
            "predicted_funding_negative": (
                opportunity.predicted_funding.is_negative 
                if opportunity.predicted_funding else False
            ),
            "total_apy_positive": opportunity.score.is_profitable,
            "volatility_acceptable": opportunity.funding_volatility < self.MAX_FUNDING_VOLATILITY,
            "price_deviation_acceptable": opportunity.price_deviation < Decimal("0.005"),
            "preflight_passed": opportunity.preflight_checks_passed,
        }
        
        # All criteria must be True
        should_enter = all(criteria.values())
        criteria["should_enter"] = should_enter
        
        return should_enter, criteria
    
    def clear_cache(self) -> None:
        """Clear cached data from underlying clients."""
        if self.asgard:
            self.asgard.clear_cache()
        if self.hyperliquid:
            self.hyperliquid.clear_cache()
        logger.debug("Opportunity detector cache cleared")
