# Feasibility Study: Delta-Neutral Basis Trading

Economic analysis of a SOL/USDC delta-neutral strategy using Asgard (leveraged lending) + Hyperliquid (short perp).

## Key Finding

**2x leverage with an optimized rebalance trigger returns +4.0% annualized** with zero liquidations. 3x is marginal (-3.5%), 4x is not viable (-19.6%). Liquidation penalties — not trading fees — are the dominant cost.

Capital rebalancing (transferring funds between legs at $3/bridge) reduced trading fees by 85% vs. the old full-rotation model. But the real insight is that **every leverage/trigger combo that avoids liquidation is profitable**.

### Three-Model Comparison ($10k)

| Model | 2x | 3x | 4x |
|-------|---:|---:|---:|
| Static (ceiling) | +5.9% | +7.1% | +8.3% |
| **Capital rebalance (realistic)** | **+4.0%** | **-3.5%** | **-19.6%** |
| Full-rotation (floor) | +4.8% | -14.9% | -14.1% |

### Optimal Trigger Per Leverage ($10k)

| Leverage | Best Trigger | Ann Return | Liquidations |
|---------|:-----------:|----------:|------------:|
| 2x | 5x | **+4.0%** | 0 |
| 3x | 6x | -3.5% | 1 |
| 4x | 8x | -19.6% | 5 |

## Files

- **`study.md`** — Full analysis with methodology, results, and recommendations
- **`TRACKER.md`** — Fix & update tracker documenting all changes
- **`data/`** — Raw data (funding rates, lending rates, price candles) + backtest output
- **`scripts/`** — Backtest scripts (static, multi-leverage, multi-size, full-rotation, capital rebalance)

## Reproducing Results

```bash
# Capital rebalance backtest (primary finding)
python3 scripts/backtest_rebalance.py

# Full-rotation backtest (pessimistic floor)
python3 scripts/backtest_managed.py

# Static backtests (theoretical ceiling)
python3 scripts/backtest_full.py
python3 scripts/backtest_leverage.py
python3 scripts/backtest_scaled.py
```

Scripts read local data files from `data/`. Output is saved to `data/rebalance_backtest_output.txt`.
