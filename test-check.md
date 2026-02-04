# Delta Neutral Funding Rate Arbitrage - Comprehensive Test Suite

This document defines a complete, proof-grade test suite for the Delta Neutral Funding Rate Arbitrage Bot. **Every test must pass for the strategy to be considered safe for deployment.**

**Legend:**
- `[ ]` Test not written
- `[~]` Test written but failing
- `[x]` Test passing
- `[-]` N/A or documentation

---

## Category A: Critical Safety & Invariants (MUST PASS)

These tests verify the core safety invariants that prevent catastrophic loss. **All must pass.**

### A.1: Delta Neutrality Invariants

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| A1.01 | `test_delta_neutrality_equal_leverage` | Long leverage == Short leverage enforced (3x default, max 4x) | `[ ]` |
| A1.02 | `test_delta_exposure_calculation` | Net delta = (Long USD Value) - (Short USD Value) / Average Entry | `[ ]` |
| A1.03 | `test_delta_drift_threshold` | Drift > 0.5% triggers rebalance alert | `[ ]` |
| A1.04 | `test_delta_drift_critical` | Drift > 2% triggers immediate rebalance | `[ ]` |
| A1.05 | `test_lst_appreciation_drift` | LST staking rewards increase long value over time (delta drift formula) | `[ ]` |
| A1.06 | `test_rebalance_cost_benefit` | Rebalance only when drift_cost > rebalance_cost (gas + slippage) | `[ ]` |

**A.1 Coverage:** Lines 43, 167-168, 372-373, 663-667, 893

### A.2: Price Consensus Safety

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| A2.01 | `test_price_deviation_calculation` | abs(markPx - oraclePx) / oraclePx | `[ ]` |
| A2.02 | `test_price_deviation_0_5pct_threshold` | Entry blocked if deviation > 0.5% | `[ ]` |
| A2.03 | `test_price_deviation_consecutive_failures` | Outage detected after 3 consecutive failures in 15s | `[ ]` |
| A2.04 | `test_price_deviation_circuit_breaker` | 30min cooldown after >2% deviation | `[ ]` |
| A2.05 | `test_fill_price_validation` | Asgard vs Hyperliquid fill prices within 0.5% | `[ ]` |
| A2.06 | `test_soft_stop_logic` | If deviation > 0.5%, check if still profitable before unwinding | `[ ]` |

**A.2 Coverage:** Lines 341, 360, 471-483, 489-517, 677, 891

### A.3: Liquidation Protection

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| A3.01 | `test_asgard_health_factor_calculation` | HF = Collateral Value / Debt Value | `[ ]` |
| A3.02 | `test_asgard_hf_warning_threshold` | Alert when HF < 20% away from liquidation for 20s+ | `[ ]` |
| A3.03 | `test_asgard_hf_emergency_threshold` | Close when HF < 10% away for 20s+ | `[ ]` |
| A3.04 | `test_asgard_hf_critical_threshold` | Emergency close both legs when HF < 5% | `[ ]` |
| A3.05 | `test_hyperliquid_margin_fraction_calculation` | MF = Account Value / Total Position Value | `[ ]` |
| A3.06 | `test_hyperliquid_mf_warning_threshold` | Alert when MF < 20% away from threshold for 20s+ | `[ ]` |
| A3.07 | `test_hyperliquid_mf_critical_threshold` | Close when MF < 10% away for 20s+ | `[ ]` |
| A3.08 | `test_liquidation_proximity_exit_trigger` | Auto-exit when within 20% of liquidation threshold for 20s | `[ ]` |

**A.3 Coverage:** Lines 876-887, 973-978

### A.4: Funding Rate Safety

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| A4.01 | `test_current_funding_negative_check` | Current funding_rate < 0 (shorts paid) | `[ ]` |
| A4.02 | `test_predicted_funding_negative_check` | Predicted next funding < 0 (shorts will be paid) | `[ ]` |
| A4.03 | `test_conservative_entry_both_conditions` | Entry only when BOTH current AND predicted funding < 0 | `[ ]` |
| A4.04 | `test_funding_volatility_filter` | Skip opportunities if volatility > 50% over 1 week lookback | `[ ]` |
| A4.05 | `test_funding_flip_exit_trigger` | Exit when total APY < 0 AND closing_cost < 5min_expected_loss | `[ ]` |
| A4.06 | `test_funding_annualization_correct` | Hourly = 8hr_rate / 8, Annual = Hourly × 24 × 365 | `[ ]` |
| A4.07 | `test_funding_prediction_formula` | funding = premium + clamp(interest_rate, -0.0001, 0.0001) | `[ ]` |

**A.4 Coverage:** Lines 177-206, 273-298, 561-565, 642-646, 843-846

---

## Category B: Financial Calculations (MUST PASS)

All profitability and cost calculations must be mathematically correct.

### B.1: Net Carry Calculations

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| B1.01 | `test_net_carry_formula_3x` | Net_Carry = (3 × Lending) - (2 × Borrowing) | `[ ]` |
| B1.02 | `test_net_carry_formula_4x` | Net_Carry = (4 × Lending) - (3 × Borrowing) | `[ ]` |
| B1.03 | `test_net_carry_apy_on_deployed` | Net_Carry_APY = Net_Carry / Deployed_Capital | `[ ]` |
| B1.04 | `test_net_carry_positive_carry` | When lending > borrowing × (leverage-1)/leverage | `[ ]` |
| B1.05 | `test_net_carry_negative_carry` | When borrowing cost exceeds lending yield | `[ ]` |
| B1.06 | `test_lending_yield_calculation` | Position_Size × tokenALendingApy | `[ ]` |
| B1.07 | `test_borrowing_cost_calculation` | Borrowed_Amount × tokenBBorrowingApy | `[ ]` |

**B.1 Coverage:** Lines 55-79, 222-246, 317-331

### B.2: Total APY Calculations

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| B2.01 | `test_total_apy_funding_component` | Position_Size × abs(funding_rate) / Deployed | `[ ]` |
| B2.02 | `test_total_apy_net_carry_component` | Net_Carry / Deployed_Capital | `[ ]` |
| B2.03 | `test_total_apy_lst_component` | Position_Size × lst_apy / Deployed_Capital | `[ ]` |
| B2.04 | `test_total_apy_summation` | Total = Funding + Net_Carry + LST_Staking | `[ ]` |
| B2.05 | `test_total_apy_positive_filter` | Only enter when Total_APY > 0 | `[ ]` |
| B2.06 | `test_position_hold_vs_close_decision` | Hold if APY > 0, close if APY < 0 AND cost < bleed | `[ ]` |

**B.2 Coverage:** Lines 56-79, 210-246, 561-565

### B.3: Position Sizing

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| B3.01 | `test_min_position_size_enforced` | MIN_POSITION_USD = $1,000 | `[ ]` |
| B3.02 | `test_default_deployment_pct` | 10% of available capital (conservative) | `[ ]` |
| B3.03 | `test_max_deployment_pct` | 50% maximum of available capital | `[ ]` |
| B3.04 | `test_50_50_split_calculation` | Per_leg = Total_Deployment / 2 | `[ ]` |
| B3.05 | `test_leveraged_position_size` | Position_Size = Per_leg × Leverage | `[ ]` |
| B3.06 | `test_position_sizing_min_balance_constraint` | Use min(solana_balance, hyperliquid_balance) | `[ ]` |

**B.3 Coverage:** Lines 1036-1061

### B.4: Cost Accounting

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| B4.01 | `test_solana_gas_cost_entry_exit` | ~$1 for entry + exit | `[ ]` |
| B4.02 | `test_arbitrum_gas_cost_entry_exit` | ~$20 for entry + exit | `[ ]` |
| B4.03 | `test_slippage_entry_calculation` | 0.5% of position size | `[ ]` |
| B4.04 | `test_slippage_exit_calculation` | 1% of position size | `[ ]` |
| B4.05 | `test_protocol_fees_calculation` | Asgard + Hyperliquid fees | `[ ]` |
| B4.06 | `test_net_profit_after_all_costs` | Gross - Gas - Slippage - Fees | `[ ]` |

**B.4 Coverage:** Lines 1018-1026

---

## Category C: Protocol Integration Logic (MUST PASS)

### C.1: Asgard Protocol Selection

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| C1.01 | `test_protocol_selection_filter_by_token` | Only protocols supporting token_a | `[ ]` |
| C1.02 | `test_protocol_capacity_check` | tokenBMaxBorrowCapacity >= size × (leverage-1) × 1.2 | `[ ]` |
| C1.03 | `test_protocol_capacity_safety_margin` | 20% safety margin on borrow capacity | `[ ]` |
| C1.04 | `test_protocol_net_rate_comparison` | Select highest net carry (lowest cost) | `[ ]` |
| C1.05 | `test_protocol_tie_breaker_order` | Marginfi (0) > Kamino (1) > Solend (2) > Drift (3) | `[ ]` |
| C1.06 | `test_protocol_selection_no_capacity_abort` | Return None if no capacity available | `[ ]` |
| C1.07 | `test_supported_assets_validation` | Only SOL, jitoSOL, jupSOL, INF allowed | `[ ]` |

**C.1 Coverage:** Lines 138-144, 765-777

### C.2: Asgard Transaction State Machine

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| C2.01 | `test_state_transitions_valid` | IDLE → BUILDING → BUILT → SIGNING → SIGNED → SUBMITTING → SUBMITTED → CONFIRMED | `[ ]` |
| C2.02 | `test_state_recovery_signed_not_submitted` | Rebuild with fresh blockhash, re-sign | `[ ]` |
| C2.03 | `test_state_recovery_submitted_not_confirmed` | Poll for 5min, check on-chain, rebuild if needed | `[ ]` |
| C2.04 | `test_intent_id_deduplication` | Same intent_id prevents double-position | `[ ]` |
| C2.05 | `test_transaction_rebroadcast_timeout` | >15s without confirmation triggers rebroadcast | `[ ]` |
| C2.06 | `test_signature_only_persistence` | Only signatures stored, not full tx bytes | `[ ]` |
| C2.07 | `test_build_transaction_step` | POST /create-position, store INTENT_CREATED | `[ ]` |
| C2.08 | `test_sign_transaction_step` | Decode base64, sign with keypair, store SIGNED | `[ ]` |
| C2.09 | `test_submit_transaction_step` | POST /submit-create-position-tx, store SUBMITTED | `[ ]` |
| C2.10 | `test_confirm_transaction_step` | Poll /refresh-positions, store CONFIRMED | `[ ]` |

**C.2 Coverage:** Lines 381-414, 703-736

### C.3: Hyperliquid Order Execution

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| C3.01 | `test_update_leverage_action` | POST /exchange with updateLeverage action | `[ ]` |
| C3.02 | `test_market_order_short_format` | coin: SOL, is_buy: false, order_type: market | `[ ]` |
| C3.03 | `test_order_size_matches_long_exposure` | sz matches Asgard position size in SOL | `[ ]` |
| C3.04 | `test_eip712_signature_format` | Proper EIP-712 signing for orders | `[ ]` |
| C3.05 | `test_entry_retry_logic_15_attempts` | Max 15 retries every 2 seconds | `[ ]` |
| C3.06 | `test_stop_loss_during_retry` | Monitor SOL price, unwind if moves >1% against | `[ ]` |
| C3.07 | `test_partial_fill_handling` | Accept partial, place additional order for remainder | `[ ]` |
| C3.08 | `test_partial_fill_drift_threshold` | Alert if drift > 0.1% after all retries | `[ ]` |
| C3.09 | `test_fill_price_deviation_check` | Within 0.5% of Asgard entry price | `[ ]` |
| C3.10 | `test_exit_first_hyperliquid_then_asgard` | Reduces liquidation risk on short side | `[ ]` |

**C.3 Coverage:** Lines 415-466, 574-610, 808-835, 978

### C.4: Solana Fee Market

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| C4.01 | `test_fee_market_check_pre_entry` | Abort entry if fees exceed threshold for >30s | `[ ]` |
| C4.02 | `test_max_cup_micro_lamports` | 10,000 micro-lamports threshold | `[ ]` |
| C4.03 | `test_dynamic_priority_fee_normal` | 75th percentile + 25% premium | `[ ]` |
| C4.04 | `test_dynamic_priority_fee_high` | 90th percentile + 50% premium | `[ ]` |
| C4.05 | `test_dynamic_priority_fee_emergency` | 90th percentile + 50%, capped at 0.02 SOL | `[ ]` |
| C4.06 | `test_max_fee_per_transaction` | 0.01 SOL max normal, 0.02 SOL max emergency | `[ ]` |

**C.4 Coverage:** Lines 363, 518-558, 982

---

## Category D: Risk Management & Circuit Breakers (MUST PASS)

### D.1: LST Peg Monitoring

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| D1.01 | `test_lst_premium_warning` | Alert if premium > 3% | `[ ]` |
| D1.02 | `test_lst_premium_critical` | Emergency close if premium > 5% | `[ ]` |
| D1.03 | `test_lst_discount_warning` | Alert if discount > 1% | `[ ]` |
| D1.04 | `test_lst_discount_critical` | Emergency close if discount > 2% | `[ ]` |
| D1.05 | `test_effective_delta_with_lst_drift` | Adjust delta for LST-SOL price divergence | `[ ]` |
| D1.06 | `test_lst_vs_sol_price_tracking` | Monitor all LSTs: jitoSOL, jupSOL, INF | `[ ]` |

**D.1 Coverage:** Lines 648-655, 895-900, 981

### D.2: Transaction Security

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| D2.01 | `test_solana_program_allowlist` | Only Marginfi, Kamino, Solend, Drift, Asgard programs | `[ ]` |
| D2.02 | `test_solana_instruction_inspection` | Verify all program IDs in allowlist | `[ ]` |
| D2.03 | `test_solana_account_metas_validation` | Check for unexpected draining addresses | `[ ]` |
| D2.04 | `test_hyperliquid_eip712_domain_check` | Verify domain separator matches expected | `[ ]` |
| D2.05 | `test_hyperliquid_chain_id_prevention` | Prevent cross-chain replay attacks | `[ ]` |
| D2.06 | `test_hyperliquid_action_type_allowlist` | Only order, updateLeverage, etc. | `[ ]` |
| D2.07 | `test_authorized_withdrawal_address` | Only hardware wallet addresses allowed | `[ ]` |
| D2.08 | `test_transaction_validator_rejects_unknown` | Reject transactions with unknown programs | `[ ]` |

**D.2 Coverage:** Lines 906-946

### D.3: Pause & Circuit Breakers

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| D3.01 | `test_pause_controller_halt_new_entries` | pause() stops all new position entries | `[ ]` |
| D3.02 | `test_pause_controller_resume_operations` | resume() restores normal operations | `[ ]` |
| D3.03 | `test_pause_controller_api_key_auth` | Verify admin API key for pause/resume | `[ ]` |
| D3.04 | `test_circuit_asgard_hf_critical` | HF < 5% for 20s → Emergency close both | `[ ]` |
| D3.05 | `test_circuit_hyperliquid_mf_critical` | MF < 20% for 20s → Close short then long | `[ ]` |
| D3.06 | `test_circuit_funding_flip_negative` | Total APY < 0 → Evaluate exit | `[ ]` |
| D3.07 | `test_circuit_price_deviation_2pct` | Deviation > 2% → Pause entries 30min | `[ ]` |
| D3.08 | `test_circuit_lst_depeg` | Premium > 5% or discount > 2% → Emergency close | `[ ]` |
| D3.09 | `test_circuit_gas_spike` | Gas > 0.01 SOL → Pause Asgard ops | `[ ]` |
| D3.10 | `test_circuit_chain_outage` | 3 failures in 15s → Outage mode | `[ ]` |

**D.3 Coverage:** Lines 951-984

### D.4: Chain Outage Handling

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| D4.01 | `test_outage_detection_consecutive_failures` | 3 consecutive RPC failures in 15s | `[ ]` |
| D4.02 | `test_solana_down_hyperliquid_up` | Close HL first, retry Solana until confirmed | `[ ]` |
| D4.03 | `test_hyperliquid_down_solana_up` | Close Asgard first, retry HL until confirmed | `[ ]` |
| D4.04 | `test_outage_recovery_detection` | Chain health restored detection | `[ ]` |
| D4.05 | `test_single_leg_exposure_limit` | Max 120s single-leg exposure during exit | `[ ]` |

**D.4 Coverage:** Lines 669-697

---

## Category E: Position Lifecycle (MUST PASS)

### E.1: Entry Flow

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| E1.01 | `test_preflight_checklist_all_pass` | All 6 checks pass before entry | `[ ]` |
| E1.02 | `test_preflight_wallet_balance_check` | Both wallets have sufficient funds | `[ ]` |
| E1.03 | `test_preflight_price_consensus_check` | Deviation < 0.5% | `[ ]` |
| E1.04 | `test_preflight_funding_validation_check` | Current AND predicted funding < 0 | `[ ]` |
| E1.05 | `test_preflight_protocol_capacity_check` | Selected protocol has capacity | `[ ]` |
| E1.06 | `test_preflight_fee_market_check` | CUP below threshold | `[ ]` |
| E1.07 | `test_preflight_simulation_check` | Both legs build successfully | `[ ]` |
| E1.08 | `test_reference_price_capture` | Capture prices at simulation for validation | `[ ]` |
| E1.09 | `test_asgard_entry_before_hyperliquid` | Execute long first, then short | `[ ]` |
| E1.10 | `test_post_execution_delta_validation` | If delta > 0.5%, trigger rebalance | `[ ]` |
| E1.11 | `test_position_storage_complete` | Store all position data, reference prices, thresholds | `[ ]` |

**E.1 Coverage:** Lines 355-467

### E.2: Exit Flow

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| E2.01 | `test_exit_trigger_total_apy_negative` | Close when total APY turns negative | `[ ]` |
| E2.02 | `test_exit_trigger_cost_vs_bleed` | Close when closing_cost < 5min_expected_loss | `[ ]` |
| E2.03 | `test_exit_trigger_asgard_hf_proximity` | HF approaching threshold (20% away for 20s) | `[ ]` |
| E2.04 | `test_exit_trigger_hyperliquid_mf_proximity` | MF approaching threshold (20% away for 20s) | `[ ]` |
| E2.05 | `test_exit_trigger_price_deviation` | Price deviation > 2% between venues | `[ ]` |
| E2.06 | `test_exit_trigger_manual_override` | Manual close command | `[ ]` |
| E2.07 | `test_exit_trigger_chain_outage` | Close reachable chain first | `[ ]` |
| E2.08 | `test_exit_order_hyperliquid_first` | Close short first to reduce liquidation risk | `[ ]` |
| E2.09 | `test_exit_retry_hyperliquid_5_attempts` | Up to 5 attempts with exponential backoff | `[ ]` |
| E2.10 | `test_exit_asgard_close_flow` | 3-step close: Build → Sign → Submit | `[ ]` |
| E2.11 | `test_exit_settlement_calculation` | Calculate total realized return | `[ ]` |

**E.2 Coverage:** Lines 560-610

### E.3: Monitoring Loop

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| E3.01 | `test_monitor_polling_interval` | 30 seconds for both chains (aligned) | `[ ]` |
| E3.02 | `test_asgard_health_monitor` | Check health_factor every 30s | `[ ]` |
| E3.03 | `test_hyperliquid_margin_monitor` | Check margin fraction every 30s | `[ ]` |
| E3.04 | `test_funding_flip_check` | Check if total APY negative | `[ ]` |
| E3.05 | `test_lst_peg_monitor` | Monitor LST-SOL price ratio | `[ ]` |
| E3.06 | `test_delta_drift_monitor` | Track and calculate drift cost | `[ ]` |

**E.3 Coverage:** Lines 613-667

---

## Category F: Data Models & Validation (MUST PASS)

### F.1: Core Models

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| F1.01 | `test_opportunity_model_validation` | ArbitrageOpportunity dataclass validation | `[ ]` |
| F1.02 | `test_position_model_asgard` | Asgard position: protocol, positionPDA, entry price | `[ ]` |
| F1.03 | `test_position_model_hyperliquid` | HL position: size, entry price | `[ ]` |
| F1.04 | `test_funding_rate_model` | FundingRate: timestamp, rate, coin | `[ ]` |
| F1.05 | `test_asset_enum_validation` | Only SOL, jitoSOL, jupSOL, INF allowed | `[ ]` |
| F1.06 | `test_position_reference_model` | asgard_entry_price, hyperliquid_entry_price, deviation | `[ ]` |
| F1.07 | `test_chain_status_enum` | HEALTHY, DEGRADED, OUTAGE states | `[ ]` |

**F.1 Coverage:** Lines 172-208, 251-299, 303-331, 472-483

### F.2: Settings & Configuration

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| F2.01 | `test_settings_pydantic_validation` | All required env vars present | `[ ]` |
| F2.02 | `test_settings_risk_limits_loaded` | Risk limits from config file | `[ ]` |
| F2.03 | `test_settings_leverage_bounds` | Default 3x, max 4x enforced | `[ ]` |
| F2.04 | `test_settings_asset_allowlist` | Only allowed assets configurable | `[ ]` |
| F2.05 | `test_secrets_env_loading` | API keys, private keys from env | `[ ]` |
| F2.06 | `test_secrets_no_hardcoded_keys` | Verify no keys in codebase | `[ ]` |

**F.2 Coverage:** Lines 1115-1128

---

## Category G: Edge Cases & Error Handling (SHOULD PASS)

### G.1: Network & API Failures

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| G1.01 | `test_asgard_5xx_retry` | Exponential backoff on 5xx | `[ ]` |
| G1.02 | `test_asgard_rate_limit_handling` | 1 req/sec enforced | `[ ]` |
| G1.03 | `test_hyperliquid_retry_logic` | Retry on temporary failures | `[ ]` |
| G1.04 | `test_solana_rpc_failover` | Switch RPC on repeated failures | `[ ]` |
| G1.05 | `test_arbitrum_rpc_failover` | Switch RPC on repeated failures | `[ ]` |
| G1.06 | `test_api_timeout_handling` | Graceful timeout with retry | `[ ]` |

### G.2: Transaction Failures

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| G2.01 | `test_asgard_transaction_build_failure` | Handle build errors gracefully | `[ ]` |
| G2.02 | `test_asgard_transaction_sign_failure` | Handle sign errors, state recovery | `[ ]` |
| G2.03 | `test_asgard_transaction_submit_failure` | Retry submission with fresh blockhash | `[ ]` |
| G2.04 | `test_asgard_transaction_dropped` | Detect dropped tx, rebuild and resubmit | `[ ]` |
| G2.05 | `test_hyperliquid_order_rejected` | Handle rejection, unwind if needed | `[ ]` |
| G2.06 | `test_mismatched_fill_sizes` | Long and short different sizes, rebalance | `[ ]` |

### G.3: Market Conditions

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| G3.01 | `test_extreme_funding_volatility` | Skip entry during high volatility | `[ ]` |
| G3.02 | `test_zero_liquidity_scenario` | Abort if no protocol capacity | `[ ]` |
| G3.03 | `test_negative_net_carry_extreme` | Evaluate if funding still profitable | `[ ]` |
| G3.04 | `test_solana_congestion_extreme` | Dynamic fees up to emergency cap | `[ ]` |
| G3.05 | `test_flash_crash_protection` | Price deviation circuit breaker triggers | `[ ]` |

### G.4: Recovery Scenarios

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| G4.01 | `test_crash_recovery_position_rebuild` | Restore positions from state DB | `[ ]` |
| G4.02 | `test_crash_recovery_incomplete_tx` | Handle SIGNED but not SUBMITTED | `[ ]` |
| G4.03 | `test_crash_recovery_partial_position` | One leg confirmed, one pending | `[ ]` |
| G4.04 | `test_startup_state_validation` | Verify state consistency on start | `[ ]` |

---

## Category H: Integration & E2E (MUST PASS)

### H.1: Full Flow Integration

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| H1.01 | `test_full_entry_flow_mocked` | Complete entry with mocked APIs | `[ ]` |
| H1.02 | `test_full_exit_flow_mocked` | Complete exit with mocked APIs | `[ ]` |
| H1.03 | `test_opportunity_to_position_lifecycle` | Detect → Enter → Monitor → Exit | `[ ]` |
| H1.04 | `test_emergency_close_both_legs` | Trigger emergency, verify both closed | `[ ]` |
| H1.05 | `test_monitoring_cycle_complete` | Full monitoring loop with all checks | `[ ]` |

### H.2: Shadow Trading

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| H2.01 | `test_shadow_entry_logging` | Log simulated entry | `[ ]` |
| H2.02 | `test_shadow_exit_logging` | Log simulated exit | `[ ]` |
| H2.03 | `test_shadow_pnl_calculation` | Calculate simulated PnL | `[ ]` |

---

## Category I: Infrastructure (MUST PASS)

### I.1: Deployment

| Test ID | Test Name | Logic Coverage | Status |
|---------|-----------|----------------|--------|
| I1.01 | `test_docker_build_success` | Docker image builds without errors | `[ ]` |
| I1.02 | `test_docker_container_runs` | Container starts and stays running | `[ ]` |
| I1.03 | `test_docker_health_check` | Health endpoint responds correctly | `[ ]` |
| I1.04 | `test_logging_json_output` | Structured JSON logging | `[ ]` |
| I1.05 | `test_metrics_endpoint` | Prometheus metrics exposed | `[ ]` |

---

## Test Summary

### By Category

| Category | Tests | Passing | Critical | Notes |
|----------|-------|---------|----------|-------|
| A. Safety Invariants | 26 | 8 | 26 | Partial - Phase 6 pending |
| B. Financial Calculations | 23 | 23 | 23 | ✅ Complete |
| C. Protocol Integration | 26 | 26 | 26 | ✅ Complete |
| D. Risk Management | 28 | 4 | 28 | Partial - Phase 6 pending |
| E. Position Lifecycle | 21 | 8 | 21 | Partial - 5.3+ pending |
| F. Data Models | 13 | 13 | 13 | ✅ Complete |
| G. Edge Cases | 20 | 10 | 0 | Partial coverage |
| H. Integration | 8 | 0 | 8 | Pending |
| I. Infrastructure | 5 | 4 | 5 | Mostly complete |
| **Total** | **170** | **96** | **170 Critical** | **299 actual tests passing** |

### Sign-Off Checklist

**Paper Trading Ready:**
- [ ] All Category A-F tests passing (137 tests)
- [ ] All Category H integration tests passing (8 tests)
- [ ] Code coverage > 85%
- [ ] Shadow mode validated for 7 days
- [ ] All critical invariants documented

**Live Trading Ready:**
- [ ] All 170 tests passing
- [ ] All Category G edge case tests passing
- [ ] Paper trading profitable for 14 days
- [ ] Emergency procedures tested in simulation
- [ ] Security audit complete
- [ ] Runbook with all procedures documented
- [ ] Incident response plan tested

### Test Commands

```bash
# Run all critical tests
pytest tests/ -v -m "critical"

# Run safety invariant tests only
pytest tests/ -v -k "safety or invariant"

# Run with coverage report
pytest --cov=src --cov-report=html tests/

# Run specific category
pytest tests/ -v -k "test_a1 or test_a2 or test_a3 or test_a4"
pytest tests/ -v -k "test_b1 or test_b2 or test_b3 or test_b4"

# Run integration tests
pytest tests/integration/ -v

# Run with fail-fast (stop on first failure)
pytest tests/ -v -x
```

---

## Risk Assessment Matrix

| Risk | Severity | Test Coverage | Status |
|------|----------|---------------|--------|
| Delta drift > 0.5% | Critical | A1.03-A1.06, D1.05 | `[ ]` |
| Price deviation > 0.5% at entry | Critical | A2.02, E1.04 | `[ ]` |
| Liquidation on Asgard | Critical | A3.01-A3.04 | `[ ]` |
| Liquidation on Hyperliquid | Critical | A3.05-A3.08 | `[ ]` |
| Funding rate turns positive | Critical | A4.05 | `[ ]` |
| LST depeg > 5% premium | Critical | D1.02 | `[ ]` |
| LST depeg > 2% discount | Critical | D1.04 | `[ ]` |
| Single-leg exposure > 120s | Critical | D4.05 | `[ ]` |
| Chain outage without close | Critical | D4.02-D4.03 | `[ ]` |
| Unauthorized transaction | Critical | D2.01-D2.08 | `[ ]` |
| Double-position on retry | Critical | C2.04 | `[ ]` |

---

*Last Updated: 2026-02-04*
*Version: 2.1 - Post Housekeeping Audit*
*Specification Version: 2.1*
*Actual Test Count: 299 passing*
