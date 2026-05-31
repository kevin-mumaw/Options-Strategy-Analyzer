# Changelog
All notable changes to the Options Strategy Analyzer project.

## [4.21.0] - 2026-05-30
### Fixed
- CSP RSI filter tightened to <= 69 (was < 70, allowing RSI exactly 70 through)

## [4.17.0] - 2026-05-27
### Added — Phase 2: PUT Signal Logic
- score_put_setup() — 12-point bearish scoring system
- find_best_put() — ITM put selection with adaptive delta range
- PUT signals displayed in separate section below CALL signals
- Individual stock override — PUT allowed in BULLISH regime if score >= 9
- PUT hard disqualifiers — oversold stocks blocked, extended-down stocks blocked
- Bearish volume scoring — inverse of CALL volume (distribution=2, accumulation=0)
- Footer updated to show CALL + PUT signal counts separately

### Fixed
- rr_fails variable undefined in no-signal display path (v4.16)

### Notes
- First live trade executed: BAC $50 Call July 17 2026
- Stop Limit order required in Robinhood — NOT limit sell
- 
## [4.10.0] - 2026-05-25
### Fixed
- Options now correctly target July 17 monthly expiration over July 2 weekly (target_dte raised from 45 to 52)
- Separated "no option found" from "option found but failed reward/risk" in output
- Reward/risk failures now show actual R/R ratio with actionable message
- Removed silent exception swallowing in find_best_call
- Fixed volume NaN handling in option loop

### Added
- VERSION constant displayed in scan header — always know what code ran
- DISQUALIFIED section for overbought/extended stocks
- OPTION FOUND — FAILED R/R section showing exact R/R for watch candidates
- Adaptive delta range by stock price tier (ITM for <$100, near-ATM for $300+)
- Hard disqualifiers: RSI ≥75, overbought+extended, price >15% above MA50
- Expanded watchlist to 34 symbols across 4 price tiers
- Reward/risk minimum set to 1:2 per Jason Brown's framework
- ITM options preferred per Jason Brown (delta 0.55-0.80 on lower-priced stocks)
  
## [4.0.0] - 2026-05-24
### Added — Phase 1 Scanner Rebuild (options_scanner_v4.py)
- Complete rewrite as importable Python module
- 10-point quality scoring gate — signals only generated at 6+/10
- Scoring: Regime (2) + RSI (2) + Trend (2) + Volume (2) + Weekly (1) + Support (1)
- Bull call spread sizing when single leg exceeds account limits
- "Also Qualified" section for symbols cut off by 3-signal cap
- "Near Misses" section for symbols scoring exactly 5/10
- Plain English reward/risk display on every signal
- Signals that fail minimum reward/risk filtered out entirely
- Liquid watchlist of 25 symbols across 7 sectors
- Exact exit prices (stop, target, time stop) on every signal

### Changed
- Options targeting shifted to ITM preference (delta 0.55–0.80) per Jason Brown
- Minimum reward/risk lowered to 1:2 per Jason Brown's PTU framework
- Spread sizing uses 40% account allocation (defined-risk position)
- Strike width for spreads uses dollar-based logic ($10/$15/$20 by stock price)

### Notes
- Replaces v3.x notebook-based approach with clean module architecture
- Designed to be pulled directly from GitHub into Colab via wget
- Phase 1 covers CALL-side only; Phase 2 will add PUT signal logic
- MACD, Bollinger Bands, and earnings filter planned for Phase 1 completion

## [3.4.0] - 2026-05-23
### Added
- Enhanced diagnostic tables: symbol + setup combined, year + regime combined
- Cleaner breakdown of performance drivers

### Performance (GOOGL, AAPL, MSFT — 2018–2024)
- Total trades: 127
- Win rate: 59.8%
- Profit factor: 2.64
- Strategy rating: GOOD

### Notes
- Last notebook-based version before Phase 1 rebuild
- Benchmark changed from SPY to QQQ in v2.7

## [3.2.0] - 2026-05-22
### Added
- Fibonacci retracement levels (23.6%, 38.2%, 50%, 61.8%, 78.6%)
- Swing high/low detection for Fibonacci anchoring
- Fibonacci context display (informational only)

## [3.1.0] - 2026-05-21
### Added
- Linear regression slope and channel
- Distance from regression midline
- Regression context display (informational only)

## [3.0.0] - 2026-05-20
### Changed
- Candlestick patterns promoted to narrow confirmation filter
- Hammer, Shooting Star, Engulfing patterns active in signal logic

### Notes
- Candlestick filter reduced trade count without improving results
- v3.4 reverted candlesticks to informational context only

## [2.9.0] - 2026-05-19
### Added
- Candlestick pattern detection (Hammer, Shooting Star, Bullish/Bearish Engulfing)
- Patterns used as hard confirmation filter

### Fixed
- Known bug: bullish_candle_confirmed undefined in backtest loop
- Caused AAPL and MSFT backtest crashes

### Notes
- v2.9 not recommended as baseline — return to v2.7/v2.8

## [2.8.0] - 2026-05-18
### Added
- Candlestick pattern foundation (informational only)
- Hammer, Shooting Star detection

## [2.7.0] - 2026-05-17
### Changed
- Regime benchmark changed from SPY → QQQ
- Better fit for tech-heavy watchlist

## [2.6.0] - 2026-05-17
### Changed
- Tightened mixed-regime signal filtering
- Higher-quality requirements for mixed-regime bullish CALL setups
- Continued refinement of regime-aware trade selection

### Performance (MSFT only — 2018–2024)
- Total trades: 46
- Win rate: 63.0%
- Profit factor: 2.52
- Strategy rating: EXCELLENT

## [2.5.0] - 2026-05-13
### Added
- Benchmark warm-up history for regime classification
- Setup-by-regime diagnostics

### Changed
- Filtered `Clean uptrend` CALL setups in MIXED regimes by default
- Focus shifted to mixed-regime tightening

## [2.4.0] - 2026-05-08
### Added
- Market regime filter using benchmark trend structure
- Regime classification: BULLISH, MIXED, BEARISH
- Regime-aware signal filtering
- Backtest diagnostics by regime

### Changed
- Reduced bullish CALL exposure in bearish conditions
- Added modest bearish-regime PUT expansion

## [2.3.0] - 2026-05-05
### Added
- Expanded default backtest range to start in 2018
- Final version review cell
- Improved notebook structure and backtest realism

### Changed
- Prevented overlapping trades on the same ticker in backtesting

## [2.2.0] - 2026-05-02
### Changed
- Optimized exit parameters
- Hold period reduced: 21 days → 17 days
- Stop loss tightened: -50% → -35%
- Profit target adjusted: +100% → +75%

## [2.1.0] - 2026-04-28
### Added
- Interactive configuration (Code Cell 1A) for easy ticker/mode selection
- User prompts for tickers, backtest mode, charts, and journal toggles

### Fixed
- PUT signal logic — removed 5 underperforming conditions
- Restricted PUTs to HIGH conviction reversals in UPTREND only
- Restricted overbought PUTs to confirmed DOWNTREND only

### Performance
- Win rate improved: 51% → 68.8% (+17.8%)
- Profit factor improved: 1.84 → 4.16 (+126%)
- Strategy rating: GOOD → EXCELLENT

## [2.0.0] - 2026-04-21
### Added
- Historical backtesting framework
- Walk-forward analysis
- Performance metrics (win rate, profit factor, max drawdown)
- Trade-by-trade CSV export
- Configurable backtest parameters

## [1.8.0] - 2026-04-14
### Added
- Multi-timeframe analysis (daily + weekly)
- Timeframe alignment checking
- Signal conviction boosting for aligned trades

## [1.7.0] - 2026-04-07
### Added
- Price chart visualization with signal markers
- RSI indicator panel
- Timezone configuration (US/Eastern default)
- Fixed timestamp display in journal

## [1.6.0] - 2026-03-23
### Added
- CSV trade journal export
- Automatic logging of all signals

## [1.5.0] - 2026-03-11
### Fixed
- Volume distribution/accumulation logic
- Corrected institutional buying/selling interpretation

## [1.4.1] - 2026-03-04
### Fixed
- Greeks calculation using Black-Scholes model
- Fallback when yfinance doesn't provide Greeks

## [1.4.0] - 2026-03-03
### Added
- Options Greeks display (Delta, Gamma, Theta, Vega)
- Greeks-based position warnings
- Break-even calculations

## [1.3.0] - 2026-02-25
### Added
- Minimum volume and open interest filters
- Liquidity warnings
- Bid/ask spread percentage checks

## [1.2.0] - 2026-02-18
### Added
- Data validation for options chains
- Error handling improvements
- Sanity checks for option pricing

## [1.1.0] - 2026-02-11
### Fixed
- RSI divergence detection using pivot points
- Swing high/low identification

## [1.0.0] - 2026-01-29
### Initial Release
- Basic scanner framework
