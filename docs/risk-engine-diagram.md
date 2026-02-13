# Risk Management Engine

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RISK MANAGEMENT ENGINE                              │
│                         bot/core/risk_engine.py                             │
└─────────────────────────────────────────────────────────────────────────────┘

                          ┌──────────────────┐
                          │  Live Market Data │
                          │  (per position)   │
                          └────────┬─────────┘
                                   │
         ┌─────────────────────────┼──────────────────────────┐
         │                         │                          │
         ▼                         ▼                          ▼
┌─────────────────┐   ┌──────────────────┐   ┌────────────────────────┐
│  Asgard Health  │   │  Hyperliquid     │   │  Funding / Price /     │
│  Factor (HF)    │   │  Margin Fraction │   │  LST / Chain Data      │
└────────┬────────┘   └────────┬─────────┘   └───────────┬────────────┘
         │                     │                          │
         ▼                     ▼                          │
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│               evaluate_exit_trigger(position, ...)                       │
│               ─────────────────────────────────────                     │
│               Priority-ordered exit evaluation:                         │
│                                                                         │
│  ┌─── P1 ──────────────────────────────────────────────────────────┐    │
│  │  CHAIN_OUTAGE  │ chain_outage != None         → CRITICAL EXIT   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │ pass                                     │
│                              ▼                                          │
│  ┌─── P2 ──────────────────────────────────────────────────────────┐    │
│  │  HEALTH_FACTOR │ check_asgard_health(position.asgard)           │    │
│  │                │                                                 │    │
│  │   HF ≤ 5% ──────────→ CRITICAL ──┐                              │    │
│  │   HF ≤ 10% ─────────→ CRITICAL ──┤                              │    │
│  │   HF ≤ 20% ─────────→ WARNING    │  .should_close?              │    │
│  │   HF > 20% ─────────→ NORMAL     │    = CRITICAL or             │    │
│  │                                   │      proximity_triggered     │    │
│  │   Proximity: HF ≤ 24%* for 20s+──┘        → EXIT                │    │
│  │   *(min_HF × 1.20)                                              │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │ pass                                     │
│                              ▼                                          │
│  ┌─── P3 ──────────────────────────────────────────────────────────┐    │
│  │  MARGIN_FRACTION │ check_hyperliquid_margin(position.hyperliquid)│   │
│  │                  │                                               │    │
│  │   MF ≤ 5% ──────────→ CRITICAL ──┐                              │    │
│  │   MF ≤ 10% ─────────→ WARNING    │  .should_close?              │    │
│  │   MF > 10% ─────────→ NORMAL     │    = CRITICAL or             │    │
│  │                                   │      proximity_triggered     │    │
│  │   Proximity: MF ≤ 12%* for 20s+──┘        → EXIT                │    │
│  │   *(MF_threshold × 1.20)                                        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │ pass                                     │
│                              ▼                                          │
│  ┌─── P4 ──────────────────────────────────────────────────────────┐    │
│  │  LST_DEPEG      │ lst_depegged == True        → CRITICAL EXIT   │    │
│  │                  │ (premium >5% or discount >2%)                 │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │ pass                                     │
│                              ▼                                          │
│  ┌─── P5 ──────────────────────────────────────────────────────────┐    │
│  │  PRICE_DEVIATION │ deviation > 2%             → CRITICAL EXIT   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │ pass                                     │
│                              ▼                                          │
│  ┌─── P6 ──────────────────────────────────────────────────────────┐    │
│  │  NEGATIVE_APY    │ APY < 0 AND                                   │    │
│  │                  │ close_cost < 5min_expected_loss               │    │
│  │                  │                            → WARNING EXIT     │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │ pass                                     │
│                              ▼                                          │
│  ┌─── P7 ──────────────────────────────────────────────────────────┐    │
│  │  FUNDING_FLIP    │ shorts currently paid AND                     │    │
│  │                  │ predicted: longs will be paid                 │    │
│  │                  │                            → WARNING EXIT     │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │ pass                                     │
│                              ▼                                          │
│        ExitDecision(should_exit=False, level=worst_of(HF, MF))         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                          │
               exit_decision.should_exit?
                          │
              ┌───── YES ─┴─ NO ────┐
              │                     │
              ▼                     ▼
┌──────────────────────┐   ┌──────────────────┐
│  Circuit Breaker     │   │  Continue         │
│  (bot.py:464-479)    │   │  Monitoring       │
│                      │   └──────────────────┘
│  HEALTH_FACTOR ──→ ASGARD_HEALTH breaker
│  MARGIN_FRACTION → HYPERLIQUID_MARGIN breaker
│  LST_DEPEG ──────→ LST_DEPEG breaker
│                      │
│  Others (funding     │
│  flip, neg APY,      │
│  price dev) do NOT   │
│  trigger breakers    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────────────────────────────┐
│  _execute_exit(position, reason)              │
│  bot.py → PositionManager.close_position()    │
│                                               │
│  1. Map reason string → ExitReason enum       │
│  2. close_position(id, reason=ExitReason)     │
│  3. If result.success:                        │
│       - Remove from tracked positions         │
│       - Save state                            │
│       - Fire position_closed callbacks        │
│       - Increment stats.positions_closed      │
│  4. If !result.success:                       │
│       - Log error, position stays tracked     │
└──────────────────────────────────────────────┘
```

## Additional Check: Delta Drift

Standalone check, not part of `evaluate_exit_trigger`:

```
   drift_ratio
     ≥ 2.0%  ──→ CRITICAL ──→ should_rebalance = True
     ≥ 0.5%  ──→ WARNING
     < 0.5%  ──→ NORMAL     Rebalance if drift_cost > rebalance_cost
```

## Callers

| Caller | Mode | Source |
|--------|------|--------|
| `DeltaNeutralBot._monitor_position()` | Single-tenant | `bot/core/bot.py:445` |
| `PositionMonitorService._check_position()` | Multi-tenant | `bot/core/position_monitor.py` |

- **Single-tenant** uses the full `RiskEngine.evaluate_exit_trigger()` with circuit breakers and callbacks.
- **Multi-tenant** uses a simplified `_evaluate_exit()` that only checks HF ≤ 10%, MF < 10%, and funding flip > 0.

Proximity state is tracked per-position in `risk_engine._proximity_start_times: Dict[str, datetime]`.

## Thresholds (from risk.yaml)

| Category | Parameter | Value |
|----------|-----------|-------|
| Asgard | min_health_factor | 20% |
| Asgard | emergency_health_factor | 10% |
| Asgard | critical_health_factor | 5% |
| Hyperliquid | margin_fraction_threshold | 10% |
| Proximity | distance | within 20% of threshold |
| Proximity | duration | 20 seconds sustained |
| Other | price_deviation | 2% |
| Other | delta_drift_warn | 0.5% |
| Other | delta_drift_crit | 2.0% |
| Other | lst_premium | 5% |
| Other | lst_discount | 2% |
