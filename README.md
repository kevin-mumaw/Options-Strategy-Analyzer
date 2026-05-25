# 📊 Options Strategy Analyzer

A Google Colab-based options strategy research notebook for identifying and validating directional options trades using technical analysis, reversal detection, market regime filtering, and historical backtesting.

---

## Project Status

- **Current Development Version:** v4.13
- **Status:** Active development and validation
- **Platform:** Google Colab
- **Language:** Python
- **Backtest Performance (v3.4):** 127 trades | 59.8% win rate | 2.64 profit factor | GOOGL, AAPL, MSFT | 2018–2024

---

## Core Capabilities

### Signal Generation
- RSI-based oversold/overbought detection
- Reversal pattern detection (divergence, climax tops, failed breakouts, MA breakdowns)
- Volume analysis (accumulation, distribution, weak rally, selling pressure)
- Multi-timeframe confirmation (daily + weekly trend alignment)
- Bullish reversal signal scoring with conviction levels (WATCH / MODERATE / HIGH)

### Market Context
- Market regime classification: BULLISH / MIXED / BEARISH (QQQ benchmark)
- Regime warm-up history to reduce early UNKNOWN classifications
- Mixed-regime quality filtering (tighter entry requirements in transitional markets)
- Bearish regime participation with selective CALL exceptions

### Options Analysis
- Options chain retrieval with liquidity filters (minimum volume + open interest)
- Near-ATM strike selection (within 10% of current price)
- 45+ DTE expiry targeting
- Greeks display: Delta, Gamma, Theta, Vega (Black-Scholes model)
- IV percentile ranking against 1-year history

### Risk Management
- Dynamic position sizing based on signal conviction (3–5% account risk per trade)
- Maximum 20% account concentration per position
- Hard exit rules: -35% stop loss, +75% profit target, 17-day hold limit
- Account guardrails: max 4 open positions
- IV warning when options are expensive relative to history

### Backtesting & Diagnostics
- Walk-forward backtesting with non-overlapping trades
- Simplified delta/theta P&L model
- Performance metrics: win rate, profit factor, avg win/loss, max drawdown
- Diagnostic tables by year, symbol, setup reason, exit reason, market regime
- Combined diagnostics: symbol + setup, year + regime

### Context Layers (Informational)
- Candlestick pattern detection: Hammer, Shooting Star, Bullish/Bearish Engulfing
- Linear regression slope and channel
- Distance from regression midline
- Fibonacci retracement levels (23.6%, 38.2%, 50.0%, 61.8%, 78.6%)
- Swing high/low detection

### Logging & Output
- CSV trade journal with full signal and sizing detail
- Interactive configuration cell (tickers, mode, dates, toggles)
- Final version review cell (The Good / The Bad / The Ugly / Ideas)

---

## Version History Summary

| Version | Key Change | Win Rate | Profit Factor |
|---------|-----------|----------|---------------|
| v1.0–v1.8 | Core scanner, Greeks, journal, multi-timeframe | — | — |
| v2.0 | Backtesting framework added | — | — |
| v2.2 | Exit parameter optimization (17d hold, -35% stop, +75% target) | — | — |
| v2.4 | Market regime filter (BULLISH/MIXED/BEARISH) | — | — |
| v2.6 | Mixed-regime quality tightening | 63.0%* | 2.52* |
| v2.7 | Benchmark changed SPY → QQQ | — | — |
| v2.8 | Candlestick pattern foundation (informational) | — | — |
| v3.0 | Narrow candlestick filter (did not improve results) | 58.5% | 2.62 |
| v3.1 | Regression context layer (informational) | 59.8% | 2.64 |
| v3.2 | Fibonacci context layer (informational) | 59.8% | 2.64 |
| v3.4 | Diagnostics upgrade — symbol+setup, year+regime tables | 59.8% | 2.64 |

*v2.6 tested on MSFT only (46 trades). v3.x tested on GOOGL, AAPL, MSFT (127 trades, 2018–2024).

---

## Key Backtest Findings (v3.4)

**By Symbol:**
| Symbol | Win Rate | Total P&L |
|--------|----------|-----------|
| MSFT | 64.4% | $7,082 |
| GOOGL | 61.9% | $3,151 |
| AAPL | 52.5% | $2,141 |

**By Setup:**
| Setup | Win Rate | Notes |
|-------|----------|-------|
| Bullish reversal | 75.0% | Strongest setup |
| Clean uptrend | 58.8% | Highest trade count |
| RSI oversold + MA50 support | 56.0% | Weakest in BULLISH regime |

**Known Weaknesses:**
- Strategy is CALL-biased — PUT logic underdeveloped
- Performance tested predominantly in bull market conditions (2018–2024)
- AAPL underperforms MSFT and GOOGL consistently
- Bearish and mixed-regime PUT participation remains limited

---

## Quick Start

### Open the Notebook
Use the notebook in the `notebooks/` folder as the current working version.

### Basic Workflow
1. Open the notebook in Google Colab
2. Run **Cell 1** — installs dependencies
3. Run **Cell 1A** — interactive configuration (tickers, mode, dates)
4. Run remaining cells in order
5. Choose **Live Scan** or **Backtest** mode in the configuration cell
6. Review signals, options data, and risk metrics
7. Validate any strategy changes with backtesting before going live

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
├── notebooks/
│   ├── Options_Strategy_Analyzer_Version_3_4.ipynb   ← current
│   └── archive/
│       └── older versions (v1.x through v3.2)
```

---

## Configuration Reference

| Parameter | Default | Description |
|-----------|---------|-------------|
| `TICKERS` | GOOGL, AAPL, MSFT | Symbols to scan |
| `BACKTEST_MODE` | False | Live scan vs backtest |
| `REGIME_SYMBOL` | QQQ | Market regime benchmark |
| `MIN_DTE` | 45 | Minimum days to expiration |
| `RSI_OVERSOLD` | 35 | RSI oversold threshold |
| `RSI_OVERBOUGHT` | 65 | RSI overbought threshold |
| `ACCOUNT_SIZE` | 4000.00 | Options trading capital |
| `RISK_PCT_MIN` | 3% | Min risk per trade |
| `RISK_PCT_MAX` | 5% | Max risk per trade |
| `STOP_LOSS_PCT` | 35% | Option premium stop loss |
| `PROFIT_TARGET_PCT` | 75% | Option premium profit target |
| `BACKTEST_HOLD_DAYS` | 17 | Max hold period in backtest |

---

## Roadmap

- [ ] Phase 1 — Scanner rewrite: quality scoring gate, clean ranked output, exit prices displayed per signal
- [ ] Phase 2 — PUT signal logic rebuilt from scratch with dedicated bearish criteria
- [ ] Phase 3 — Bear market detection layer that shifts scanner posture by regime automatically
- [ ] Expand liquid watchlist beyond AAPL/MSFT/GOOGL to 20–25 names
- [ ] Streamlit or mobile-accessible interface

---

## Limitations

- Backtest uses simplified delta/theta P&L model — no actual historical option prices
- No IV expansion/contraction modeling
- Assumes liquidity on all tested strikes
- Tested primarily in bull market conditions — bearish regime performance limited
- Not financial advice. Always validate before trading real capital.

---

## Dependencies

- `yfinance >= 0.2.40`
- `pandas >= 2.0`
- `numpy >= 1.24`
- `matplotlib >= 3.7`
- `scipy >= 1.10`
- `pytz`

---

## License

MIT
