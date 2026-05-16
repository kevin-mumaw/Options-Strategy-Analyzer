# 📊 Options Strategy Analyzer

A systematic options trading strategy that combines technical analysis, reversal pattern detection, and rigorous backtesting to identify high-probability directional trades.

![Version](https://img.shields.io/badge/version-2.1-blue)
![Python](https://img.shields.io/badge/python-3.8+-green)
![License](https://img.shields.io/badge/license-MIT-orange)

## 🎯 Performance

Based on 2-year backtest (2023-2024) on GOOGL and AAPL:

| Metric | Result |
|--------|--------|
| **Win Rate** | 68.8% |
| **Profit Factor** | 4.16 |
| **Total Trades** | 138 |
| **Rating** | EXCELLENT |

*Strategy makes $4.16 for every $1 risked over the test period.*

---

## ✨ Features

### Core Capabilities
- **Multi-Factor Signal Generation**: Combines RSI, moving averages, volume analysis, and reversal patterns
- **Historical Backtesting**: Validate strategies on years of data before risking capital
- **Multi-Timeframe Analysis**: Daily + weekly chart confirmation for higher conviction
- **Options Greeks Integration**: Full risk profile with Delta, Theta, Vega, Gamma
- **Dynamic Position Sizing**: Adjusts allocation based on signal strength (3-5% risk per trade)
- **Trade Journaling**: Automatic CSV export of all signals and performance metrics

### Technical Analysis
- RSI divergence detection (proper pivot point identification)
- Volume distribution/accumulation analysis
- Climax top detection
- Failed breakout identification
- Moving average breakdown signals

### Risk Management
- Configurable stop-loss and profit targets
- Position concentration limits (max 20% per trade)
- Multi-position portfolio management
- Liquidity filtering (minimum volume/open interest)

---

## 🚀 Quick Start

### 1. Installation

**Open in Google Colab** (recommended):

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/kevin-mumaw/Options_Strategy_Analyzer_(Version_2_1).ipynb/blob/main/Options_Strategy_Analyzer.ipynb)

**Or install locally:**

```bash
git clone https://github.com/kevin-mumaw/options-strategy-analyzer.git
cd options-strategy-analyzer
pip install -r requirements.txt
