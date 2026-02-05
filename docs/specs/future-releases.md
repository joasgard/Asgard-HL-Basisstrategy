# Future Releases & Roadmap

This document tracks features, improvements, open questions, and enhancements planned for future releases.

---

## Table of Contents

1. [Critical Items (Already Implemented)](#critical-items-already-implemented)
2. [Release Roadmap](#release-roadmap)
   - [v1.0 (MVP / Parallel)](#v10-mvp--parallel)
   - [v1.1 (High Priority)](#v11-high-priority)
   - [v1.2 (Medium Priority)](#v12-medium-priority)
   - [v1.3 (Lower Priority)](#v13-lower-priority)
   - [v2.0 (Major Features)](#v20-major-features)
   - [v2.0+ (Long-term)](#v20-long-term)
3. [Deferred Technical Questions](#deferred-technical-questions)
4. [Summary Priority Matrix](#summary-priority-matrix)

---

## Critical Items (Already Implemented)

The following items have been incorporated into the current implementation:

### State Machine Recovery (Q21)
- **SIGNED but not SUBMITTED**: Discard and rebuild with fresh blockhash (requires re-signing)
- **SUBMITTED but not CONFIRMED >5min**: Check on-chain via `/refresh-positions`, rebuild if not found
- **CONFIRMED on-chain but DB says SUBMITTED**: Reconcile via position existence check

### Transaction Validation (Q22)
- Decode and inspect Solana instruction program IDs against allowlist
- Verify EIP-712 domain separator and chain ID for Hyperliquid
- Reject transactions with unexpected accounts

### Exit Flow Resilience (Q25)
- Hyperliquid close fails: Retry 5 times, then proceed to close Asgard anyway
- Asgard close fails after Hyperliquid closed: Retry aggressively with 2x priority fee, alert if still failing after 60s
- Maximum single-leg exposure time: 120 seconds before emergency procedures

### Dynamic Priority Fees (Q26)
- Percentile-based: 75th percentile of recent landed transactions + 25% premium
- Maximum: 0.01 SOL per transaction (emergency: 0.02 SOL)
- Urgency-adjusted: Stop-loss uses 90th percentile + 50% premium

### Protocol Selection Edge Cases (Q30)
- Tie-breaker: Marginfi > Kamino > Solend > Drift
- Capacity safety margin: Require 1.2x needed borrow
- Protocol switching: Not implemented in v1 (future: position migration)

### Partial Fills (Q33)
- Hyperliquid: Accept partial, immediately retry remaining size
- Asgard: Track target vs actual size, rebalance if drift > 0.1%

---

## Release Roadmap

---

### v1.0 (MVP / Parallel)

#### 1. Paper Trading Mode

**Current State**: Not implemented

**Implementation**:
```python
class PaperTradingExecutor:
    """
    Simulates execution without real capital.
    """
    
    def execute_entry(self, opportunity: Opportunity) -> SimulatedPosition:
        """
        - Record entry price from oracle
        - Simulate funding accrual
        - Simulate borrowing costs
        - Track PnL without real transactions
        """
        pass
    
    def audit_logs(self) -> PerformanceReport:
        """
        Detailed logging for strategy validation:
        - Entry/exit timing
        - Slippage estimates
        - Funding prediction accuracy
        - Opportunity capture rate
        """
        pass
```

**Priority**: High (for strategy validation)

---

### v1.1 (High Priority)

#### 2. Improved Asgard Close Timeout Handling

**Current State (MVP)**:
- 60-second timeout with 3 retry attempts
- If Hyperliquid close fails, proceed to close Asgard anyway

**Future Implementation**:
- **Graceful Degradation**: 
  - If one leg fails to close, enter "recovery mode"
  - Continuous retry of failed leg
  - Adjust the open leg to reduce risk (partial close if possible)
  - Escalate to operator notification after 5 minutes
  
- **Partial Close Support**:
  - Close portion of position to reduce risk while retrying
  - Requires Asgard API support for partial position closes

**Priority**: High

---

#### 3. Funding Rate API Fallbacks

**Current State (MVP)**:
- If Hyperliquid funding rate API is unavailable, the bot cannot make entry decisions
- No fallback data source implemented

**Future Implementation**:
- **Primary**: Hyperliquid API
- **Fallback 1**: Cache recent funding rates (last known good value with decay)
- **Fallback 2**: Third-party oracle (e.g., Pyth Network funding rate feeds)
- **Decision Logic**: 
  - If primary fails, use cached data with increased risk premium
  - If cached data > 5 minutes old, pause new entries
  - Alert operator of fallback activation

**Priority**: Medium

---

#### 4. Advanced Exit Logic: Patience Mode

**Current State (MVP)**:
- Exits immediately when total APY turns negative
- Does not account for exit slippage vs bleed rate

**Future Implementation**:
```python
class PatienceExitController:
    """
    Waits for favorable exit conditions when profitable on paper
    but facing high exit costs.
    """
    
    MAX_HOLD_TIME_HOURS = 24
    
    def should_exit_now(self, position: Position) -> ExitDecision:
        """
        Calculate exit cost vs bleed rate:
        
        exit_cost = estimated_slippage + fees
        bleed_rate = abs(negative_apy_per_hour)
        
        If exit_cost > 2 × (bleed_rate × hours_to_better_conditions):
            Wait for better exit
        Else:
            Exit now
        """
        pass
```

**Priority**: Medium

---

#### 5. Funding Rate Flip Simulation Testing

**Current State (MVP)**:
- Testing in production with small capital
- No synthetic testing capability

**Future Implementation**:
```python
class FundingFlipSimulator:
    """
    Mocks Hyperliquid API to test exit logic.
    """
    
    def simulate_flip_scenario(self, 
                                start_funding: float,
                                end_funding: float,
                                flip_speed: float):
        """
        Injects synthetic funding rates:
        1. Start at profitable negative funding
        2. Gradually shift to unprofitable positive funding
        3. Verify bot exits at correct threshold
        4. Measure exit timing and slippage
        """
        pass
```

**Priority**: Medium (for testing)

---

### v1.2 (Medium Priority)

#### 6. Dead Man's Switch / Cloud Watchdog

**Current State (MVP)**:
- Not implemented
- Bot may leave positions open if process crashes

**Future Implementation**:
```python
class DeadMansSwitch:
    """
    External watchdog that monitors bot health.
    """
    
    HEARTBEAT_INTERVAL = 60  # seconds
    TIMEOUT_THRESHOLD = 300  # 5 minutes
    
    async def send_heartbeat(self):
        """Called by bot every minute."""
        pass
    
    async def check_health(self):
        """
        Run by external service (e.g., AWS Lambda).
        If heartbeat missing for 5 minutes:
        1. Alert operator
        2. Attempt graceful position closure via backup keys
        3. Escalate if positions remain open
        """
        pass
```

**Priority**: Medium

---

#### 7. Enhanced LST Depeg Protection

**Current State (MVP)**:
- Static thresholds (5% premium / 2% discount = close)

**Future Implementation**:
- **Dynamic Thresholds**: Adjust based on historical volatility
- **Graduated Response**:
  - 3% premium: Reduce position size 25%
  - 5% premium: Reduce position size 50%
  - 7% premium: Full close
- **Correlated Asset Check**: Compare INF basket components for basket drift

**Priority**: Medium

---

#### 8. Telegram Bot Features

Based on Q12, the following bot capabilities are planned:

**Core Features**:
- Real-time alerts (funding flips, health factors, liquidations)
- Configurable heartbeat with severity levels
- Manual pause/resume commands
- Position status queries

**Alert Types**:
- Funding rate flip detected
- Health factor approaching threshold (WARNING/CRITICAL)
- Delta drift > 0.5%
- LST depeg warning/critical
- Position close to liquidation
- Chain outage detected
- Transaction submission failures

**Commands**:
```
/status - Show current positions and health
/pause - Pause new entries
/resume - Resume operations
/heartbeat - Force heartbeat message
/sweep - Trigger profit sweep (future)
/config - View/edit configuration (future)
```

**Priority**: Medium

---

#### 9. Advanced LST Management

Based on Q9:

**Depeg Response Strategies**:
- Gradual depeg: Warning escalation with monitoring frequency increase
- Instant depeg: Emergency close procedures with configurable thresholds
- Directional asymmetry: Different responses for premium vs discount

**LST Selection Optimization**:
- Dynamic LST choice based on staking yield + funding rates
- LST rotation for yield maximization

**Priority**: Medium

---

#### 10. API Key Rotation

**Current State (MVP)**:
- Static API keys
- Rotation requires restart

**Future Implementation**:
- **Hot Rotation**: Update API keys without downtime
- **Key Provider Integration**: AWS Secrets Manager, HashiCorp Vault
- **Automatic Rotation**: Rotate keys on schedule (e.g., monthly)

**Priority**: Low

---

### v1.3 (Lower Priority)

#### 11. Multi-Bridge Support

**Current State (MVP)**:
- Single bridge (highest volume)
- Only used when no positions open

**Future Implementation**:
- **Bridge Comparison**: Real-time comparison of LayerZero, Wormhole, CCTP, deBridge
- **Route Optimization**: Select based on cost + speed + reliability
- **Bridge Insurance**: Optional insurance for large transfers
- **Cross-Chain Rebalancing**: Bridge while positions open (advanced)

**Priority**: Low

---

### v2.0 (Major Features)

#### 12. Cross-Chain Yield Aggregation

**Current State (MVP)**:
- Only Asgard + Hyperliquid

**Future Implementation**:
- **Additional Long Venues**:
  - Flash Trade (Solana)
  - Drift perp-margined spot
  
- **Additional Short Venues**:
  - dYdX v4
  - GMX v2
  - Aevo
  
- **Smart Routing**: Select best venue combination based on real rates

**Priority**: Low

---

#### 13. Multi-Instance & High Availability

Based on Q15:

**Deployment Topologies**:
- Active-passive failover
- Split responsibility (monitoring vs execution)
- Split-brain prevention

**State Coordination**:
- Distributed lock for position management
- Shared state backend (Redis/PostgreSQL)
- Leader election mechanism

**Priority**: Low

---

#### 14. Capital Rebalancing

Based on Q8:

**Rebalancing Triggers**:
- Imbalance threshold: >10% difference
- Time-based: Weekly rebalancing
- Funding-adjusted: Rebalance when cost of imbalance exceeds fees

**Bridge Integration**:
- Highest volume bridge selection
- Bridge fee optimization
- Cross-chain swap alternatives

**Priority**: Low

---

#### 15. Configuration Management

Based on Q27:

**Features**:
- Environment-specific configs (dev/staging/prod)
- Hot-reloadable configuration
- Config validation strategies
- Sensitive parameter storage (code vs config)

**Priority**: Low

---

#### 16. Concurrent Opportunities

Based on Q37:

**Features**:
- Multiple positions per asset evaluation
- Position upgrading (close+reopen for better rates)
- Stacking positions for size building

**Priority**: Medium

---

#### 17. Withdrawal Security & Sweeping

Based on Q31:

**Features**:
- Automated profit sweeping to hardware wallet
- Minimum operational balance enforcement
- Sweep triggers (threshold, time-based, manual)
- Emergency withdrawal procedures

**Priority**: Medium

---

#### 18. Historical Backtesting

**Data Requirements**:
- Hyperliquid funding history API access
- Asgard historical rate data (if available)
- SOL price data for LST drift modeling

**Simulation Features**:
- Replay mode with mocked execution
- PnL calculation validation
- Strategy parameter optimization
- Stress testing with historical volatility periods

**Priority**: Low

---

#### 19. Network Partition Handling

Based on Q38:

**Resilience Features**:
- Split-brain detection
- Reduced functionality mode
- Asymmetric information handling
- Cross-chain reachability monitoring

**Priority**: Medium

---

### v2.0+ (Long-term)

#### 20. Machine Learning Enhancements

**Current State (MVP)**:
- Rule-based opportunity detection

**Future Implementation**:
- **Funding Rate Prediction**: LSTM model for funding rate forecasting
- **Regime Detection**: Classify market conditions (volatile, stable, trending)
- **Position Sizing Optimization**: RL agent for optimal capital allocation
- **Slippage Prediction**: Predict exit costs based on market conditions

**Priority**: Low

---

#### 21. Institutional Features

**Current State (MVP)**:
- Single operator, single strategy

**Future Implementation**:
- **Multi-Strategy**: Run multiple delta-neutral strategies simultaneously
- **Sub-Accounts**: Isolate capital across strategies
- **Reporting**: GAAP-compliant PnL reporting
- **Compliance**: KYC/AML integration for institutional clients
- **Insurance Fund**: Self-insurance against smart contract risk

**Priority**: Low

---

#### 22. Risk Management Enhancements

**Position Sizing v2**:
- Kelly criterion-based sizing
- Volatility-adjusted position limits
- Drawdown-based sizing reduction

**Correlation Monitoring**:
- SOL ecosystem correlation breakdown
- Cross-asset spread monitoring
- Macro event detection

**Priority**: Low

---

## Deferred Technical Questions

The following implementation details and technical questions are deferred to their respective releases:

### Q23: Funding Rate Volatility Calculation Details (v1.1)

Details to finalize:
- Rolling vs fixed window for 168h lookback
- Volatility metric: Standard deviation vs mean absolute deviation
- Outlier exclusion criteria for liquidation spikes
- MAX_FUNDING_VOLATILITY threshold definition (std < 0.5 of mean?)

**Impact**: Medium - refines opportunity filtering

---

### Q24: Polling Synchronization (v1.1)

Implementation details:
- Synchronized vs independent polling
- Handling query latency gaps for delta calculations
- Health factor percentage conversion formula
- Asyncio.gather() vs sequential execution

**Impact**: Low - implementation optimization

---

### Q28: Testing Strategy (v1.1 partial, v2.0 full)

Components:
- Comprehensive unit test suite with mocked APIs
- Integration tests against devnet/testnet
- Chaos testing framework (RPC failures, delays, rate limits)
- Property-based testing for opportunity detection
- Historical simulation mode for PnL validation

**Impact**: High for reliability

---

### Q29: Logging & Observability (v1.1)

Features:
- Structured JSON logging
- Log level configuration (DEBUG/INFO/WARNING/ERROR)
- Sensitive data redaction (keys, signatures)
- Correlation IDs for request tracing
- Log retention and shipping configuration

**Impact**: Medium - production debugging

---

### Q32: API Rate Limiting & Backpressure (v1.1)

Implementation:
- Client-side token bucket rate limiting
- Exponential backoff with jitter on 429 errors
- Circuit breaker pattern for repeated failures
- Maximum latency SLOs for opportunity detection

**Impact**: Medium - prevents API bans

---

### Q34: Time Synchronization (v1.1)

Considerations:
- NTP sync requirement
- Blockchain timestamp vs system clock
- Funding payment timing tracking

**Impact**: Low - minor precision improvement

---

### Q35: Code Quality & CI/CD (v1.1)

Standards:
- Full mypy type coverage
- Ruff/black/isort linting
- Pre-commit hooks
- GitHub Actions CI/CD
- Code review requirements

**Impact**: Low - development process

---

### Q36: Mathematical Precision (v1.1)

Standards:
- Python Decimal for all monetary calculations
- Rounding strategy definition (half-up)
- Precision levels per asset type

**Impact**: Low - edge case precision

---

## Summary Priority Matrix

| Feature | Priority | ETA | Effort |
|---------|----------|-----|--------|
| Paper Trading | High | v1.0 | Medium |
| Improved Close Timeout | High | v1.1 | Medium |
| API Fallbacks | Medium | v1.1 | Low |
| Patience Exit Logic | Medium | v1.1 | Medium |
| Funding Flip Simulator | Medium | v1.1 | Low |
| Dead Man's Switch | Medium | v1.2 | Medium |
| Enhanced LST Protection | Medium | v1.2 | Low |
| Telegram Bot | Medium | v1.2 | Medium |
| Advanced LST Management | Medium | v1.2 | Medium |
| API Key Rotation | Low | v1.2 | Low |
| Multi-Bridge Support | Low | v1.3 | Medium |
| Cross-Chain Aggregation | Low | v2.0 | High |
| Multi-Instance & HA | Low | v2.0 | High |
| Capital Rebalancing | Low | v2.0 | Medium |
| Configuration Management | Low | v2.0 | Low |
| Concurrent Opportunities | Medium | v2.0 | Medium |
| Withdrawal Security | Medium | v2.0 | Medium |
| Historical Backtesting | Low | v2.0 | Medium |
| Network Partition Handling | Medium | v2.0 | Medium |
| ML Enhancements | Low | v2.0+ | High |
| Institutional Features | Low | v2.0+ | High |
| Risk Management v2 | Low | v2.0+ | High |

---

| Technical Question | Status | ETA | Impact |
|-------------------|--------|-----|--------|
| Q23: Funding Volatility Calc | Deferred | v1.1 | Medium |
| Q24: Polling Synchronization | Deferred | v1.1 | Low |
| Q28: Testing Strategy | Partial | v1.1/v2.0 | High |
| Q29: Logging & Observability | Deferred | v1.1 | Medium |
| Q32: API Rate Limiting | Deferred | v1.1 | Medium |
| Q34: Time Synchronization | Deferred | v1.1 | Low |
| Q35: CI/CD & Code Quality | Deferred | v1.1 | Low |
| Q36: Mathematical Precision | Deferred | v1.1 | Low |

---

*Document Version: 2.0 (Consolidated)*
*Last Updated: 2025-02-04*
