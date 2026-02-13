# Asgard Basis Trading: Economic Feasibility Analysis

**Date:** February 2026
**Pair:** SOL/USDC | **Leverage:** 2x, 3x, 4x | **Capital:** $1k, $10k, $100k

---

## 1. Executive Summary

We backtested a delta-neutral basis trading strategy — long SOL on Asgard (leveraged lending) + short SOL perp on Hyperliquid — using 410 days of real historical rate data (Dec 2024 - Feb 2026) across three leverage levels and three capital sizes.

### By leverage (at $1k capital)

| Metric | 2x | 3x | 4x |
|--------|---:|---:|---:|
| Annualized return | **+5.7%** | **+6.9%** | **+8.2%** |
| Net P&L (410 days) | +$64 | +$78 | +$92 |
| Days with positive P&L | 76.6% | 74.4% | 74.1% |
| 30-day win rate | 57.0% | 56.4% | 55.9% |
| 90-day win rate | **80.4%** | 69.2% | 67.6% |
| Worst 90-day return | -$6 | -$13 | -$20 |

### By capital size (at 3x leverage)

| Metric | $1k | $10k | $100k |
|--------|----:|-----:|------:|
| Annualized return | +6.9% | **+7.1%** | **+7.1%** |
| Net P&L (410 days) | +$78 | +$795 | +$7,929 |
| 30-day win rate | 56.4% | **61.9%** | **61.7%** |
| 90-day win rate | 69.2% | **73.8%** | **73.5%** |
| Median breakeven | 20 days | **12 days** | **13 days** |
| Fees as % of gross | 6.4% | **4.3%** | **4.5%** |

**Bottom line:** The strategy is profitable at every combination of leverage and capital size tested. It scales linearly — returns are nearly identical at $1k, $10k, and $100k — with larger positions being more capital-efficient because gas costs ($2 flat) get amortized. HL orderbook slippage is negligible even at $100k.

**The risk/return trade-off:**
- **2x** — Safest. 80-91% win rate at 90 days (depending on size), smallest drawdowns, but lowest absolute return (+5.7%).
- **3x** — Balanced. +6.9-7.1% return with moderate risk. Most practical default for automated strategies.
- **4x** — Aggressive. Highest return (+8.2%), but worst-case losses triple vs 2x and the carry contribution nearly vanishes.

**The sweet spot:** $10k at 2-3x leverage. Gas costs become negligible (5-8% of fees vs 38-47% at $1k), slippage is effectively zero, and the 90-day win rate reaches 73-90%.

---

## 2. Strategy Overview

The strategy opens two simultaneous legs to capture yield while remaining market-neutral:

| Leg | Platform | Action | Revenue |
|-----|----------|--------|---------|
| Long | Asgard | Leveraged lending (SOL at Nx) | Earns SOL lending APY, pays USDC borrowing APY |
| Short | Hyperliquid | Perpetual futures short | Receives funding when positive (longs pay shorts) |

**Capital split:** 50/50 between legs (Asgard collateral + HL margin).

| Parameter | 2x | 3x | 4x |
|-----------|---:|---:|---:|
| Asgard collateral | $500 | $500 | $500 |
| Notional per leg | $1,000 | $1,500 | $2,000 |
| HL margin | $500 | $500 | $500 |

**Revenue formula:**
```
Net carry (Asgard) = (SOL_lending_rate x leverage) - (USDC_borrow_rate x (leverage - 1))
Funding income (HL) = funding_rate x short_notional  (positive funding = shorts receive)
Total return = Net carry + Funding income - Fees
```

---

## 3. Data & Methodology

### 3.1 Data Sources

| Component | Source | Granularity | Records | Coverage |
|-----------|--------|-------------|---------|----------|
| SOL lending APY | DefiLlama (Kamino SOL pool) | Daily | 819 | Nov 2023 - present |
| USDC borrowing APY | DefiLlama (Kamino USDC pool) | Daily | 471 | Nov 2023 - present |
| SOL funding rate | Hyperliquid `fundingHistory` API | Hourly | 9,807 | Jan 2025 - Feb 2026 |

After aligning all three: **410 overlapping days** (Dec 31, 2024 - Feb 13, 2026).

DefiLlama Kamino rates are used as a proxy for Asgard's underlying protocol rates. Asgard does not currently expose historical rate data through its API.

### 3.2 Rate Environment

| Metric | Average | Range |
|--------|---------|-------|
| SOL lending APY | 5.24% | 3.6% - 7.9% |
| USDC borrowing APY | 6.71% | 4.2% - 14.5% |
| HL funding APY | +4.16% | -25.4% to +19.9% |

The average SOL lending rate (5.24%) is *lower* than USDC borrowing (6.71%), meaning the Asgard carry is negative at 1x. Leverage amplifies lending income, which is what makes the carry positive — but only barely at lower multiples.

---

## 4. Historical Performance

### 4.1 Overall P&L

| Component | 2x | 3x | 4x |
|-----------|---:|---:|---:|
| Asgard carry (long leg) | +$21.14 | +$12.87 | +$4.60 |
| HL funding (short leg) | +$46.74 | +$70.12 | +$93.49 |
| **Gross** | **+$67.89** | **+$82.99** | **+$98.09** |
| Fees | -$4.20 | -$5.30 | -$6.40 |
| **Net** | **+$63.69** | **+$77.69** | **+$91.69** |
| Annualized | **+5.67%** | **+6.92%** | **+8.16%** |

A critical pattern emerges across leverage levels:

| Metric | 2x | 3x | 4x |
|--------|---:|---:|---:|
| Asgard carry share of gross | **31.1%** | 15.5% | 4.7% |
| HL funding share of gross | 68.9% | **84.5%** | **95.3%** |
| Avg carry APY (on collateral) | +3.76% | +2.29% | +0.82% |

**At higher leverage, Asgard carry evaporates.** This happens because borrowing costs scale as `(leverage - 1)` while lending income scales as `leverage` — with borrowing rates higher than lending rates, each additional turn of leverage *reduces* net carry. At 4x, carry contributes under 5% of gross returns.

The strategy works at all levels because HL funding scales linearly with notional and is the dominant income source regardless.

### 4.2 Monthly Breakdown (3x)

| Month | SOL Lend | USDC Borr | Carry | HL Fund | Strategy | Cum P&L |
|-------|---------|----------|-------|---------|----------|---------|
| 2024-12 | 5.20% | 14.48% | -13.4% | +1.8% | -7.9% | -$5.41 |
| **2025-01** | 6.40% | 9.87% | -0.5% | **+11.1%** | **+32.7%** | +$8.48 |
| 2025-02 | 7.92% | 9.43% | +4.9% | +1.3% | +8.8% | +$11.86 |
| 2025-03 | 3.57% | 7.61% | -4.5% | -1.8% | -9.8% | +$7.72 |
| 2025-04 | 4.44% | 7.23% | -1.1% | -5.9% | -18.9% | -$0.07 |
| **2025-05** | 5.41% | 7.35% | +1.5% | **+10.6%** | **+33.3%** | +$14.07 |
| **2025-06** | 5.16% | 7.42% | +0.7% | **+6.9%** | **+21.3%** | +$22.83 |
| **2025-07** | 5.62% | 7.22% | +2.4% | **+19.9%** | **+62.0%** | +$49.15 |
| **2025-08** | 5.83% | 5.32% | +6.9% | **+11.8%** | **+42.2%** | +$67.06 |
| **2025-09** | 5.83% | 6.42% | +4.7% | **+10.8%** | **+37.2%** | +$82.35 |
| 2025-10 | 4.54% | 5.60% | +2.4% | -4.8% | -11.9% | +$77.29 |
| 2025-11 | 4.60% | 5.18% | +3.4% | -2.4% | -3.8% | +$75.71 |
| **2025-12** | 4.05% | 5.06% | +2.0% | **+5.5%** | **+18.6%** | +$83.60 |
| **2026-01** | 4.26% | 4.24% | +4.3% | **+3.1%** | **+13.7%** | +$89.40 |
| 2026-02 | 6.85% | 5.01% | +10.5% | -25.4% | -65.7% | +$77.69 |

*All rates annualized. Bold months had strong HL funding income.*

### 4.3 Leverage Amplification by Month

How the same market conditions produce different outcomes at each leverage:

| Month | 2x | 3x | 4x |
|-------|---:|---:|---:|
| 2024-12 | -0.4% | -7.9% | -15.3% |
| 2025-01 | +25.1% | +32.7% | +40.3% |
| 2025-04 | -10.2% | -18.9% | -27.7% |
| **2025-07** | **+43.7%** | **+62.0%** | **+80.2%** |
| **2026-02** | **-42.2%** | **-65.7%** | **-89.3%** |

*Strategy APY, annualized. Selected months showing amplification effect.*

July 2025 (best month): 4x returned +80% annualized vs 2x at +44%. But Feb 2026 (worst month): 4x lost -89% annualized vs 2x at -42%. **Higher leverage doubles both the upside and the downside.**

### 4.4 Cumulative P&L Trajectory

| Month | 2x | 3x | 4x |
|-------|---:|---:|---:|
| 2024-12 | -$4.21 | -$5.41 | -$6.61 |
| 2025-03 | +$8.22 | +$7.72 | +$7.21 |
| 2025-06 | +$21.34 | +$22.83 | +$24.32 |
| **2025-09** | **+$63.68** | **+$82.35** | **+$101.02** |
| 2025-12 | +$66.73 | +$83.60 | +$100.47 |
| **2026-02** | **+$63.69** | **+$77.69** | **+$91.69** |

All three leverage levels peaked around Sep 2025, then gave back some gains during the Oct-Nov 2025 HL funding drawdown and the sharp Feb 2026 reversal. The 2x trajectory is visibly smoother.

### 4.5 P&L Consistency

| Metric | 2x | 3x | 4x |
|--------|---:|---:|---:|
| Days with positive net P&L | 76.6% | 74.4% | 74.1% |
| Average profitable streak | 10.1 days | 9.2 days | 8.9 days |
| Longest profitable streak | 98 days | 83 days | 83 days |

Lower leverage has slightly better day-to-day consistency. The 2x strategy had a 98-day profitable streak (May-Aug 2025) vs 83 days for 3x and 4x.

---

## 5. Hold Duration & Breakeven

### 5.1 Win Rate by Hold Duration

| Hold | 2x | 3x | 4x |
|-----:|---:|---:|---:|
| 7 days | 5.4% | 7.4% | 9.2% |
| 14 days | 28.7% | 32.0% | 34.8% |
| **30 days** | **57.0%** | **56.4%** | **55.9%** |
| **60 days** | **72.9%** | **67.8%** | **64.4%** |
| **90 days** | **80.4%** | **69.2%** | **67.6%** |

A nuanced trade-off:
- **Short holds (7-14 days):** Higher leverage wins more often because the larger position overcomes fixed fees faster.
- **Long holds (60-90 days):** Lower leverage wins more often because it's less exposed to funding regime shifts that erase gains.
- **30 days:** All three converge near 56-57%.

**2x at 90 days (80.4%) is the highest win rate of any combination.** For automated strategies that can hold for 3 months, 2x is the most reliable choice.

### 5.2 Average and Worst Returns by Hold Duration

| Hold | 2x avg | 3x avg | 4x avg | 2x worst | 3x worst | 4x worst |
|-----:|-------:|-------:|-------:|---------:|---------:|---------:|
| 7d | -$3.02 | -$3.86 | -$4.69 | -$12.59 | -$18.15 | -$23.71 |
| 14d | -$1.76 | -$2.28 | -$2.80 | -$12.45 | -$18.17 | -$23.88 |
| 30d | +$1.23 | +$1.49 | +$1.74 | -$10.78 | -$16.13 | -$21.48 |
| 60d | +$6.72 | +$8.38 | +$10.03 | -$10.32 | -$17.53 | -$24.74 |
| 90d | +$12.66 | +$15.94 | +$19.22 | -$6.28 | -$13.37 | -$20.48 |

Average returns scale proportionally with leverage. But **worst-case losses also scale** — the worst 90-day window at 4x (-$20.48) is 3.3x worse than 2x (-$6.28). This is the core trade-off: 4x earns ~50% more on average but loses ~3x more in the worst case.

### 5.3 Breakeven

| Metric | 2x | 3x | 4x |
|--------|---:|---:|---:|
| Entries that break even | 91.0% | 91.2% | 90.7% |
| Median breakeven | 20 days | 20 days | 19 days |
| Average breakeven | 33.7 days | 35.6 days | 36.8 days |
| 10th percentile (fast) | 9 days | 8 days | 8 days |
| 90th percentile (slow) | 87 days | 101 days | 106 days |

Breakeven is remarkably similar across leverage levels — median ~20 days for all three. This is because both costs and daily income scale with notional. The slight increase in average/P90 breakeven at higher leverage reflects the deeper drawdowns during adverse periods.

### 5.4 Smart Entry

Only entering when trailing 24h HL funding is positive (shorts receiving payments):

| Metric | 2x | 3x | 4x |
|--------|---:|---:|---:|
| 30-day win rate (blind) | 57.0% | 56.4% | 55.9% |
| 30-day win rate (smart) | **63.4%** | **63.1%** | **62.4%** |
| Improvement | +6.4pp | +6.6pp | +6.5pp |

The smart entry filter improves outcomes by ~6.5pp at every leverage level. It's available 73% of the time.

---

## 6. Fee Analysis

### 6.1 Fee Structure by Leverage

| Fee | Rate | 2x | 3x | 4x |
|-----|------|---:|---:|---:|
| **Asgard open** | 0.15% on notional | **$1.50** | **$2.25** | **$3.00** |
| Asgard close | 0% | $0.00 | $0.00 | $0.00 |
| HL taker (open + close) | 0.035% x 2 | $0.70 | $1.05 | $1.40 |
| Gas | flat | $2.00 | $2.00 | $2.00 |
| **Total** | | **$4.20** | **$5.30** | **$6.40** |
| **% of capital** | | **0.42%** | **0.53%** | **0.64%** |
| **% of gross profit** | | **6.2%** | **6.4%** | **6.5%** |

Fees scale with notional but remain a small fraction of gross profit (6-7%) at all leverage levels. The **absence of a close fee** is a meaningful competitive advantage.

### 6.2 Fee Sensitivity (Backtested, 30-day win rate)

| Asgard Fee | 2x | 3x | 4x |
|-----------|---:|---:|---:|
| **0.15% (current)** | **57.0%** | **56.4%** | **55.9%** |
| 0.10% | 59.3% | 57.2% | 56.7% |
| 0.05% | 62.2% | 60.9% | 59.8% |
| Free | 64.6% | 64.0% | 63.3% |

Fee reduction has the largest effect at lower leverage (2x: +7.6pp from 0.15% to free) because fees are a larger share of the smaller absolute returns. At 4x, the same fee change improves win rate by only 7.4pp.

### 6.3 Scaling: $1k → $10k → $100k

#### Fee structure by capital size (3x leverage)

| Component | $1k | $10k | $100k |
|-----------|----:|-----:|------:|
| Asgard open (0.15%) | $2.25 | $22.50 | $225.00 |
| HL taker (round-trip) | $1.05 | $10.50 | $105.00 |
| Gas (flat) | $2.00 | $2.00 | $2.00 |
| **Platform fees** | **$5.30** | **$35.00** | **$332.00** |
| HL slippage (est.) | $0.03 | $0.30 | $38.10 |
| **Total incl. slippage** | **$5.33** | **$35.30** | **$370.10** |
| **Gas as % of total** | **37.5%** | **5.7%** | **0.5%** |

Gas is the dominant cost at $1k (38%) but negligible at $10k+ (<6%). Slippage is negligible at all sizes — even $100k at 4x ($200k notional) only adds $69 of slippage round-trip on a $271M OI market.

#### Backtested performance by capital (3x leverage)

| Metric | $1k | $10k | $100k |
|--------|----:|-----:|------:|
| Annualized return | +6.9% | **+7.1%** | **+7.1%** |
| Net P&L (410 days) | +$78 | +$795 | +$7,929 |
| Fees as % of gross | 6.4% | 4.3% | 4.5% |
| 30-day win rate | 56.4% | **61.9%** | **61.7%** |
| 90-day win rate | 69.2% | **73.8%** | **73.5%** |
| Median breakeven | 20 days | **12 days** | **13 days** |

Larger positions have better win rates and faster breakeven because fixed gas costs are amortized. The return improvement plateaus above $10k — the jump from $1k to $10k (5.5pp on 30-day WR) is far larger than $10k to $100k (0.2pp).

#### Worst-case returns by capital size

| Capital | Hold | 2x worst | 3x worst | 4x worst |
|--------:|-----:|---------:|---------:|---------:|
| $1k | 30d | -$11 | -$16 | -$22 |
| $1k | 90d | -$6 | -$13 | -$21 |
| $10k | 30d | -$90 | -$144 | -$197 |
| $10k | 90d | -$45 | -$116 | -$187 |
| $100k | 30d | -$896 | -$1,453 | -$2,019 |
| $100k | 90d | -$446 | -$1,178 | -$1,918 |

Worst-case losses scale linearly with capital. The maximum 90-day drawdown is 0.4-2.0% of capital depending on leverage — modest for a yield strategy. At $100k/4x, the worst 90-day period would lose ~$1,918 (1.9%).

#### Slippage sensitivity

Slippage model based on HL SOL-PERP orderbook snapshot (Feb 2026, $292M daily volume, $271M OI). We test at 1x (base), 2x (moderate stress), and 5x (severe stress) slippage multipliers:

| Capital | Lev | Base | Slip 2x | Slip 5x | Impact |
|--------:|----:|-----:|--------:|--------:|-------:|
| $1k | 3x | +6.91% | +6.91% | +6.90% | -0.01pp |
| $10k | 3x | +7.07% | +7.07% | +7.06% | -0.01pp |
| $100k | 3x | +7.06% | +7.02% | +6.92% | -0.14pp |
| $100k | 4x | +8.28% | +8.22% | +8.03% | -0.24pp |

**Slippage is a non-issue.** Even at 5x the observed slippage on a $200k notional position (the largest tested), annualized return drops by only 0.24pp. HL's SOL-PERP market is deep enough to absorb positions well beyond $100k without meaningful price impact.

#### Lending rate impact

At current Kamino pool sizes (SOL: $262M supply, USDC: $203M supply):

| Capital | Lev | SOL deposit | % of SOL pool | USDC borrow | % of USDC pool |
|--------:|----:|----------:|-------------:|----------:|--------------:|
| $1k | 3x | $1,500 | 0.001% | $1,000 | 0.001% |
| $10k | 3x | $15,000 | 0.006% | $10,000 | 0.005% |
| $100k | 3x | $150,000 | 0.057% | $100,000 | 0.049% |
| $100k | 4x | $200,000 | 0.076% | $150,000 | 0.074% |

Even the largest position ($100k/4x) represents <0.1% of pool liquidity. Rate impact from our own position is negligible.

**Minimum recommended position: $1,000** (below this, gas dominates). **Sweet spot: $10k+** (gas becomes noise, win rates improve 5-6pp vs $1k).

### 6.4 Competitive Context

| Platform | Open Fee | Close Fee | Round-Trip | Notes |
|----------|----------|-----------|------------|-------|
| **Asgard** | **0.15%** | **0%** | **0.15%** | On notional. No close fee. |
| Marginfi (direct) | ~0.1% swap | ~0.1% swap | ~0.2% | DEX swap slippage both ways |
| Kamino (direct) | ~0.1% swap | ~0.1% swap | ~0.2% | Similar to Marginfi |
| Drift (direct) | 0.1% taker | 0.1% taker | 0.2% | Perp taker fee both ways |

Asgard's 0.15% open + 0% close = 0.15% total compares favorably to direct protocol access (~0.2% round-trip), while providing the abstraction layer, leverage management, and multi-protocol routing.

---

## 7. Risk Factors

### 7.1 Funding Regime Shifts

The biggest risk, and it scales with leverage. Feb 2026 saw -25.4% annualized funding (shorts paying longs):

| Leverage | Feb 2026 strategy APY | P&L impact |
|---------|----------------------:|----------:|
| 2x | -42.2% | -$7.50 |
| 3x | -65.7% | -$11.71 |
| 4x | -89.3% | -$15.91 |

The strategy has no natural hedge against funding reversals. At 4x, a single bad month can erase nearly 4 months of typical gains.

### 7.2 Carry Erosion at Higher Leverage

Asgard net carry degrades as leverage increases because USDC borrowing (6.71% avg) exceeds SOL lending (5.24% avg):

| Leverage | Carry APY (on collateral) | Carry as % of gross |
|---------|-------------------------:|--------------------:|
| 2x | +3.76% | 31.1% |
| 3x | +2.29% | 15.5% |
| 4x | +0.82% | 4.7% |

At 4x, carry is nearly zero — the strategy becomes a pure funding rate play with Asgard acting only as the hedge vehicle. If USDC borrowing rates rise further, carry could turn negative at higher leverage.

### 7.3 Data Limitations

- DefiLlama provides Kamino rates, which may differ from Asgard's executed rates
- 410-day window captures mostly bullish SOL conditions — bearish conditions would have different funding dynamics
- No historical data for Asgard-specific optimizations (multi-protocol routing)

---

## 8. Recommendations

### High Impact

**8.1 Historical Rate API**
Expose historical lending/borrowing rates through the Asgard API. This backtest relied on DefiLlama's Kamino data as a proxy. Native historical data would enable more accurate backtesting and attract quant integrators.

**8.2 Position Asgard as Hedging Infrastructure**
HL funding income drives 69-95% of returns depending on leverage. The product narrative should emphasize: *"Asgard provides the leveraged long leg for delta-neutral strategies that capture perp funding income."* The carry is a bonus, not the core.

**8.3 USDC Borrowing Rate Optimization**
Net carry averaged only +2.29% (3x) because USDC borrowing nearly offsets SOL lending. Any improvement to borrowing rates directly improves carry — and this matters most at higher leverage where carry erodes fastest. Reducing average USDC borrowing from 6.71% to 5.24% (matching SOL lending) would double net carry at 3x.

### Medium Impact

**8.4 Volume-Based Fee Tiers**

| Tier | 30-Day Volume | Fee |
|------|--------------|-----|
| Standard | <$100k | 0.15% |
| Silver | $100k-$500k | 0.10% |
| Gold | $500k-$2M | 0.07% |
| Institutional | >$2M | 0.05% |

Fees are 6-7% of gross profit — tiers are more about adoption signaling than material P&L impact.

**8.5 Leverage Guidance**
The data suggests different optimal leverage for different user profiles:
- **Conservative / automated:** 2x — highest 90-day win rate (80.4%), smallest drawdowns
- **Balanced:** 3x — best risk/return trade-off, most practical default
- **Aggressive / active management:** 4x — highest returns but requires active drawdown management

Surfacing this guidance (with supporting data) in the API or documentation would help users choose appropriately.

**8.6 Regime Detection Signals**
Provide API fields that help bots identify favorable conditions — trailing 7-day funding rate, funding volatility, or a simple indicator. Smart entry improves 30-day win rate by ~6.5pp at all leverage levels.

### Nice to Have

**8.7 Multi-Protocol Carry Routing**
Automatic routing to the best carry across Kamino, Drift, and Marginfi would improve the 2.29% average carry, particularly benefiting higher-leverage positions where carry erosion is most acute.

**8.8 Longer Hold Incentives**
Fee rebates for positions held >30 days would align platform incentives (sticky TVL) with the data: 60+ day holds have the best risk-adjusted outcomes.

**8.9 Basis Trading API Mode**
An intent-level API accepting both legs as a single atomic operation with a bundled fee (e.g., 0.10% combined). Simplifies integrations and provides guaranteed execution or rollback.

---

## 9. Conclusions

1. **The strategy works across all leverage and capital combinations tested.** Returns range from +5.7% (2x) to +8.2% (4x) annualized, with 74-77% of days profitable. Performance is consistent across $1k, $10k, and $100k.

2. **It scales linearly with no degradation.** Annualized returns are essentially identical at $1k, $10k, and $100k (~7% at 3x). HL orderbook slippage is negligible even at $200k notional. Lending pool rate impact is <0.1%. There is no capacity constraint at these sizes.

3. **Larger positions are more efficient.** At $10k+, gas costs become noise (5% of fees vs 38% at $1k), breakeven drops from 20 to 12 days, and 30-day win rate improves 5-6pp. **$10k is the sweet spot** — maximum efficiency with no slippage concerns.

4. **Leverage is a risk dial, not a return multiplier.** 2x → 4x adds only 2.5pp annualized return but triples worst-case 90-day losses and drops the 90-day win rate from 80% to 68%.

5. **The best risk-adjusted configuration is $10k+ at 2x.** This achieves a 90-91% win rate at 90 days, $45 maximum 90-day drawdown on $10k (0.45%), and 12-day median breakeven.

6. **HL funding is the engine, Asgard is the chassis.** Funding income drives 69-95% of gross returns. Asgard's carry contribution shrinks at higher leverage as USDC borrowing erodes it.

7. **Fees are not the bottleneck.** Fees are 3.5-6.5% of gross profit across all configurations. The strategy's economics are driven by funding rate regimes, not entry costs.

8. **Hold 30+ days.** This is the minimum for >50% win probability at every configuration. At 60+ days, 2x reaches 73%.

9. **Carry improvement is Asgard's biggest lever.** Reducing USDC borrowing rates would widen the carry spread, making higher leverage more viable and providing a larger cushion during adverse funding periods.

---

*Data: 410 days of overlapping observations (Dec 2024 - Feb 2026) combining 9,807 hourly SOL funding rates from Hyperliquid, daily SOL lending rates and USDC borrowing rates from DefiLlama (Kamino pools). Slippage model based on HL SOL-PERP orderbook snapshot ($292M daily volume, $271M OI). Lending rate impact estimated from Kamino pool sizes ($262M SOL, $203M USDC). All figures: SOL/USDC. DefiLlama Kamino rates used as proxy for Asgard's underlying protocol rates.*
