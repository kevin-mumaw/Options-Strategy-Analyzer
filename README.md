# 📊 Options Strategy Analyzer

A Google Colab-based options strategy research notebook for identifying and validating directional options trades using technical analysis, market regime filtering, and historical backtesting.

---

## Project Status

- **Current Version:** v4.25
- **Status:** Phase 1, 1.5 & 2 complete — active trading use
- **Platform:** Google Colab
- **Language:** Python
- **Framework:** Jason Brown / PTU trading principles

---

## Backtest Results (v4.25 — 34 symbols, 2023–2024)

| Filter | Trades | Win Rate | Profit Factor | Total P&L |
|--------|--------|----------|---------------|-----------|
| Score 6+, all regimes | 1,495 | 44.9% | 1.82 | $107,352 |
| Score 7+, all regimes | 639 | 48.8% | 1.98 | $58,343 |
| Score 7+, BULLISH only | 391 | 50.1% | 2.06 | $39,256 |

**Key findings:**
- Score 7+ in BULLISH regime: 50.1% win rate, 2.06 profit factor
- MIXED regime loses money at score 7 (-$1,868) — CALL signals restricted to BULLISH
- MACD bullish was NOT predictive for CALL entries — removed from scoring
- Time stops hit 82.5% win rate — holding 17 days works well
- Average winner 2.1× average loser

---

## Scanner Signal Types

### 1. BUY CALL — Directional Bullish
Execute on Robinhood or thinkorswim.

### 2. BUY PUT — Directional Bearish
Execute on Robinhood or thinkorswim. Individual stock override: PUT allowed in BULLISH regime if score ≥ 9.

### 3. SELL PUT (CSP) — Income / Neutral
Execute on thinkorswim only. Requires margin approval. RSI < 70 required (no overbought stocks).

---

## 11-Point Scoring System

MACD was removed from scoring after backtesting showed it was not predictive for CALL entries. It is still displayed as informational context.

| Criteria | Points | Description |
|----------|--------|-------------|
| **Regime** | 0–2 | Market direction via QQQ vs MA50/MA200 |
| **RSI** | 0–2 | Momentum — oversold bounce vs overbought |
| **Trend** | 0–2 | Price structure vs MA20 and MA50 |
| **Volume** | 0–2 | Institutional accumulation vs distribution |
| **Weekly** | 0–1 | Multi-timeframe confirmation |
| **Support** | 0–1 | Entry near key support level |
| **Bollinger** | 0–1 | Volatility/support context |
| **MACD** | info | Informational only — not scored |

**Conviction levels:** 7 = MODERATE | 8–9 = HIGH | 10–11 = VERY HIGH

---

## Hard Disqualifiers
Signals blocked regardless of score:
- RSI ≥ 65 AND price >10% above MA50 (overbought + extended)
- RSI ≥ 75 (severely overbought)
- Price >15% above MA50 in uptrend
- Earnings within 14 days
- MIXED or BEARISH regime (CALL signals only)

---

## Options Selection
- Target 45–55 DTE (prefers standard monthly expirations over weeklies)
- Adaptive delta range by stock price tier:
  - Under $100: delta 0.55–0.80 (ITM preferred)
  - $100–$300: delta 0.50–0.70 (slight ITM bias)
  - Over $300: delta 0.40–0.65 (ATM, best liquidity)
- Minimum volume ≥ 50 OR open interest ≥ 200
- Maximum bid/ask spread 25%

---

## Bull Call Spread Sizing
When single leg premium exceeds account limits, automatically finds a spread:
- Strike width: $10/$15/$20 based on stock price
- Allows up to 40% of account for defined-risk spreads
- Reward/risk checked against 1:2 minimum

---

## Output Sections
1. **Market regime** with plain English summary
2. **CALL signals** — full scoring, Greeks, sizing, exact exit prices, stop limit instructions
3. **PUT signals** — bearish setups with same detail
4. **CSP signals** — income setups for thinkorswim
5. **Disqualified** — blocked by hard rules with reason
6. **Near misses** — one factor away from qualifying
7. **Option found, failed R/R** — good stocks at wrong entry point

---

## Watchlist (34 symbols across 4 price tiers)

| Tier | Price Range | Symbols |
|------|-------------|---------|
| Tier 1 | $10–50 | BAC, F, PLTR, T, PFE, AAL, SOFI |
| Tier 2 | $50–150 | XLF, KO, DIS, NKE, UBER, AMD, INTC, WFC, C, MU |
| Tier 3 | $150–400 | AAPL, GOOGL, JPM, V, MA, XOM, CVX, UNH, JNJ, GS |
| Tier 4 | $400+ | MSFT, AMZN, META, NVDA, COST, SPY, QQQ |

---

## Trade Journal

Built-in CSV trade journal:

```python
# Log a new trade immediately after filling
trade_id = log_entry(symbol="BAC", direction="BUY CALL", ...)

# Log exit when closing position
log_exit(trade_id="BAC-202605270945", exit_premium=5.86, exit_reason="PROFIT TARGET")

# View all trades
show_journal()          # all trades
show_journal("OPEN")    # open positions only
show_journal("WIN")     # winning trades
```

---

## Backtester

```python
df = run_backtest(
    symbols    = ALL_SYMBOLS,
    start_date = "2023-01-01",
    end_date   = "2024-12-31",
    min_score  = 7,
    stop_pct   = 0.35,
)
print_backtest_results(df)
export_backtest(df)
```

Output includes win rate, profit factor, max drawdown, and breakdowns by score band, regime, exit reason, and MACD filter.

---

## Quick Start

### Open in Colab
1. Go to **colab.research.google.com**
2. File → Open notebook → GitHub tab
3. Select `kevin-mumaw/options-strategy-analyzer`
4. Open `options_scanner_v4.ipynb`

### Daily Workflow
1. Run **Force Reload Cell** — pulls latest scanner from GitHub
2. Run **Cell 3** — set account size
3. Run **Cell 4** — run the scan
4. Review signals, check exit rules, decide whether to trade
5. If trading: run **Cell 7** with fill price to log the entry

### Stop Orders in Robinhood
Always use **Stop Limit** (NOT limit sell). Limit sell fills immediately at market open if bid exceeds your limit price.

---

## Repository Structure

```text
options-strategy-analyzer/
│
├── README.md
├── CHANGELOG.md
├── requirements.txt
├── LICENSE
├── .gitignore
│
├── options_scanner_v4.py          ← current scanner module
├── options_scanner_v4.ipynb       ← current notebook
│
└── notebooks/
    └── archive/
        └── older versions (v1.x through v3.4)
```

---

## Version History

| Version | Key Change | Win Rate | Profit Factor |
|---------|-----------|----------|---------------|
| v1.0–v1.8 | Core scanner, Greeks, journal | — | — |
| v2.0 | Backtesting framework | — | — |
| v2.6 | Mixed-regime quality tightening | 63.0%* | 2.52* |
| v3.4 | Diagnostics upgrade | 59.8% | 2.64 |
| v4.0 | Phase 1 rebuild — module architecture | — | — |
| v4.10 | Monthly expiry fix, adaptive delta | — | — |
| v4.11 | Earnings filter (14-day window) | — | — |
| v4.12 | MACD + Bollinger Bands added | — | — |
| v4.14 | Market summary, Eastern time | — | — |
| v4.15 | Trade journal | — | — |
| v4.17 | Phase 2 — PUT signal logic | — | — |
| v4.19 | Phase 1.5 — CSP signals | — | — |
| v4.22 | Backtester v4 | — | — |
| v4.25 | Backtest-driven: min_score→7, BULLISH-only, MACD removed | 50.1% | 2.06 |

*v2.6 tested on MSFT only. v3.x tested on 3 symbols (127 trades, 2018–2024). v4.25 tested on 34 symbols (391 trades, 2023–2024).

---

## Configuration Reference

| Parameter | Default | Description |
|-----------|---------|-------------|
| `account_size` | 5000.00 | Options trading capital |
| `min_score` | 7 | Minimum score to generate signal |
| `calls_bullish_only` | True | CALL signals restricted to BULLISH regime |
| `min_reward_risk` | 2.0 | Minimum reward:risk (1:2 per Jason Brown) |
| `earnings_warn_days` | 14 | Block trades within this many days of earnings |
| `stop_loss_pct` | 35% | Exit if premium drops this much |
| `profit_target_pct` | 75% | Exit if premium rises this much |
| `time_stop_dte` | 21 | Exit when this many DTE remain |
| `target_dte` | 52 | Target days to expiration (favors monthly) |
| `regime_symbol` | QQQ | Market regime benchmark |

---

## Roadmap

### Next
- CAN SLIM integration (feed top-scoring stocks into options scanner as pre-filter)
- Streamlit mobile UI
- GitHub Actions daily scheduled scan

### Phase 3 — Bear Market Detection
- Automatic posture shift based on regime
- Defensive positioning when market turns

---

## Limitations

- Backtest uses simplified delta/theta P&L model — no actual historical option prices
- Tested primarily in bull market conditions (2023–2024)
- Not financial advice. Always validate before trading real capital.

---

## Dependencies

- `yfinance >= 0.2.40`
- `pandas >= 2.0`
- `numpy >= 1.24`
- `scipy >= 1.10`
- `pytz`

---

## License

MIT
