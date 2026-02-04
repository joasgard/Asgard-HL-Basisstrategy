# Delta Neutral Funding Rate Arbitrage System
## Technical Specification v2.0 - Asgard + Hyperliquid

---

## 1. Executive Summary

This document specifies a **Delta Neutral Funding Rate Arbitrage Bot** that captures yield differentials between:
- **Long Spot/Margin Positions**: Via Asgard Finance API on Solana (aggregating Marginfi, Kamino, Solend, Drift)
- **Short Perpetual Positions**: Via Hyperliquid on Arbitrum

The bot monitors Hyperliquid funding rates and Asgard net borrowing costs, identifies profitable spreads, and executes delta-neutral positions programmatically.

### Primary Strategy: Equal Leverage Delta Neutral

```
┌────────────────────────────────────────────────────────────────┐
│                    ASGARD (Solana)                             │
│  ┌──────────────────────────────────────────────────────┐     │
│  │  LONG Spot Margin Position                           │     │
│  │  • Asset: SOL or SOL LST (jitoSOL, jupSOL, INF)      │     │
│  │  • Collateral: USDC                                  │     │
│  │  • Direction: LONG (0)                               │     │
│  │  • Leverage: 3-4x (configurable, default 3x)         │     │
│  │  • Protocol: Best rate from Marginfi/Kamino/Solend   │     │
│  │  • Exposure: +3-4x SOL (or equivalent LST)           │     │
│  └──────────────────────────────────────────────────────┘     │
└────────────────────────┬───────────────────────────────────────┘
                         │ Delta Neutral (Equal Leverage)
┌────────────────────────▼───────────────────────────────────────┐
│               HYPERLIQUID (Arbitrum)                           │
│  ┌──────────────────────────────────────────────────────┐     │
│  │  SHORT Perpetual Position                            │     │
│  │  • Asset: SOL-PERP (SOLUSD)                          │     │
│  │  • Leverage: 3-4x (must match long side)             │     │
│  │  • Funding: Received hourly (1/8 of 8hr rate)        │     │
│  │  • Exposure: -3-4x SOL                               │     │
│  └──────────────────────────────────────────────────────┘     │
└────────────────────────────────────────────────────────────────┘
```

**Key Principle**: Both legs use **equal leverage (3-4x)** to achieve delta neutrality. Default is 3x for conservative risk profile.

**Supported Long Assets**:
| Asset | Type | Notes |
|-------|------|-------|
| SOL | Native | Standard choice |
| jitoSOL | LST | Jito liquid staking token |
| jupSOL | LST | Jupiter liquid staking token |
| INF | LST | Infinity LST basket |

**Yield Capture**: Hyperliquid funding earned - Asgard net borrowing cost + LST staking yield

**Net Borrowing Cost Formula** (calculated on deployed capital):
```
Position Structure (3x leverage example):
- Deployed Capital: $100
- Total Position: $300 ($100 principal + $200 borrowed)
- Collateral: $300 in SOL/LST earning lending yield
- Debt: $200 in USDC paying borrowing cost

Annual Flows:
- Lending Yield Earned: $300 × tokenALendingApyRate
- Borrowing Cost Paid: $200 × tokenBBorrowingApyRate
- Net Carry: (Lending Yield) - (Borrowing Cost)
- Net APY: Net Carry / Deployed Capital

Example (3x leverage, 5% lend, 8% borrow):
- Lending Yield: $300 × 5% = $15/year
- Borrowing Cost: $200 × 8% = $16/year
- Net Carry: $15 - $16 = -$1/year (cost)
- Net Carry APY: -$1 / $100 = -1%

Example (3x leverage, 6% lend, 5% borrow - POSITIVE CARRY):
- Lending Yield: $300 × 6% = $18/year
- Borrowing Cost: $200 × 5% = $10/year
- Net Carry: $18 - $10 = +$8/year (you get paid!)
- Net Carry APY: +$8 / $100 = +8%
```

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         OFF-CHAIN MONITORING LAYER                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Hyperliquid │  │    Asgard    │  │   Price      │  │   Risk       │     │
│  │Funding Oracle│  │ Borrow Oracle│  │   Consensus  │  │   Monitor    │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
│         └─────────────────┴─────────────────┴─────────────────┘             │
│                               │                                             │
│                    ┌──────────▼──────────┐                                  │
│                    │  Opportunity        │                                  │
│                    │  Detection Engine   │                                  │
│                    └──────────┬──────────┘                                  │
└───────────────────────────────┼─────────────────────────────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │   Execution Router    │
                    │   (Off-chain Logic)   │
                    └───────────┬───────────┘
                                │
        ┌───────────────────────┴───────────────────────┐
        │                                               │
        ▼                                               ▼
┌───────────────┐                            ┌───────────────┐
│   SOLANA      │                            │   ARBITRUM    │
│   (Asgard)    │                            │ (Hyperliquid) │
│               │                            │               │
│  ┌─────────┐  │                            │  ┌─────────┐  │
│  │  LONG   │  │                            │  │  SHORT  │  │
│  │  SPOT   │  │                            │  │  PERP   │  │
│  │  MARGIN │  │                            │  │         │  │
│  └─────────┘  │                            │  └─────────┘  │
└───────────────┘                            └───────────────┘
```

---

## 3. Venue Specifications

### 3.1 Asgard Finance (Long Side)

| Parameter | Value |
|-----------|-------|
| **Chain** | Solana |
| **Type** | Margin Trading Aggregator |
| **Underlying Protocols** | Marginfi (0), Kamino (1), Solend (2), Drift (3) |
| **API Base** | `https://v2-ultra-edge.asgard.finance/margin-trading` |
| **Auth** | X-API-Key header |
| **Transaction Pattern** | Build → Sign → Submit (with persistent state tracking) |
| **Position ID** | positionPDA (Program Derived Address) |
| **Max Leverage** | 4x (strategy default: 3x) |

**Supported Assets** (Token A/USDC pairs):
| Token A | Mint | Type |
|---------|------|------|
| SOL | So11111111111111111111111111111111111111112 | Native |
| jitoSOL | jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v | LST |
| jupSOL | jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v | LST |
| INF | 5oVNBeEEQvYi1cX3ir8Dx5n1P7pdxydbGF2X6TxNxsi | LST |

**Note**: All long assets are SOL or SOL-equivalent (liquid staking tokens). Short leg on Hyperliquid uses SOL-PERP which tracks SOL price.

### 3.2 Hyperliquid (Short Side)

| Parameter | Value |
|-----------|-------|
| **Chain** | Arbitrum (Hyperliquid L1) |
| **Type** | Perpetual DEX |
| **Collateral** | USDC |
| **API Base** | `https://api.hyperliquid.xyz` |
| **Funding Interval** | 8 hours (paid hourly as 1/8 of rate) |
| **Info Endpoint** | `POST /info` |
| **Exchange Endpoint** | `POST /exchange` |
| **Signing** | EIP-712 |
| **Asset** | SOL-PERP (SOLUSD) |
| **Max Leverage** | 4x (strategy default: 3x) |
| **Order Type** | Market orders only |

**Note**: Short leg always uses SOL-PERP regardless of whether long leg uses SOL, jitoSOL, jupSOL, or INF. All SOL LSTs track SOL price with minor drift.

---

## 4. Core Components

### 4.1 Opportunity Detection

```python
class OpportunityDetector:
    """
    Scans Asgard net borrowing costs vs Hyperliquid funding rates.
    Limited to SOL ecosystem: SOL, jitoSOL, jupSOL, INF vs SOL-PERP.
    
    Opportunity Condition:
    1. Current funding_rate indicates shorts are paid (negative rate)
    2. Predicted next funding_rate also indicates shorts are paid
    3. Total expected APY > 0 after all costs
    
    Total APY = |funding_rate| + net_carry_apy
    
    Note: net_carry_apy includes LST staking yield via the Lending_Rate
    when using LST collateral (jitoSOL, jupSOL, INF)
    
    Funding lookback: 1 week minimum for volatility assessment
    """
    
    # Asset universe
    ALLOWED_ASSETS = ["SOL", "jitoSOL", "jupSOL", "INF"]
    LST_ASSETS = ["jitoSOL", "jupSOL", "INF"]
    
    # Funding analysis
    FUNDING_LOOKBACK_HOURS = 168  # 1 week
    MIN_FUNDING_HISTORY_HOURS = 24
    MAX_FUNDING_VOLATILITY = 0.5
    
    async def scan_opportunities(self) -> List[ArbitrageOpportunity]:
        """
        1. Query Asgard /markets for SOL/USDC and LST/USDC pairs
        2. Query Hyperliquid SOL-PERP current funding + predicted next funding
        3. Calculate total expected APY including:
           - Hyperliquid funding yield (annualized)
           - Asgard net carry APY (lending yield - borrowing cost)
           - LST staking yield if applicable
        4. Filter: total APY > 0
        5. Return sorted by total yield
        """
        pass
```

#### Scoring Formula

```
Inputs (for 3x leverage, $100k deployed capital split 50/50):
- Deployed per leg: $50k
- Position size: $150k ($50k × 3x)
- Borrowed: $100k

Hyperliquid Short Leg:
  Funding_Earned = Position_Size × |funding_rate|
                 = $150k × 25% = $37.5k/year

Asgard Long Leg (Net Carry on Deployed Capital):
  For LST assets (jitoSOL, jupSOL, INF):
    tokenALendingApy = Base_Lending_Rate + LST_Staking_Rate
    
  Lending_Yield = Position_Size × tokenALendingApy
                = $150k × 13% (5% base + 8% staking) = $19.5k/year
  Borrowing_Cost = Borrowed_Amount × tokenBBorrowingApy
                 = $100k × 8% = $8k/year
  Net_Carry = Lending_Yield - Borrowing_Cost
            = $19.5k - $8k = $11.5k/year
  Net_Carry_APY = Net_Carry / Deployed_Capital
                = $11.5k / $50k = 23%

Total_Yield = Funding_Earned + Net_Carry
            = $37.5k + $11.5k = $49k/year

Total_APY = Total_Yield / Total_Deployed_Capital
          = $49k / $100k = 49%

Position Hold Decision:
- If Total_APY > 0: Continue holding
- If Total_APY < 0 AND closing_cost < 5min_bleed: Close position
```

### 4.2 Hyperliquid Funding Rate Oracle

```python
class HyperliquidFundingOracle:
    """
    Fetches funding rates from Hyperliquid API.
    Uses conservative approach: checks both current AND predicted next funding.
    """
    
    API_BASE = "https://api.hyperliquid.xyz"
    
    async def get_current_funding_rates(self) -> Dict[str, FundingRate]:
        """
        Returns current funding rates for all assets.
        Uses metaAndAssetCtxs endpoint.
        """
        pass
    
    async def get_funding_history(self, coin: str, hours: int = 168) -> List[FundingRate]:
        """
        Historical funding for trend analysis.
        Default 1 week lookback for volatility assessment.
        """
        pass
    
    async def predict_next_funding(self, coin: str) -> float:
        """
        Predict next funding rate based on current premium.
        Formula: funding = premium + clamp(interest_rate, -0.0001, 0.0001)
        where premium = 1-hour TWAP of (mark_price - index_price) / index_price
        
        Implementation:
        1. Fetch current mark price and index price from metaAndAssetCtxs
        2. Calculate premium using 1-hour TWAP
        3. Apply interest rate clamp
        4. Return predicted 8-hour funding rate
        
        Conservative entry requires BOTH current AND predicted funding
        to indicate shorts will be paid.
        """
        pass
    
    async def calculate_funding_volatility(self, coin: str, hours: int = 168) -> float:
        """
        Calculate funding rate volatility for opportunity filtering.
        Uses hourly funding rates over lookback period (default 1 week).
        
        Volatility metric: Standard deviation of hourly funding rates.
        Used to filter opportunities during extreme volatility periods.
        """
        pass
```

### 4.3 Asgard Borrowing Rate Oracle

```python
class AsgardBorrowingOracle:
    """
    Fetches lending/borrowing rates from Asgard /markets endpoint.
    Calculates net carry based on deployed capital.
    """
    
    async def get_rates(self, token_a_mint: str) -> Dict[int, AsgardRates]:
        """
        Returns lending and borrowing rates across all 4 protocols.
        Checks tokenBMaxBorrowCapacity before recommending protocol.
        """
        pass
    
    async def calculate_net_carry_apy(self, 
                                       protocol_id: int,
                                       token_a_mint: str,
                                       leverage: float = 3.0) -> float:
        """
        Calculate net carry APY on deployed capital.
        
        Formula:
        Net_Carry = (Leverage × Lending_Rate) - ((Leverage - 1) × Borrowing_Rate)
        
        Example (3x leverage, 5% lend, 8% borrow):
        Net_Carry = (3 × 5%) - (2 × 8%) = 15% - 16% = -1%
        """
        pass
```

### 4.4 Price Consensus

```python
class PriceConsensus:
    """
    Ensures Asgard and Hyperliquid prices are aligned before execution.
    """
    
    MAX_PRICE_DEVIATION = 0.005  # 0.5%
    
    async def check_consensus(self, asset: str) -> ConsensusResult:
        """
        Compare Hyperliquid markPx vs Asgard oracle prices.
        Raises if deviation > 0.5% - prevents bad entries during volatility.
        """
        pass
```

---

## 5. Execution Flow

### 5.0 Pre-Flight Checklist

Before executing any position entry, the following MUST pass:

1. **Wallet Balance Check**: Both Solana and Hyperliquid wallets have sufficient funds
2. **Price Consensus**: Deviation between venues < 0.5%
3. **Funding Validation**: Both current AND predicted next funding indicate shorts paid
4. **Protocol Capacity**: Asgard selected protocol has sufficient borrow capacity
5. **Fee Market Check**: Solana compute unit price below threshold (see 5.1.2)
6. **Opportunity Simulation**: Both legs can be built successfully

### 5.1 Entry Flow

```
1. DETECT OPPORTUNITY
   └─> Get Asgard net borrowing rates for SOL, jitoSOL, jupSOL, INF
   └─> Get Hyperliquid SOL-PERP current + predicted funding rate
   └─> Calculate total expected APY
   └─> Filter: total APY > 0

2. PRE-FLIGHT SIMULATION
   └─> Build Asgard transaction (dry-run)
   └─> Simulate Hyperliquid order
   └─> Record reference prices for both legs
   └─> Verify all checks pass (Section 5.0)

3. EXECUTE ASGARD LONG (3-Step Flow with State Machine)
   
   Step A: Build Transaction
   ├─> POST /create-position
   ├─> Select best protocol (lowest NET borrowing rate)
   ├─> Store state: INTENT_CREATED with unique intent_id
   │
   Step B: Sign Transaction
   ├─> Decode base64 transaction
   ├─> Sign with Solana keypair
   ├─> Store state: TRANSACTION_SIGNED
   │
   Step C: Submit & Confirm
   ├─> POST /submit-create-position-tx
   ├─> Store state: TRANSACTION_SUBMITTED
   ├─> Poll /refresh-positions until confirmed
   ├─> Store state: POSITION_CONFIRMED
   └─> Extract: positionPDA, entry price
   
   Retry Logic (Helius/Triton):
   - If submission fails: Retry immediately (next Solana block ~400ms)
   - If second failure: Abort entry, unwind if other leg active
   - Track transaction status via getSignatureStatuses
   
   Transaction Rebroadcasting (Safety-First Approach):
   - If transaction stuck >15s without confirmation:
     1. Query getSignatureStatuses to check if landed
     2. If landed: Update state and proceed
     3. If not landed: Assume dropped, rebuild with fresh blockhash
     4. Re-sign with same key (new signature, same intent)
     5. Submit new transaction
   - Deduplication: Same intent_id prevents double-position creation
   - Timeout: Maximum 5 minutes for confirmation before marking failed

4. EXECUTE HYPERLIQUID SHORT
   
   Step A: Update Leverage
   ├─> POST /exchange {"action": {"type": "updateLeverage", ...}}
   ├─> Set leverage to match Asgard (3x default)
   │
   Step B: Place Market Short Order (with retry logic)
   ├─> POST /exchange with order action
   ├─> {
   │     "type": "order",
   │     "orders": [{
   │       "coin": "SOL",
   │       "is_buy": false,          // SHORT
   │       "sz": "20.5",             // Size in SOL (match long exposure)
   │       "order_type": {"market": {}}
   │     }]
   │   }
   ├─> Sign with EIP-712
   │
   Step C: Confirm Fill & Price Validation
   ├─> Query /info {"type": "clearinghouseState", "user": "..."}
   ├─> Verify fill price within 0.5% of Asgard entry price
   ├─> If deviation > 0.5%: Check if total spread still profitable
   └─> If not profitable: Trigger immediate unwind
   
   Partial Fill Handling:
   - If Hyperliquid fills partially: Accept partial fill
   - Immediately place additional order for remaining size
   - Track target_size vs actual_size
   - If drift > 0.1% after all retries: Alert and continue monitoring
   
   Retry Logic (Hyperliquid Entry Failure):
   - Max retries: 15 attempts
   - Interval: Every 2 seconds (30 second total window)
   - Stop-loss monitoring: Active during entire retry window
   - Stop-loss trigger: SOL moves >1% against position
   - On stop-loss trigger: Immediate market unwind with 0.1% slippage tolerance
   - On max retries exceeded: Unwind Asgard position

5. POST-EXECUTION VALIDATION
   ├─> Verify Asgard position confirmed
   ├─> Verify Hyperliquid fill confirmed
   ├─> Check price deviation from reference < 0.5%
   ├─> Calculate actual delta exposure
   └─> If delta > 0.5%: Trigger rebalance or unwind

6. STORE POSITION
   ├─> Asgard: protocol, positionPDA, entry prices
   ├─> Hyperliquid: position size, entry price
   ├─> Reference prices for both legs
   ├─> Expected yields, monitoring thresholds
   └─> Start monitoring loops
```

#### 5.1.1 Reference Price Tracking

```python
@dataclass
class PositionReference:
    """Captured at pre-flight simulation for validation."""
    asgard_entry_price: float
    hyperliquid_entry_price: float
    max_acceptable_deviation: float = 0.005  # 0.5%
    
    def check_deviation(self, current_asgard: float, current_hyperliquid: float) -> bool:
        asgard_dev = abs(current_asgard - self.asgard_entry_price) / self.asgard_entry_price
        hyperliquid_dev = abs(current_hyperliquid - self.hyperliquid_entry_price) / self.hyperliquid_entry_price
        return asgard_dev <= self.max_acceptable_deviation and hyperliquid_dev <= self.max_acceptable_deviation
```

#### 5.1.3 Post-Execution Fill Validation

After each leg is executed, the system validates actual fill prices:

```python
class FillValidator:
    """
    Validates filled prices against reference prices and profitability.
    Uses soft stop approach: Check profitability before unwinding on deviation.
    """
    
    MAX_FILL_DEVIATION = 0.005  # 0.5% between Asgard and Hyperliquid fills
    
    async def validate_fills(self, 
                            asgard_fill: float, 
                            hyperliquid_fill: float,
                            expected_spread: float) -> ValidationResult:
        """
        1. Calculate fill deviation: |asgard_fill - hyperliquid_fill| / asgard_fill
        2. If deviation > 0.5%:
           - Calculate actual spread at filled prices
           - If still profitable: Accept position (soft stop)
           - If not profitable: Trigger immediate unwind
        3. If deviation <= 0.5%: Accept position
        """
        pass
```

**Soft Stop Logic**:
- Hard deviation check of 0.5% triggers profitability re-evaluation
- Position only unwound if total expected APY < 0 at actual filled prices
- This prevents closing profitable positions during volatile but viable conditions

#### 5.1.2 Solana Fee Market Monitoring

```python
class SolanaFeeMonitor:
    """
    Monitors compute unit prices for target programs.
    Prevents entry during fee spikes.
    Uses dynamic priority fees based on 75th percentile + 25% premium.
    """
    
    MAX_CUP_MICRO_LAMPORTS = 10_000  # ~0.001 SOL for 200k CU tx
    CHECK_DURATION_SECONDS = 30
    
    # Dynamic fee configuration
    FEE_PERCENTILE = 75  # Base on 75th percentile of recent txs
    FEE_PREMIUM_PCT = 25  # Add 25% premium
    MAX_FEE_SOL = 0.01  # Maximum 0.01 SOL per tx
    MAX_FEE_EMERGENCY_SOL = 0.02  # Maximum 0.02 SOL for stop-loss
    
    async def check_fee_market(self, target_programs: List[str]) -> bool:
        """
        Check median CUP for recent landed transactions on target programs.
        Return False if fees exceed threshold for >30 seconds.
        """
        pass
    
    async def calculate_priority_fee(self, urgency: str = "normal") -> int:
        """
        Calculate priority fee based on fee market.
        - normal: 75th percentile + 25%
        - high: 90th percentile + 50%
        - emergency: 90th percentile + 50%, capped at MAX_FEE_EMERGENCY_SOL
        """
        pass
    
    async def preflight_fee_check(self) -> FeeCheckResult:
        """
        If fees spike: Abort entry, return to monitoring.
        """
        pass
```

### 5.2 Exit Flow

```
EXIT TRIGGERS:
├─> Total APY turns negative (funding + net carry + staking < 0)
├─> Closing cost < expected loss over next 5 minutes
├─> Asgard health_factor approaching threshold (20% away for 20s+)
├─> Hyperliquid margin fraction approaching threshold (20% away for 20s+)
├─> Price deviation > 2% between venues
├─> Manual override
└─> Solana/Hyperliquid outage detected

EXIT FLOW:

1. CLOSE HYPERLIQUID SHORT FIRST
   ├─> Reduces liquidation risk on short side
   ├─> Place market buy order to close short
   ├─> Wait for fill confirmation
   ├─> Retry logic: Up to 5 attempts with exponential backoff
   ├─> If still failing after 60s: Proceed to close Asgard anyway
   └─> Withdraw USDC margin
   
   Note: Maximum acceptable single-leg exposure during exit is 120 seconds.
   If Asgard close fails after Hyperliquid is closed:
   - Retry aggressively with 2x priority fee
   - Alert if still failing after 60s
   - Accept directional short exposure until resolved

2. CLOSE ASGARD LONG (3-Step with State Machine)
   
   Step A: Build Close
   ├─> POST /close-position
   ├─> Store state: CLOSE_INTENT_CREATED
   │
   Step B: Sign
   ├─> Sign with Solana wallet
   ├─> Store state: CLOSE_SIGNED
   │
   Step C: Submit
   ├─> POST /submit-close-position-tx
   ├─> Store state: CLOSE_SUBMITTED
   ├─> Poll until confirmed
   └─> Calculate realized PnL

3. SETTLE & REBALANCE
   ├─> Calculate total return
   ├─> Rebalance wallets if imbalance > 10% (only when no position open)
   ├─> Bridge funds if needed (use highest volume bridge)
   └─> Log performance
```

### 5.3 Monitoring Loop

```python
class PositionMonitor:
    """
    Continuous monitoring of both positions.
    Aligned polling intervals: 30 seconds for both chains.
    """
    
    POLL_INTERVAL_SECONDS = 30
    
    async def monitor_asgard(self, position_pda: str, protocol: int):
        """
        Every 30 seconds:
        - POST /refresh-positions
        - Check health_factor
        - Close if < 20% away from liquidation for 20s+
        """
        pass
    
    async def monitor_hyperliquid(self, wallet: str, coin: str):
        """
        Every 30 seconds:
        - Query clearinghouseState
        - Track funding payments accrued
        - Check margin fraction
        - Close if < 20% away from liquidation for 20s+
        """
        pass
    
    async def check_funding_flip(self):
        """
        Check if total APY has turned negative.
        If negative AND closing_cost < 5min_expected_loss: Exit.
        """
        pass
    
    async def check_lst_peg(self, lst_mint: str):
        """
        Monitor LST-SOL price ratio.
        If premium > 3% or discount > 1%: Alert.
        If premium > 5% or discount > 2%: Emergency close.
        """
        pass
    
    async def check_delta_drift(self):
        """
        Account for LST appreciation (staking rewards accrue in token).
        Rebalance strategy: Wait until accumulated drift cost exceeds rebalance cost.
        
        Formula:
        drift_cost = drift_amount × funding_rate × time_held
        if drift_cost > rebalance_cost (gas + slippage):
            Rebalance by partially closing long position to restore delta neutral
        """
        pass
```

### 5.4 Chain Outage Detection & Handling

```python
class ChainOutageDetector:
    """
    Detects outages on either chain using consecutive failure counting.
    """
    
    MAX_CONSECUTIVE_FAILURES = 3
    FAILURE_WINDOW_SECONDS = 15
    
    async def check_chain_health(self, chain: str) -> ChainStatus:
        """
        Mark chain as OUTAGE if 3 consecutive RPC calls fail within 15s.
        """
        pass
    
    async def handle_outage(self, affected_chain: str):
        """
        If Solana down but Hyperliquid up:
        - Immediately close Hyperliquid position
        - Continue retrying Solana close until confirmed
        
        If Hyperliquid down but Solana up:
        - Immediately close Asgard position
        - Continue retrying Hyperliquid close until confirmed
        """
        pass
```

---

## 6. Asgard Integration Deep Dive

### 6.1 Transaction Flow with State Machine

```
┌────────────────────────────────────────────────────────────────────┐
│  PERSISTENT STATE STORE (SQLite)                                   │
│  - intent_id: UUID for each position attempt                       │
│  - state: Enum of transaction lifecycle                            │
│  - timestamp: For timeout handling                                 │
│  - signature: Transaction signature only (not full tx bytes)       │
│  - metadata: Position params, reference prices, retry count        │
└────────────────────────────────────────────────────────────────────┘

Note: Only signatures and metadata are stored, not full signed transaction
bytes, for security. Recovery requires rebuilding transactions with fresh
blockhashes and re-signing.

State Machine:
IDLE → BUILDING → BUILT → SIGNING → SIGNED → SUBMITTING → SUBMITTED → CONFIRMED
              ↓        ↓          ↓           ↓             ↓
           FAILED   FAILED     FAILED      FAILED        FAILED/timeout

Recovery on Startup:
1. Query state DB for incomplete transactions
2. For each SIGNED but not SUBMITTED:
   - Discard old signature (blockhash likely expired)
   - Rebuild transaction with fresh blockhash
   - Re-sign and submit
3. For SUBMITTED but not CONFIRMED:
   - Poll for confirmation up to 5 minutes
   - Check on-chain via /refresh-positions for position existence
   - If found on-chain: Mark CONFIRMED
   - If not found and signature not found: Rebuild and retry
   - If timeout: Rebuild with fresh blockhash
```

### 6.2 Key Data Fields

From `/refresh-positions`:
```json
{
  "healthFactor": 40.94,
  "booksAndBalances": {
    "balances": [{
      "bank_address": {
        "mint": "So111111...",
        "assetsQt": 45.5,
        "liabsQt": 0
      }
    }, {
      "bank_address": {
        "mint": "EPjF...",
        "assetsQt": 0,
        "liabsQt": 1365.0
      }
    }]
  }
}
```

### 6.3 Protocol Selection

```python
def select_best_protocol(markets: dict, token_a: str, size_usd: float, leverage: float) -> int:
    """
    1. Filter markets by tokenAMint == token_a
    2. For each liquidity source:
       - Check tokenBMaxBorrowCapacity >= size_usd * (leverage - 1) * 1.2
         (20% safety margin on borrow capacity)
       - Calculate net_rate = (leverage × lending) - ((leverage-1) × borrowing)
    3. Return protocol with best (highest) net carry
    4. Tie-breaker order: Marginfi (0) > Kamino (1) > Solend (2) > Drift (3)
    5. If capacity unavailable: Return None (abort entry)
    """
    pass
```

---

## 7. Hyperliquid Integration Deep Dive

### 7.1 API Structure

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/info` | POST | Read-only data (meta, funding, positions) |
| `/exchange` | POST | State-changing actions (orders, leverage) |

### 7.2 Info Endpoints

```python
# Get all asset metadata + current states
{"type": "metaAndAssetCtxs"}
# Returns: [meta, [assetCtxs]]
# assetCtx contains: funding, markPx, openInterest, etc.

# Get user's clearinghouse state
{"type": "clearinghouseState", "user": "0x..."}
# Returns: positions, margin summary, etc.

# Get historical funding
{"type": "fundingHistory", "coin": "SOL", "startTime": timestamp_ms}
```

### 7.3 Exchange Actions

```python
# Update leverage
{
  "action": {
    "type": "updateLeverage",
    "coin": "SOL",
    "leverage": 3,
    "isCross": True
  },
  "nonce": 123456,
  "signature": "0x..."
}

# Place market order
{
  "action": {
    "type": "order",
    "orders": [{
      "coin": "SOL",
      "is_buy": False,
      "sz": "20.5",
      "order_type": {"market": {}}
    }]
  },
  "nonce": 123457,
  "signature": "0x..."
}
```

### 7.4 Funding Rate Calculation

```
Hourly_Funding = funding_8hr_rate / 8

Conservative Entry Check:
1. Current funding_8hr < 0 (shorts paid)
2. Predicted next funding < 0 (shorts will be paid)
3. Both conditions must pass
```

---

## 8. Risk Management

### 8.1 Risk Parameters

```yaml
risk_limits:
  # Position Limits
  max_position_size_usd: 500000
  max_total_exposure_usd: 2000000
  max_positions_per_asset: 1
  
  # Asset Universe
  allowed_long_assets:
    - SOL
    - jitoSOL
    - jupSOL
    - INF
  allowed_short_assets:
    - SOL-PERP
  
  # Leverage Limits
  default_leverage: 3.0
  max_leverage: 4.0
  enforce_equal_leverage: true
  
  # Asgard Risk
  asgard:
    min_health_factor: 0.20
    emergency_health_factor: 0.10
    critical_health_factor: 0.05
    liquidation_proximity_threshold: 0.20  # 20% away for 20s+ = close
    liquidation_proximity_duration: 20
    
  # Hyperliquid Risk
  hyperliquid:
    margin_fraction_threshold: 0.10
    liquidation_proximity_threshold: 0.20
    liquidation_proximity_duration: 20
    
  # Execution Safety
  max_price_deviation: 0.005  # 0.5%
  max_slippage_entry_bps: 50
  max_slippage_exit_bps: 100
  max_delta_drift: 0.005  # 0.5%
  
  # LST Monitoring
  lst:
    warning_premium: 0.03  # 3%
    critical_premium: 0.05  # 5%
    warning_discount: 0.01  # 1%
    critical_discount: 0.02  # 2%
```

### 8.2 Transaction Allowlist

```python
class TransactionValidator:
    """
    Validates all transactions before signing.
    Prevents compromised bot from draining funds.
    """
    
    # Allowlisted programs/contracts
    ALLOWED_SOLANA_PROGRAMS = [
        "Marginfi program",
        "Kamino program", 
        "Solend program",
        "Drift program",
        "Asgard program"
    ]
    
    ALLOWED_HYPERLIQUID_CONTRACTS = [
        "Hyperliquid exchange"
    ]
    
    # Withdrawal addresses (hardware wallet under operator control)
    AUTHORIZED_WITHDRAWAL_SOLANA = "HARDWARE_WALLET_ADDRESS"
    AUTHORIZED_WITHDRAWAL_HYPERLIQUID = "HARDWARE_WALLET_ADDRESS"
    
    async def validate_transaction(self, tx: Transaction, chain: str) -> bool:
        """
        Verify transaction only interacts with allowlisted programs.
        Verify any transfers go to authorized withdrawal addresses only.
        
        Solana validation:
        - Decode transaction and inspect all instruction program IDs
        - Verify against ALLOWED_SOLANA_PROGRAMS allowlist
        - Check Account Metas for unexpected draining addresses
        - Reject if any instruction calls unknown programs
        
        Hyperliquid validation:
        - Verify EIP-712 domain separator matches expected
        - Verify chain ID prevents cross-chain replay
        - Validate action type is in allowed set (order, updateLeverage, etc.)
        """
        pass
```

### 8.3 Pause Mechanism

```python
class PauseController:
    """
    Administrative pause without requiring private keys.
    """
    
    def __init__(self, admin_api_key: str):
        self.paused = False
        self.admin_api_key = admin_api_key
    
    def pause(self, api_key: str, reason: str):
        """Halt all new position entries immediately."""
        pass
    
    def resume(self, api_key: str):
        """Resume normal operations."""
        pass
    
    def check_paused(self) -> bool:
        """Called before any entry execution."""
        pass
```

### 8.4 Circuit Breakers

| Condition | Action | Cooldown |
|-----------|--------|----------|
| Asgard HF < 10% for 20s | Emergency close both | Immediate |
| Hyperliquid MF < 20% for 20s | Close short, then long | Immediate |
| Total APY < 0 | Evaluate exit cost vs bleed | Immediate |
| Price deviation > 2% | Pause new entries | 30 min |
| LST premium > 5% or discount > 2% | Emergency close | Immediate |
| Solana gas > 0.01 SOL | Pause Asgard ops | Until < 0.005 |
| Chain outage detected | Close reachable chain first | Immediate |

---

## 9. Profitability Analysis

### 9.1 Example: SOL Position with 3x Leverage

| Parameter | Value |
|-----------|-------|
| Capital Deployed | $100,000 (split 50/50) |
| Per Leg Deployed | $50,000 |
| Asgard Protocol | Kamino |
| Long Asset | SOL |
| SOL Lending Yield | 5% APY |
| USDC Borrowing Cost | 8% APY |
| Hyperliquid Funding | -25% APY (shorts paid) |
| **Leverage** | **3x** |
| **Position Size** | **$150,000 each side** |

**Capital Split**:
- Asgard: $50,000 USDC principal → $150,000 SOL long (3x)
  - Lending: $150,000 × 5% = $7,500/year
  - Borrowing: $100,000 × 8% = $8,000/year
  - **Net Carry: -$500/year** (pay to hold)
  - **Net Carry APY: -1%**
- Hyperliquid: $50,000 USDC margin → $150,000 SOL short (3x)
  - Funding: $150,000 × 25% = $37,500/year

**Total Calculation**:
```
Hyperliquid Funding Earned: $37,500 (75% APY on $50k)
Asgard Net Carry: -$500 (-1% APY on $50k)
Gross Profit: $37,000

Costs:
- Solana gas (entry+exit): ~$1
- Arbitrum gas (entry+exit): ~$20
- Slippage (0.5% entry, 1% exit): ~$2,250
- Protocol fees: ~$400

Net Annual Profit: ~$34,300
ROI on Capital: 34.3%
```

### 9.2 Position Sizing Rules

```python
class PositionSizer:
    """
    Determines position size based on available capital.
    """
    
    MIN_POSITION_USD = 1000
    DEFAULT_DEPLOYMENT_PCT = 0.10  # 10% of available capital
    MAX_DEPLOYMENT_PCT = 0.50      # 50% max
    
    def calculate_position_size(self, 
                                solana_balance: float,
                                hyperliquid_balance: float,
                                current_leverage: float = 3.0) -> PositionSize:
        """
        1. Find minimum balance across chains
        2. Apply deployment percentage (start conservative 10%)
        3. Calculate per-leg deployment (50/50 split)
        4. Calculate position size: deployment × leverage
        """
        min_balance = min(solana_balance, hyperliquid_balance)
        deployment = min_balance * self.DEFAULT_DEPLOYMENT_PCT
        per_leg = deployment / 2
        position_size = per_leg * current_leverage
        
        return PositionSize(
            total_deployment=deployment,
            per_leg=per_leg,
            position_size=position_size,
            leverage=current_leverage
        )
```

---

## 10. Project Structure

```
delta-neutral-arb/
├── src/
│   ├── __init__.py
│   ├── config/
│   │   ├── settings.yaml
│   │   └── secrets.env
│   ├── core/
│   │   ├── opportunity_detector.py
│   │   ├── position_manager.py
│   │   ├── position_sizer.py
│   │   ├── pause_controller.py
│   │   └── risk_engine.py
│   ├── venues/
│   │   ├── asgard/
│   │   │   ├── client.py
│   │   │   ├── transactions.py
│   │   │   └── models.py
│   │   └── hyperliquid/
│   │       ├── client.py
│   │       ├── signer.py
│   │       └── models.py
│   ├── chain/
│   │   ├── solana.py
│   │   ├── arbitrum.py
│   │   └── outage_detector.py
│   ├── state/
│   │   ├── persistence.py
│   │   └── state_machine.py
│   ├── security/
│   │   ├── transaction_validator.py
│   │   └── allowlist.py
│   ├── models/
│   │   ├── opportunity.py
│   │   ├── position.py
│   │   └── funding.py
│   └── utils/
│       ├── logger.py
│       ├── retry.py
│       └── fee_monitor.py
├── tests/
├── docker/
└── requirements.txt
```

---

## 11. API Keys & Credentials

| Venue | Credential | Security |
|-------|------------|----------|
| Asgard | X-API-Key | Environment variable |
| Solana | Private key (ed25519) | HSM/AWS KMS - SEPARATE from Hyperliquid |
| Hyperliquid | Private key (secp256k1) | HSM/AWS KMS - SEPARATE from Solana |
| Admin | API key for pause/resume | Environment variable |

### Wallet Setup

1. **Solana**: Generate new keypair, use for Asgard positions only
2. **Hyperliquid**: Generate new EVM wallet, deposit USDC
3. **Withdrawal**: Hardware wallet under operator control (allowlisted)

---

## 12. Monitoring & Alerting

### Metrics to Track

- Current funding rate (Hyperliquid) - current and predicted
- Net borrowing rate (Asgard by protocol)
- Total position APY (funding + net carry + staking)
- Position health (Asgard HF, Hyperliquid MF)
- Delta drift (long vs short USD value)
- LST premium/discount
- Accumulated funding earned
- Accumulated net borrowing cost
- PnL by position

### Alerts

- Funding rate flip detected
- Health factor approaching threshold
- Delta drift > 0.5%
- LST depeg warning/critical
- Price deviation > 0.5%
- Position close to liquidation
- Chain outage detected
- API errors > 3 in 5 minutes
- Transaction submission failures
- Fee market spike detected

---

## Appendix A: API References

### A.1 Asgard Finance
- Docs: https://github.com/asgardfi/api-docs
- Base: `https://v2-ultra-edge.asgard.finance/margin-trading`
- Contact: @asgardfi (Telegram) for API key

### A.2 Hyperliquid
- Docs: https://hyperliquid.gitbook.io/hyperliquid-docs/
- Info API: `https://api.hyperliquid.xyz/info`
- Exchange API: `https://api.hyperliquid.xyz/exchange`
- Python SDK: https://github.com/hyperliquid-dex/hyperliquid-python-sdk

### A.3 RPC Providers
- Solana: Helius or Triton (with smart transaction support)
- Arbitrum: Alchemy or QuickNode

---

*Document Version: 2.1 - Asgard + Hyperliquid*
*Last Updated: 2025-02-03*

---

## Change Log

### v2.1 (2025-02-03)
- Added detailed execution failure recovery procedures
- Specified retry logic: 15 attempts every 2 seconds for Hyperliquid entry
- Added stop-loss monitoring during retry window (1% SOL movement trigger)
- Defined fill price validation with 0.5% soft stop threshold
- Specified LST drift rebalancing: cost-based approach
- Added dynamic priority fee strategy (75th percentile + 25% premium)
- Specified state machine recovery for SIGNED/SUBMITTED edge cases
- Added protocol selection tie-breaker and capacity safety margin
- Added partial fill handling for Hyperliquid orders
- Specified transaction rebroadcasting with fresh blockhash approach
- Defined transaction validation details (program ID inspection, EIP-712)
- Added SQLite as state store with signature-only persistence
- Created FUTURE_RELEASES.md for deferred features
