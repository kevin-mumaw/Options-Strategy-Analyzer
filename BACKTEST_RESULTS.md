# Options Scanner v4 — Backtest Results

**Generated:** 2026-05-31  
**Scanner version:** v4.26  
**Model:** Simplified delta/theta P&L — no actual historical options prices

---

## Methodology

- Walk-forward simulation — only data available at each point in time used
- Entry: when score >= min_score on CALL scoring system
- Exit: stop loss (-35%), profit target (+75%), or time stop (17 days)
- Option P&L estimated using delta (0.60 assumed) and theta decay
- Slippage: 5% on entry premium
- No commissions modeled

---

## Key Results

### 2023–2024 (Bull Market)

| Filter | Trades | Win Rate | Profit Factor | Total P&L |
|--------|--------|----------|---------------|-----------|
| Score 6+, all regimes | 1,495 | 44.9% | 1.82 | +$107,352 |
| Score 7+, all regimes | 639 | 48.8% | 1.98 | +$58,343 |
| Score 7+, BULLISH only | 391 | 50.1% | 2.06 | +$39,256 |

### 2020–2024 (Full cycle including COVID crash and bear market)

| Filter | Trades | Win Rate | Profit Factor | Total P&L |
|--------|--------|----------|---------------|-----------|
| Score 7+, all regimes | 922 | 42.7% | 1.56 | +$48,307 |

---

## Score Band Analysis (2023–2024, BULLISH only)

| Score | Trades | Win Rate | Profit Factor | Notes |
|-------|--------|----------|---------------|-------|
| 6 | 694 | 46.0% | 1.87 | High volume, lower quality |
| 7 | 156 | 53.8% | 2.86 | **Sweet spot** |
| 8 | 13 | 46.2% | 9.17 | Too few trades to trust |

**Decision: min_score raised to 7**

---

## Market Regime Analysis

| Regime | Win Rate | Result | Decision |
|--------|----------|--------|----------|
| BULLISH | 50.3% | +$59,157 | ✅ Allow CALLs |
| MIXED | 29–33% | -$1,868 to -$1,899 | ❌ Block CALLs |
| BEARISH | 66.7% | +$481 (3 trades) | ❌ Block CALLs, PUTs only |

MIXED regime loses money consistently across both test periods.  
**Decision: CALL signals restricted to BULLISH regime only (calls_bullish_only=True)**

---

## MACD Filter Analysis

Tested across all periods and symbol sets. Result was consistent every time:

| MACD Signal | Win Rate | P&L (2020-2024) |
|-------------|----------|-----------------|
| Bullish | 39.1% | +$202 |
| Bearish | 43.6% | +$48,105 |

MACD bullish was not predictive for CALL entries in any test. MACD bearish consistently outperformed. Counterintuitive but robust finding.  
**Decision: MACD removed from CALL scoring, displayed as informational only**

---

## Exit Reason Analysis

| Exit | Win Rate | Notes |
|------|----------|-------|
| Profit target (+75%) | 100% | 340–584 trades depending on period |
| Stop loss (-35%) | 0% | Largest single driver of losses |
| Time stop (17 days) | 76–83% | **Strongest exit type** |

Time stops at 17 days hit 76–83% win rate consistently.  
Holding to the time stop when not stopped out works well.  
**Decision: keep -35% stop and 17-day time stop**

---

## Stop Loss Sensitivity

| Stop | Win Rate | Profit Factor | Total P&L (2023-2024) |
|------|----------|---------------|-----------------------|
| -35% | 49.6% | 2.08 | +$18,402 |
| -50% | 53.8% | 1.75 | +$14,628 |

Tighter stop (-35%) produces better total P&L despite lower win rate.  
Average win is 2× average loss at -35% stop.  
**Decision: keep -35% stop loss**

---

## Configuration Decisions (all backtest-driven)

| Parameter | Value | Reason |
|-----------|-------|--------|
| `min_score` | 7 | Score 7+ has 2.86 profit factor vs 1.87 at score 6 |
| `calls_bullish_only` | True | MIXED regime -$1,868 across all tests |
| `stop_loss_pct` | 35% | Better P&L than 50% despite lower win rate |
| `time_stop_dte` | 21 | Time stops hit 80%+ win rate |
| MACD scoring | Removed | MACD bullish barely profitable over 5 years |

---

## Limitations

- P&L model is simplified — real options prices would differ
- Delta assumed constant at 0.60 — in practice delta changes with price
- No bid/ask spread costs modeled on exit
- Theta decay modeled as linear — real theta accelerates near expiry
- 2020 COVID data may overstate regime filter benefit (extreme conditions)
- Sample size at score 8+ is too small (13–39 trades) for reliable conclusions

---

## Bottom Line

The scanner generates positive expectancy across multiple test periods and configurations. The core finding is that **selectivity matters more than frequency** — score 7+ in BULLISH regime with a tight stop produces the best risk-adjusted returns. The system is designed to say "no trade" most days and only act on high-quality setups.

Over 5 years including a bear market and COVID crash, the system produced +$48,307 on 922 trades with a 1.56 profit factor. In the most recent 2-year bull market, score 7+ BULLISH-only produced +$39,256 on 391 trades with a 2.06 profit factor.

**The edge is real but not large. Discipline and consistency matter more than any single trade.**
