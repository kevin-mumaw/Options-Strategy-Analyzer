# 📊 Options Strategy Analyzer

A Google Colab-based options strategy research notebook for identifying and validating directional options trades using technical analysis, reversal detection, market regime filtering, and historical backtesting.

---

## Project Status

- **Current Version:** v4.15
- **Status:** Phase 1 complete — active trading use
- **Platform:** Google Colab
- **Language:** Python
- **Framework:** Jason Brown / PTU trading principles

---

## Phase 1 Scanner (options_scanner_v4.py)

A complete rewrite as a standalone importable Python module. Designed to surface 1-3 high-quality trade candidates per scan and clearly say "no trade today" when nothing qualifies.

### Core Design Principles
- Signal only generated when quality score ≥ 6/12
- Every signal includes exact stop, target, and time stop prices
- Minimum 1:2 reward/risk enforced per Jason Brown's framework
- ITM options preferred (delta 0.55–0.80 on lower-priced stocks)
- Hard disqualifiers block trades regardless of score
- No trade is always a valid choice

### 12-Point Scoring System

| Criteria | Points | Description |
|----------|--------|-------------|
| **Regime** | 0–2 | Market direction via QQQ vs MA50/MA200 |
| **RSI** | 0–2 | Momentum — oversold bounce vs overbought |
| **Trend** | 0–2 | Price structure vs MA20 and MA50 |
| **Volume** | 0–2 | Institutional accumulation vs distribution |
| **Weekly** | 0–1 | Multi-timeframe confirmation |
| **Support** | 0–1 | Entry near key support level |
| **MACD** | 0–1 | Momentum confirmation (Jason Brown) |
| **Bollinger** | 0–1 | Volatility/support context (Jason Brown) |

**Conviction levels:** 6–7 = MODERATE | 8–9 = HIGH | 10–12 = VERY HIGH

### Hard Disqualifiers
Signals blocked regardless of score:
- RSI ≥ 65 AND price >10% above MA50 (overbought + extended)
- RSI ≥ 75 (severely overbought)
- Price >15% above MA50 in uptrend
- Earnings within 14 days

### Options Selection
- Target 45–55 DTE (prefers standard monthly expirations over weeklies)
- Adaptive delta range by stock price tier:
  - Under $100: delta 0.55–0.80 (ITM preferred)
  - $100–$300: delta 0.50–0.70 (slight ITM bias)
  - Over $300: delta 0.40–0.65 (ATM, best liquidity)
- Minimum volume ≥ 50 OR open interest ≥ 200
- Maximum bid/ask spread 25%

### Bull Call Spread Sizing
When single leg premium exceeds account limits, automatically finds a spread:
- Strike width: $10/$15/$20 based on stock price
- Allows up to 40% of account for defined-risk spreads
- Reward/risk checked against 1:2 minimum

### Output Sections
1. **Market regime** with plain English summary
2. **Signals** with full scoring breakdown, Greeks, sizing, and exact exit prices
3. **Disqualified** — stocks blocked by hard rules with reason
4. **Near misses** — scored 5/12, one factor away from qualifying
5. **Option found, failed R/R** — good stocks at wrong entry point

### Watchlist (34 symbols across 4 price tiers)

| Tier | Price Range | Symbols |
|------|-------------|---------|
| Tier 1 | $10–50 | BAC, F, PLTR, T, PFE, AAL, SOFI |
| Tier 2 | $50–150 | XLF, KO, DIS, NKE, UBER, AMD, INTC, WFC, C, MU |
| Tier 3 | $150–400 | AAPL, GOOGL, JPM, V, MA, XOM, CVX, UNH, JNJ, GS |
| Tier 4 | $400+ | MSFT, AMZN, META, NVDA, COST, SPY, QQQ |

---

## Trade Journal

Built-in CSV trade journal with three functions:

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

### Execution
- **Single leg calls** → Robinhood or thinkorswim
- **Bull call spreads** → thinkorswim (both legs as one order)

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

## Version History Summary

| Version | Key Change | Win Rate | Profit Factor |
|---------|-----------|----------|---------------|
| v1.0–v1.8 | Core scanner, Greeks, journal, multi-timeframe | — | — |
| v2.0 | Backtesting framework | — | — |
| v2.6 | Mixed-regime quality tightening | 63.0%* | 2.52* |
| v3.4 | Diagnostics upgrade — last notebook version | 59.8% | 2.64 |
| v4.0 | Phase 1 rebuild — module architecture | — | — |
| v4.10 | Monthly expiry fix, R/R separation, adaptive delta | — | — |
| v4.11 | Earnings filter (14-day window) | — | — |
| v4.12 | MACD + Bollinger Bands scoring | — | — |
| v4.14 | Plain English market summary, Eastern time | — | — |
| v4.15 | Trade journal (log_entry, log_exit, show_journal) | — | — |

*v2.6 tested on MSFT only. v3.x tested on GOOGL, AAPL, MSFT (127 trades, 2018–2024).

---

## Configuration Reference

| Parameter | Default | Description |
|-----------|---------|-------------|
| `account_size` | 5000.00 | Options trading capital |
| `min_score` | 6 | Minimum score to generate signal |
| `min_reward_risk` | 2.0 | Minimum reward:risk (1:2 per Jason Brown) |
| `earnings_warn_days` | 14 | Block trades within this many days of earnings |
| `stop_loss_pct` | 35% | Exit if premium drops this much |
| `profit_target_pct` | 75% | Exit if premium rises this much |
| `time_stop_dte` | 21 | Exit when this many DTE remain |
| `target_dte` | 52 | Target days to expiration (favors monthly) |
| `regime_symbol` | QQQ | Market regime benchmark |

---

## Roadmap

### Phase 2 — PUT Signal Logic
- Dedicated bearish criteria (not just inverse of CALL)
- Regime-aware PUT entry rules
- Integration with Phase 1 CALL scanner

### Phase 3 — Bear Market Detection
- Automatic posture shift based on regime
- Defensive positioning when market turns

### Future
- CAN SLIM integration (feed top-scoring stocks into options scanner)
- Streamlit mobile UI
- GitHub Actions daily scheduled scan

---

## Limitations

- Backtest uses simplified delta/theta P&L model — no actual historical option prices
- RS Rating is a proxy, not IBD's proprietary formula
- Tested primarily in bull market conditions
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
