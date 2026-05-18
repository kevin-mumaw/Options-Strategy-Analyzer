# Changelog

All notable changes to the Options Strategy Analyzer project.

## [2.6.0] - 2026-05-17

### Changed
- Tightened mixed-regime signal filtering
- Added higher-quality requirements for mixed-regime bullish CALL setups
- Continued refinement of regime-aware trade selection

### Notes
- Current development version
- Validation ongoing

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
- PUT signal logic - removed 5 underperforming conditions
- Restricted PUTs to HIGH conviction reversals in UPTREND only
- Restricted overbought PUTs to confirmed DOWNTREND only

### Performance
- Win rate improved: 51% → 68.8% (+17.8%)
- Profit factor improved: 1.84 → 4.16 (+126%)
- Total trades reduced: 219 → 138 (eliminated losing trades)
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
