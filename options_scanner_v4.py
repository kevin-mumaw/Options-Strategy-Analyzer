"""
options_scanner_v4.py
=====================
Phase 1 — CALL-side scanner with quality scoring gate.
Aligned with Jason Brown's PTU trading principles.

Design philosophy:
  - Only generate a signal when conviction score >= 6/10
  - If nothing qualifies, say so clearly — no trade is a valid result
  - Every signal includes exact exit prices — no guessing required
  - Risk management is built in, not optional
  - Liquid watchlist of 40 symbols across 4 price tiers
  - Tier 1 ($10-50): affordable single legs
  - Tier 2 ($50-150): sweet spot for $2-5k accounts
  - Tier 3 ($150-400): ATM viable, spreads work well
  - Tier 4 ($400+): spreads preferred

Scoring system (12 points total):
  Regime    0-2  Market direction via QQQ
  RSI       0-2  Momentum positioning
  Trend     0-2  Price structure vs moving averages
  Volume    0-2  Institutional activity
  Weekly    0-1  Multi-timeframe confirmation
  Support   0-1  Entry quality relative to key levels
  MACD      0-1  Momentum confirmation (Jason Brown)
  Bollinger 0-1  Volatility/support context (Jason Brown)

  Score >= 6  → Signal generated
  Score  < 6  → No signal (wait for better setup)

Planned additions (Phase 1 completion):
  MACD      0-1  Momentum confirmation
  Bollinger 0-1  Volatility/support context
  Earnings  flag  Avoid entries within 14 days of earnings
"""

import warnings
warnings.filterwarnings("ignore")

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scipy.stats import norm
from typing import Optional

# ─────────────────────────────────────────────────────────────
# WATCHLIST — 40 names across price tiers with liquid options
#
# Tier 1 ($10-50):   affordable single legs at $2-5k account
# Tier 2 ($50-150):  sweet spot for ITM options at $2-5k account
# Tier 3 ($150-400): ATM viable, spreads preferred
# Tier 4 ($400+):    spreads only at $2-5k account
# ─────────────────────────────────────────────────────────────
WATCHLIST = {
    # Tier 1 — very affordable, high volume ($10-50)
    "tier1_affordable": ["BAC", "F", "PLTR", "T", "PFE", "AAL", "SOFI"],

    # Tier 2 — sweet spot for this account size ($50-150)
    "tier2_sweet_spot": ["XLF", "KO", "DIS", "NKE", "UBER", "AMD", "INTC",
                         "WFC", "C", "MU"],

    # Tier 3 — ATM viable, spreads work well ($150-400)
    "tier3_mid_price":  ["AAPL", "GOOGL", "JPM", "V", "MA", "XOM", "CVX",
                         "UNH", "JNJ", "GS"],

    # Tier 4 — spreads preferred ($400+)
    "tier4_high_price": ["MSFT", "AMZN", "META", "NVDA", "COST", "SPY", "QQQ"],
}

ALL_SYMBOLS = [s for group in WATCHLIST.values() for s in group]

VERSION = "4.23"

# ─────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────
CONFIG = {
    # Account
    "account_size":       2000.00,
    "risk_pct_min":       0.03,        # 3% = $60 on $2k account
    "risk_pct_max":       0.05,        # 5% = $100 on $2k account
    "max_positions":      2,           # max open positions at $2k

    # Signal gate
    "min_score":          6,           # minimum score out of 10
    "max_signals":        5,           # cap output at top 5 signals

    # Technical thresholds
    "rsi_oversold":       35,
    "rsi_overbought":     65,
    "ma_short":           20,
    "ma_long":            50,
    "vol_avg_days":       20,
    "support_proximity":  0.05,        # within 5% of MA50 = near support

    # Regime benchmark
    "regime_symbol":      "QQQ",
    "regime_ma_short":    50,
    "regime_ma_long":     200,

    # Options selection — ITM preference per Jason Brown
    "min_dte":            30,
    "target_dte":         52,         # targets ~July 17 monthly over weeklies like July 2
    "min_delta":          0.55,        # ITM preferred (delta 0.55-0.80)
    "max_delta":          0.80,
    "min_option_volume":  50,
    "min_option_oi":      200,
    "max_spread_pct":     25.0,
    "atm_tolerance":      0.15,        # wider tolerance to find ITM strikes

    # Exit rules — these are fixed, not suggestions
    "stop_loss_pct":      0.35,        # exit if premium drops 35%
    "profit_target_pct":  0.75,        # exit if premium rises 75%
    "time_stop_dte":      21,          # exit when 21 DTE remains
    "min_reward_risk":    2.0,         # minimum reward:risk ratio (1:2, per Jason Brown)
    "earnings_warn_days": 14,          # flag if earnings within 14 days
}


# ─────────────────────────────────────────────────────────────
# TECHNICAL INDICATOR HELPERS
# ─────────────────────────────────────────────────────────────

def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_hv(series: pd.Series, window: int = 30) -> float:
    log_ret = np.log(series / series.shift(1))
    hv = log_ret.rolling(window).std().iloc[-1] * np.sqrt(252) * 100
    return round(float(hv), 1) if not np.isnan(hv) else 0.0


def get_trend(price: float, ma_short: float, ma_long: float) -> str:
    if price > ma_short > ma_long:
        return "UPTREND"
    elif price < ma_short < ma_long:
        return "DOWNTREND"
    return "MIXED"


def safe_float(val, default=None) -> Optional[float]:
    try:
        v = float(val)
        return v if not np.isnan(v) else default
    except (TypeError, ValueError):
        return default


def compute_macd(series: pd.Series,
                 fast: int = 12, slow: int = 26,
                 signal: int = 9) -> dict:
    """
    Compute MACD line, signal line, and histogram.
    Returns dict with macd, signal, histogram, and bullish flag.
    """
    result = {"macd": None, "signal": None, "histogram": None, "bullish": False}
    try:
        if len(series) < slow + signal + 5:
            return result
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line

        m = round(float(macd_line.iloc[-1]), 4)
        s = round(float(signal_line.iloc[-1]), 4)
        h = round(float(histogram.iloc[-1]), 4)

        result.update({
            "macd":      m,
            "signal":    s,
            "histogram": h,
            "bullish":   m > s,   # MACD above signal = bullish momentum
        })
    except Exception:
        pass
    return result


def analyze_bollinger(series: pd.Series,
                      window: int = 20, num_std: float = 2.0) -> dict:
    """
    Compute Bollinger Bands and classify price position.
    Returns dict with upper, middle, lower bands and signal.

    Signals:
      NEAR_LOWER  — price near or below lower band (oversold, potential bounce)
      NEAR_UPPER  — price near or above upper band (overbought, potential reversal)
      MIDDLE      — price between bands (neutral)
    """
    result = {
        "upper": None, "middle": None, "lower": None,
        "pct_b": None, "signal": "UNKNOWN", "bullish": False
    }
    try:
        if len(series) < window + 5:
            return result

        middle = series.rolling(window).mean()
        std    = series.rolling(window).std()
        upper  = middle + (std * num_std)
        lower  = middle - (std * num_std)

        price  = float(series.iloc[-1])
        mid    = float(middle.iloc[-1])
        up     = float(upper.iloc[-1])
        lo     = float(lower.iloc[-1])

        band_width = up - lo
        if band_width > 0:
            pct_b = (price - lo) / band_width  # 0=lower band, 1=upper band
        else:
            pct_b = 0.5

        if pct_b <= 0.20:
            signal  = "NEAR_LOWER"
            bullish = True    # near lower band = oversold bounce opportunity
        elif pct_b >= 0.75:
            signal  = "NEAR_UPPER"
            bullish = False   # near upper band = extended
        else:
            signal  = "MIDDLE"
            bullish = False   # neutral

        result.update({
            "upper":   round(up, 2),
            "middle":  round(mid, 2),
            "lower":   round(lo, 2),
            "pct_b":   round(pct_b, 3),
            "signal":  signal,
            "bullish": bullish,
        })
    except Exception:
        pass
    return result


# ─────────────────────────────────────────────────────────────
# MARKET REGIME
# ─────────────────────────────────────────────────────────────

def analyze_regime(config: dict = CONFIG) -> dict:
    """
    Classify the broad market regime using QQQ vs its 50 and 200-day MAs.
    Returns regime dict with all context needed for display and scoring.
    """
    result = {
        "regime":   "UNKNOWN",
        "symbol":   config["regime_symbol"],
        "price":    None,
        "ma50":     None,
        "ma200":    None,
        "pct_ma50": None,
        "detail":   "Could not fetch regime data",
    }
    try:
        hist  = yf.Ticker(config["regime_symbol"]).history(period="2y")
        if hist.empty or len(hist) < 210:
            return result

        close  = hist["Close"]
        price  = round(float(close.iloc[-1]), 2)
        ma50   = round(float(close.rolling(config["regime_ma_short"]).mean().iloc[-1]), 2)
        ma200  = round(float(close.rolling(config["regime_ma_long"]).mean().iloc[-1]), 2)
        pct50  = round((price - ma50)  / ma50  * 100, 1)
        pct200 = round((price - ma200) / ma200 * 100, 1)

        if price > ma50 > ma200:
            regime = "BULLISH"
        elif price < ma50 < ma200:
            regime = "BEARISH"
        else:
            regime = "MIXED"

        result.update({
            "regime":    regime,
            "price":     price,
            "ma50":      ma50,
            "ma200":     ma200,
            "pct_ma50":  pct50,
            "pct_ma200": pct200,
            "detail":    f"{config['regime_symbol']} {price} | MA50 {ma50} ({pct50:+.1f}%) | MA200 {ma200} ({pct200:+.1f}%)",
        })
    except Exception as e:
        result["detail"] = f"Regime error: {e}"
    return result


# ─────────────────────────────────────────────────────────────
# VOLUME ANALYSIS
# ─────────────────────────────────────────────────────────────

def analyze_volume(close: pd.Series, volume: pd.Series,
                   avg_days: int = 20) -> dict:
    """
    Classify volume behavior over the last 5 bars.
    Returns label and score (0, 1, or 2).
    """
    if len(close) < avg_days + 5:
        return {"label": "UNKNOWN", "score": 1, "detail": "Insufficient data"}

    avg_vol     = volume.rolling(avg_days).mean()
    price_ch    = close.diff()
    recent_n    = 5
    up_days     = price_ch.iloc[-recent_n:] > 0
    down_days   = price_ch.iloc[-recent_n:] < 0
    vol_recent  = volume.iloc[-recent_n:]
    avg_recent  = avg_vol.iloc[-recent_n:]

    up_heavy   = int((up_days   & (vol_recent > avg_recent * 1.3)).sum())
    down_heavy = int((down_days & (vol_recent > avg_recent * 1.3)).sum())

    if up_heavy >= 3:
        return {"label": "ACCUMULATION", "score": 2,
                "detail": f"Accumulation — {up_heavy}/5 up days on heavy volume"}
    elif down_heavy >= 3:
        return {"label": "DISTRIBUTION", "score": 0,
                "detail": f"Distribution — {down_heavy}/5 down days on heavy volume"}
    elif up_heavy >= 2:
        return {"label": "MILD_ACCUMULATION", "score": 1,
                "detail": f"Mild accumulation — {up_heavy}/5 up days on above-avg volume"}
    else:
        return {"label": "NEUTRAL", "score": 1,
                "detail": "Neutral volume — no clear institutional signal"}


# ─────────────────────────────────────────────────────────────
# WEEKLY TIMEFRAME
# ─────────────────────────────────────────────────────────────

def analyze_weekly(ticker: yf.Ticker) -> dict:
    """Fetch weekly data and return trend classification."""
    result = {"trend": "UNKNOWN", "rsi": None, "detail": "No weekly data"}
    try:
        hist = ticker.history(period="2y", interval="1wk")
        if hist.empty or len(hist) < 25:
            return result

        close = hist["Close"]
        price = float(close.iloc[-1])
        ma10  = float(close.rolling(10).mean().iloc[-1])
        ma20  = float(close.rolling(20).mean().iloc[-1])
        rsi   = round(float(compute_rsi(close).iloc[-1]), 1)
        trend = get_trend(price, ma10, ma20)

        result.update({
            "trend":  trend,
            "rsi":    rsi,
            "detail": f"Weekly trend: {trend} | RSI: {rsi}",
        })
    except Exception:
        pass
    return result


# ─────────────────────────────────────────────────────────────
# QUALITY SCORER — the heart of Phase 1
# ─────────────────────────────────────────────────────────────

def score_call_setup(
    regime:        str,
    rsi:           float,
    trend:         str,
    vol_score:     int,
    weekly_trend:  str,
    pct_from_ma50: float,
    close:         pd.Series,
    rsi_series:    pd.Series,
    macd:          dict = None,
    bollinger:     dict = None,
) -> dict:
    """
    Score a potential CALL setup on a 12-point scale.

    Returns:
        score        int 0-12
        breakdown    dict of each component score
        reasons      list of strings explaining what passed/failed
        conviction   str VERY_HIGH / HIGH / MODERATE / NONE
    """
    breakdown = {}
    reasons   = []

    # ── 1. Regime (0-2) ─────────────────────────────────────
    if regime == "BULLISH":
        breakdown["regime"] = 2
        reasons.append("✓ Regime [2/2] BULLISH — QQQ above both MAs")
    elif regime == "MIXED":
        breakdown["regime"] = 1
        reasons.append("~ Regime [1/2] MIXED — QQQ in transitional zone")
    else:
        breakdown["regime"] = 0
        reasons.append("✗ Regime [0/2] BEARISH — market headwind for CALLs")

    # ── 2. RSI (0-2) ────────────────────────────────────────
    # Check if RSI is turning up from oversold (most valuable)
    rsi_prev = safe_float(rsi_series.iloc[-3], 50)
    rsi_turning_up = rsi > rsi_prev if rsi_prev else False

    if rsi < CONFIG["rsi_oversold"] and rsi_turning_up:
        breakdown["rsi"] = 2
        reasons.append(f"✓ RSI     [2/2] Oversold bounce — RSI {rsi:.0f} turning up")
    elif rsi < CONFIG["rsi_oversold"]:
        breakdown["rsi"] = 2
        reasons.append(f"✓ RSI     [2/2] Oversold — RSI {rsi:.0f} (potential reversal)")
    elif rsi < 55 and trend != "DOWNTREND":
        breakdown["rsi"] = 1
        reasons.append(f"~ RSI     [1/2] Neutral — RSI {rsi:.0f} (room to run)")
    elif rsi >= CONFIG["rsi_overbought"]:
        breakdown["rsi"] = 0
        reasons.append(f"✗ RSI     [0/2] Overbought — RSI {rsi:.0f} (chasing)")
    else:
        breakdown["rsi"] = 0
        reasons.append(f"✗ RSI     [0/2] RSI {rsi:.0f} in downtrend — unfavorable")

    # ── 3. Trend (0-2) ──────────────────────────────────────
    if trend == "UPTREND":
        breakdown["trend"] = 2
        reasons.append("✓ Trend   [2/2] Clean uptrend — price > MA20 > MA50")
    elif trend == "MIXED":
        # Partial credit if above MA50
        if pct_from_ma50 > 0:
            breakdown["trend"] = 1
            reasons.append("~ Trend   [1/2] Mixed but above MA50 support")
        else:
            breakdown["trend"] = 0
            reasons.append("✗ Trend   [0/2] Mixed with price below MA50")
    else:
        breakdown["trend"] = 0
        reasons.append("✗ Trend   [0/2] Downtrend — counter-trend CALL")

    # ── 4. Volume (0-2) ─────────────────────────────────────
    breakdown["volume"] = vol_score
    # reason already added by caller

    # ── 5. Weekly alignment (0-1) ───────────────────────────
    if weekly_trend == "UPTREND":
        breakdown["weekly"] = 1
        reasons.append("✓ Weekly  [1/1] Weekly uptrend confirmed")
    elif weekly_trend == "MIXED":
        breakdown["weekly"] = 0
        reasons.append("~ Weekly  [0/1] Weekly trend mixed")
    else:
        breakdown["weekly"] = 0
        reasons.append("✗ Weekly  [0/1] Weekly trend not supportive")

    # ── 6. Support quality (0-1) ────────────────────────────
    near_support  = abs(pct_from_ma50) <= CONFIG["support_proximity"] * 100
    overextended  = pct_from_ma50 > 10.0
    bouncing_up   = near_support and trend != "DOWNTREND"

    if bouncing_up:
        breakdown["support"] = 1
        reasons.append(f"✓ Support [1/1] Near MA50 support ({pct_from_ma50:+.1f}%)")
    elif overextended:
        breakdown["support"] = 0
        reasons.append(f"✗ Support [0/1] Extended {pct_from_ma50:+.1f}% above MA50 — wait for pullback")
    else:
        breakdown["support"] = 0
        reasons.append(f"~ Support [0/1] Not near key support ({pct_from_ma50:+.1f}% from MA50)")

    # ── 7. MACD (0-1) ───────────────────────────────────────
    if macd and macd.get("macd") is not None:
        if macd["bullish"]:
            breakdown["macd"] = 1
            reasons.append(
                f"✓ MACD    [1/1] Bullish — MACD {macd['macd']:.3f} above signal {macd['signal']:.3f}"
            )
        else:
            breakdown["macd"] = 0
            reasons.append(
                f"✗ MACD    [0/1] Bearish — MACD {macd['macd']:.3f} below signal {macd['signal']:.3f}"
            )
    else:
        breakdown["macd"] = 0
        reasons.append("~ MACD    [0/1] Insufficient data")

    # ── 8. Bollinger Bands (0-1) ────────────────────────────
    if bollinger and bollinger.get("signal") != "UNKNOWN":
        if bollinger["bullish"]:
            breakdown["bollinger"] = 1
            reasons.append(
                f"✓ BB      [1/1] Near lower band — oversold bounce (BB% {bollinger['pct_b']:.2f})"
            )
        elif bollinger["signal"] == "NEAR_UPPER":
            breakdown["bollinger"] = 0
            reasons.append(
                f"✗ BB      [0/1] Near upper band — extended (BB% {bollinger['pct_b']:.2f})"
            )
        else:
            breakdown["bollinger"] = 0
            reasons.append(
                f"~ BB      [0/1] Mid-range (BB% {bollinger['pct_b']:.2f})"
            )
    else:
        breakdown["bollinger"] = 0
        reasons.append("~ BB      [0/1] Insufficient data")

    # ── Total ────────────────────────────────────────────────
    total = sum(breakdown.values())

    if total >= 10:
        conviction = "VERY HIGH"
    elif total >= 8:
        conviction = "HIGH"
    elif total >= 6:
        conviction = "MODERATE"
    else:
        conviction = "NONE"

    return {
        "score":      total,
        "breakdown":  breakdown,
        "reasons":    reasons,
        "conviction": conviction,
    }


# ─────────────────────────────────────────────────────────────
# BLACK-SCHOLES GREEKS
# ─────────────────────────────────────────────────────────────

def black_scholes_greeks(option_type: str, S: float, K: float,
                          T: float, r: float, sigma: float) -> dict:
    """Calculate option Greeks using Black-Scholes model."""
    empty = {"delta": np.nan, "gamma": np.nan, "theta": np.nan, "vega": np.nan}
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return empty
    try:
        d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)

        if option_type == "call":
            delta = norm.cdf(d1)
        else:
            delta = -norm.cdf(-d1)

        gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))

        if option_type == "call":
            theta = (-(S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T))
                     - r * K * np.exp(-r * T) * norm.cdf(d2)) / 365
        else:
            theta = (-(S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T))
                     + r * K * np.exp(-r * T) * norm.cdf(-d2)) / 365

        vega = S * norm.pdf(d1) * np.sqrt(T) / 100

        return {
            "delta": round(delta, 3),
            "gamma": round(gamma, 4),
            "theta": round(theta, 3),
            "vega":  round(vega, 3),
        }
    except Exception:
        return empty


# ─────────────────────────────────────────────────────────────
# PUT SCORING
# ─────────────────────────────────────────────────────────────

def score_put_setup(
    regime:        str,
    rsi:           float,
    trend:         str,
    vol_score_bearish: int,
    weekly_trend:  str,
    pct_from_ma50: float,
    close:         pd.Series,
    rsi_series:    pd.Series,
    macd:          dict = None,
    bollinger:     dict = None,
) -> dict:
    """
    Score a potential PUT setup on a 12-point scale.
    Mirror of score_call_setup but with bearish criteria.

    Individual stock override: if score >= 9, signal allowed even in BULLISH regime.
    """
    breakdown = {}
    reasons   = []

    # ── 1. Regime (0-2) ─────────────────────────────────────
    if regime == "BEARISH":
        breakdown["regime"] = 2
        reasons.append("✓ Regime [2/2] BEARISH — market tailwind for PUTs")
    elif regime == "MIXED":
        breakdown["regime"] = 1
        reasons.append("~ Regime [1/2] MIXED — selective PUT entries only")
    else:
        breakdown["regime"] = 0
        reasons.append("~ Regime [0/2] BULLISH — individual stock weakness required")

    # ── 2. RSI (0-2) ────────────────────────────────────────
    rsi_prev = safe_float(rsi_series.iloc[-3], 50)
    rsi_turning_down = rsi < rsi_prev if rsi_prev else False

    if rsi >= CONFIG["rsi_overbought"] and rsi_turning_down:
        breakdown["rsi"] = 2
        reasons.append(f"✓ RSI     [2/2] Overbought rollover — RSI {rsi:.0f} turning down")
    elif rsi >= CONFIG["rsi_overbought"]:
        breakdown["rsi"] = 2
        reasons.append(f"✓ RSI     [2/2] Overbought — RSI {rsi:.0f} (potential reversal)")
    elif rsi > 45 and trend != "UPTREND":
        breakdown["rsi"] = 1
        reasons.append(f"~ RSI     [1/2] Neutral — RSI {rsi:.0f} (room to fall)")
    elif rsi <= CONFIG["rsi_oversold"]:
        breakdown["rsi"] = 0
        reasons.append(f"✗ RSI     [0/2] Oversold — RSI {rsi:.0f} (bounce risk)")
    else:
        breakdown["rsi"] = 0
        reasons.append(f"✗ RSI     [0/2] RSI {rsi:.0f} in uptrend — unfavorable for PUT")

    # ── 3. Trend (0-2) ──────────────────────────────────────
    if trend == "DOWNTREND":
        breakdown["trend"] = 2
        reasons.append("✓ Trend   [2/2] Confirmed downtrend — price < MA20 < MA50")
    elif trend == "MIXED":
        if pct_from_ma50 < 0:
            breakdown["trend"] = 1
            reasons.append("~ Trend   [1/2] Mixed but below MA50 resistance")
        else:
            breakdown["trend"] = 0
            reasons.append("✗ Trend   [0/2] Mixed with price above MA50")
    else:
        breakdown["trend"] = 0
        reasons.append("✗ Trend   [0/2] Uptrend — counter-trend PUT")

    # ── 4. Volume (0-2) ─────────────────────────────────────
    breakdown["volume"] = vol_score_bearish

    # ── 5. Weekly alignment (0-1) ───────────────────────────
    if weekly_trend == "DOWNTREND":
        breakdown["weekly"] = 1
        reasons.append("✓ Weekly  [1/1] Weekly downtrend confirmed")
    elif weekly_trend == "MIXED":
        breakdown["weekly"] = 0
        reasons.append("~ Weekly  [0/1] Weekly trend mixed")
    else:
        breakdown["weekly"] = 0
        reasons.append("✗ Weekly  [0/1] Weekly uptrend — counter-trend PUT")

    # ── 6. Resistance quality (0-1) ─────────────────────────
    near_resistance = abs(pct_from_ma50) <= CONFIG["support_proximity"] * 100
    overextended_down = pct_from_ma50 < -10.0

    if near_resistance and trend != "UPTREND":
        breakdown["resistance"] = 1
        reasons.append(f"✓ Resist  [1/1] Near MA50 resistance ({pct_from_ma50:+.1f}%)")
    elif overextended_down:
        breakdown["resistance"] = 0
        reasons.append(f"✗ Resist  [0/1] Extended {pct_from_ma50:+.1f}% below MA50 — bounce risk")
    else:
        breakdown["resistance"] = 0
        reasons.append(f"~ Resist  [0/1] Not near key resistance ({pct_from_ma50:+.1f}% from MA50)")

    # ── 7. MACD (0-1) ───────────────────────────────────────
    if macd and macd.get("macd") is not None:
        if not macd["bullish"]:
            breakdown["macd"] = 1
            reasons.append(
                f"✓ MACD    [1/1] Bearish — MACD {macd['macd']:.3f} below signal {macd['signal']:.3f}"
            )
        else:
            breakdown["macd"] = 0
            reasons.append(
                f"✗ MACD    [0/1] Bullish — MACD {macd['macd']:.3f} above signal {macd['signal']:.3f}"
            )
    else:
        breakdown["macd"] = 0
        reasons.append("~ MACD    [0/1] Insufficient data")

    # ── 8. Bollinger Bands (0-1) ────────────────────────────
    if bollinger and bollinger.get("signal") != "UNKNOWN":
        if bollinger["signal"] == "NEAR_UPPER":
            breakdown["bollinger"] = 1
            reasons.append(
                f"✓ BB      [1/1] Near upper band — extended (BB% {bollinger['pct_b']:.2f})"
            )
        elif bollinger["bullish"]:
            breakdown["bollinger"] = 0
            reasons.append(
                f"✗ BB      [0/1] Near lower band — oversold, bounce risk (BB% {bollinger['pct_b']:.2f})"
            )
        else:
            breakdown["bollinger"] = 0
            reasons.append(
                f"~ BB      [0/1] Mid-range (BB% {bollinger['pct_b']:.2f})"
            )
    else:
        breakdown["bollinger"] = 0
        reasons.append("~ BB      [0/1] Insufficient data")

    # ── Total ────────────────────────────────────────────────
    total = sum(breakdown.values())

    if total >= 10:
        conviction = "VERY HIGH"
    elif total >= 8:
        conviction = "HIGH"
    elif total >= 6:
        conviction = "MODERATE"
    else:
        conviction = "NONE"

    return {
        "score":      total,
        "breakdown":  breakdown,
        "reasons":    reasons,
        "conviction": conviction,
    }


def find_best_put(ticker: yf.Ticker, stock_price: float,
                  config: dict = CONFIG) -> Optional[dict]:
    """
    Find the best available PUT option meeting liquidity and DTE criteria.
    Adaptive delta range (negative) by stock price:
      Under $100  : delta -0.55 to -0.80 (ITM preferred)
      $100-$300   : delta -0.50 to -0.70
      Over $300   : delta -0.40 to -0.65
    """
    if stock_price < 100:
        min_delta = -0.80
        max_delta = -0.55
    elif stock_price < 300:
        min_delta = -0.70
        max_delta = -0.50
    else:
        min_delta = -0.65
        max_delta = -0.40

    try:
        today       = datetime.today().date()
        expirations = ticker.options

        if not expirations:
            return None

        best_exp = None
        best_dte = None
        for exp in expirations:
            exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
            dte = (exp_date - today).days
            if dte >= config["min_dte"]:
                if best_dte is None or abs(dte - config["target_dte"]) < abs(best_dte - config["target_dte"]):
                    best_exp = exp
                    best_dte = dte
                if dte > 75:
                    break

        if not best_exp:
            return None

        chain = ticker.option_chain(best_exp)
        puts  = chain.puts.copy()

        if puts.empty:
            return None

        puts = puts[
            (puts["bid"]  > 0) &
            (puts["ask"]  > puts["bid"]) &
            (puts["lastPrice"] > 0)
        ].copy()

        puts = puts[
            (puts["volume"].fillna(0)       >= config["min_option_volume"]) |
            (puts["openInterest"].fillna(0) >= config["min_option_oi"])
        ].copy()

        if puts.empty:
            return None

        puts["dist"] = abs(puts["strike"] - stock_price) / stock_price
        puts = puts[puts["dist"] < config["atm_tolerance"]].sort_values("dist")

        if puts.empty:
            return None

        for _, row in puts.iterrows():
            ask        = safe_float(row["ask"])
            bid        = safe_float(row["bid"])
            if ask is None or bid is None or ask == 0:
                continue

            spread_pct = (ask - bid) / ask * 100
            if spread_pct > config["max_spread_pct"]:
                continue

            iv     = safe_float(row.get("impliedVolatility", 0), 0)
            oi     = int(row.get("openInterest", 0) or 0)
            vol    = float(row.get("volume", 0) or 0)
            vol    = int(vol) if not np.isnan(vol) else 0
            strike = float(row["strike"])
            mid    = round((bid + ask) / 2, 2)
            T      = best_dte / 365.0

            greeks = black_scholes_greeks(
                "put", stock_price, strike, T, 0.045, iv if iv > 0 else 0.25
            )

            delta = greeks.get("delta", -0.5)
            if not np.isnan(delta):
                if delta < min_delta or delta > max_delta:
                    continue
            else:
                continue

            return {
                "expiry":     best_exp,
                "dte":        best_dte,
                "strike":     strike,
                "bid":        round(bid, 2),
                "ask":        round(ask, 2),
                "mid":        mid,
                "iv":         round(iv * 100, 1) if iv else None,
                "volume":     vol,
                "oi":         oi,
                "spread_pct": round(spread_pct, 1),
                "delta":      greeks["delta"],
                "gamma":      greeks["gamma"],
                "theta":      greeks["theta"],
                "vega":       greeks["vega"],
                "delta_tier": f"{min_delta:.2f} to {max_delta:.2f}",
            }

    except Exception as e:
        print(f"  [find_best_put error — {type(e).__name__}: {e}]")
    return None


# ─────────────────────────────────────────────────────────────
# CASH SECURED PUT (CSP) SCORING & SELECTION
# ─────────────────────────────────────────────────────────────

def score_csp_setup(
    regime:        str,
    rsi:           float,
    trend:         str,
    vol_score:     int,
    weekly_trend:  str,
    pct_from_ma50: float,
    iv_pct:        float,
    macd:          dict = None,
    bollinger:     dict = None,
) -> dict:
    """
    Score a Cash Secured Put setup on a 10-point scale.

    CSP logic: sell a put below current price and collect premium.
    Best conditions: stock you want to own, near support, elevated IV.

    Scoring:
      Regime    0-2  BULLISH/MIXED favorable, BEARISH unfavorable
      Trend     0-2  Uptrend or near strong support
      RSI       0-2  Neutral to oversold (not overbought — no chasing)
      IV        0-2  Elevated IV = more premium collected
      Support   0-1  Strike can be placed at/below MA50
      MACD      0-1  Bullish or neutral (not aggressively bearish)
    """
    breakdown = {}
    reasons   = []

    # ── 1. Regime (0-2) ─────────────────────────────────────
    if regime == "BULLISH":
        breakdown["regime"] = 2
        reasons.append("✓ Regime [2/2] BULLISH — ideal for selling puts")
    elif regime == "MIXED":
        breakdown["regime"] = 1
        reasons.append("~ Regime [1/2] MIXED — CSP viable with strong support")
    else:
        breakdown["regime"] = 0
        reasons.append("✗ Regime [0/2] BEARISH — avoid selling puts, assignment risk high")

    # ── 2. Trend (0-2) ──────────────────────────────────────
    if trend == "UPTREND":
        breakdown["trend"] = 2
        reasons.append("✓ Trend   [2/2] Uptrend — stock unlikely to breach put strike")
    elif trend == "MIXED" and pct_from_ma50 > -5:
        breakdown["trend"] = 1
        reasons.append("~ Trend   [1/2] Mixed but near MA50 — decent support")
    else:
        breakdown["trend"] = 0
        reasons.append("✗ Trend   [0/2] Downtrend — assignment risk elevated")

    # ── 3. RSI (0-2) ────────────────────────────────────────
    if CONFIG["rsi_oversold"] <= rsi <= 55:
        breakdown["rsi"] = 2
        reasons.append(f"✓ RSI     [2/2] Neutral/oversold — RSI {rsi:.0f} (good entry)")
    elif 55 < rsi < CONFIG["rsi_overbought"]:
        breakdown["rsi"] = 1
        reasons.append(f"~ RSI     [1/2] Slightly elevated — RSI {rsi:.0f}")
    elif rsi >= CONFIG["rsi_overbought"]:
        breakdown["rsi"] = 0
        reasons.append(f"✗ RSI     [0/2] Overbought — RSI {rsi:.0f} (pullback risk)")
    else:
        breakdown["rsi"] = 1
        reasons.append(f"~ RSI     [1/2] Oversold — RSI {rsi:.0f} (bounce likely)")

    # ── 4. IV (0-2) — elevated IV = more premium ────────────
    if iv_pct is not None:
        if iv_pct >= 60:
            breakdown["iv"] = 2
            reasons.append(f"✓ IV      [2/2] Elevated — {iv_pct:.0f}th percentile (rich premium)")
        elif iv_pct >= 40:
            breakdown["iv"] = 1
            reasons.append(f"~ IV      [1/2] Moderate — {iv_pct:.0f}th percentile")
        else:
            breakdown["iv"] = 0
            reasons.append(f"✗ IV      [0/2] Low — {iv_pct:.0f}th percentile (thin premium)")
    else:
        breakdown["iv"] = 1
        reasons.append("~ IV      [1/2] IV data unavailable")

    # ── 5. Support quality (0-1) ────────────────────────────
    # For CSP we want to sell strike at or below MA50
    if pct_from_ma50 >= 0 and pct_from_ma50 <= 8:
        breakdown["support"] = 1
        reasons.append(f"✓ Support [1/1] Near MA50 — strike can be placed at support ({pct_from_ma50:+.1f}%)")
    elif pct_from_ma50 > 8:
        breakdown["support"] = 0
        reasons.append(f"~ Support [0/1] Extended above MA50 (+{pct_from_ma50:.1f}%) — strike far from support")
    else:
        breakdown["support"] = 0
        reasons.append(f"✗ Support [0/1] Below MA50 ({pct_from_ma50:.1f}%) — assignment risk at support")

    # ── 6. MACD (0-1) ───────────────────────────────────────
    if macd and macd.get("macd") is not None:
        if macd["bullish"]:
            breakdown["macd"] = 1
            reasons.append(f"✓ MACD    [1/1] Bullish momentum — favorable for CSP")
        else:
            breakdown["macd"] = 0
            reasons.append(f"✗ MACD    [0/1] Bearish — monitor closely if assigned")
    else:
        breakdown["macd"] = 0
        reasons.append("~ MACD    [0/1] Insufficient data")

    total = sum(breakdown.values())

    if total >= 8:
        conviction = "HIGH"
    elif total >= 6:
        conviction = "MODERATE"
    else:
        conviction = "NONE"

    return {
        "score":      total,
        "breakdown":  breakdown,
        "reasons":    reasons,
        "conviction": conviction,
    }


def find_best_csp(ticker: yf.Ticker, stock_price: float,
                  config: dict = CONFIG) -> Optional[dict]:
    """
    Find the best put to SELL for a cash secured put.
    Targets:
      - Strike at or slightly below MA50 (built-in margin of safety)
      - Delta -0.25 to -0.40 (OTM — collecting premium, not expecting assignment)
      - 30-45 DTE (enough premium, not too much time risk)
      - Sufficient liquidity
    """
    try:
        today       = datetime.today().date()
        expirations = ticker.options

        if not expirations:
            return None

        # For CSP prefer slightly shorter DTE (30-40 days)
        best_exp = None
        best_dte = None
        for exp in expirations:
            exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
            dte = (exp_date - today).days
            if dte >= config["min_dte"]:
                if best_dte is None or abs(dte - 38) < abs(best_dte - 38):
                    best_exp = exp
                    best_dte = dte
                if dte > 75:
                    break

        if not best_exp:
            return None

        chain = ticker.option_chain(best_exp)
        puts  = chain.puts.copy()

        if puts.empty:
            return None

        puts = puts[
            (puts["bid"]  > 0) &
            (puts["ask"]  > puts["bid"]) &
            (puts["lastPrice"] > 0)
        ].copy()

        puts = puts[
            (puts["volume"].fillna(0)       >= config["min_option_volume"]) |
            (puts["openInterest"].fillna(0) >= config["min_option_oi"])
        ].copy()

        if puts.empty:
            return None

        # For CSP: target OTM puts (below current price)
        puts = puts[puts["strike"] < stock_price].copy()
        puts["dist"] = abs(puts["strike"] - stock_price) / stock_price
        puts = puts[puts["dist"] < 0.12].sort_values("dist")

        if puts.empty:
            return None

        T = best_dte / 365.0

        for _, row in puts.iterrows():
            bid    = safe_float(row["bid"])
            ask    = safe_float(row["ask"])
            if bid is None or ask is None or bid <= 0:
                continue

            spread_pct = (ask - bid) / ask * 100
            if spread_pct > config["max_spread_pct"]:
                continue

            iv     = safe_float(row.get("impliedVolatility", 0), 0)
            strike = float(row["strike"])
            oi     = int(row.get("openInterest", 0) or 0)
            vol    = float(row.get("volume", 0) or 0)
            vol    = int(vol) if not np.isnan(vol) else 0
            mid    = round((bid + ask) / 2, 2)

            greeks = black_scholes_greeks(
                "put", stock_price, strike, T, 0.045, iv if iv > 0 else 0.25
            )

            delta = greeks.get("delta", -0.30)
            # CSP: want OTM puts, delta -0.20 to -0.40
            if not np.isnan(delta):
                if delta < -0.45 or delta > -0.15:
                    continue
            else:
                continue

            # Premium must be meaningful — at least $0.30 per contract
            if bid < 0.30:
                continue

            return {
                "expiry":         best_exp,
                "dte":            best_dte,
                "strike":         strike,
                "bid":            round(bid, 2),
                "ask":            round(ask, 2),
                "mid":            mid,
                "iv":             round(iv * 100, 1) if iv else None,
                "volume":         vol,
                "oi":             oi,
                "spread_pct":     round(spread_pct, 1),
                "delta":          greeks["delta"],
                "theta":          greeks["theta"],
                "cash_required":  round(strike * 100, 2),
                "premium_yield":  round(bid / strike * 100, 2),
            }

    except Exception as e:
        print(f"  [find_best_csp error — {type(e).__name__}: {e}]")
    return None


def size_csp(put_bid: float, strike: float,
             config: dict = CONFIG) -> dict:
    """
    Calculate CSP position sizing.
    Cash required = strike × 100 per contract.
    Max contracts limited by available capital.
    """
    account       = config["account_size"]
    cash_required = strike * 100
    premium       = put_bid * 100

    # Don't tie up more than 30% of account in one CSP
    max_by_capital = int((account * 0.30) // cash_required)
    contracts      = max(min(max_by_capital, config["max_positions"]), 0)

    if contracts == 0 and cash_required <= account * 0.50:
        contracts = 1

    total_premium  = round(contracts * premium, 2)
    total_cash     = round(contracts * cash_required, 2)
    pct_of_account = round(total_cash / account * 100, 1)
    breakeven      = round(strike - put_bid, 2)

    return {
        "contracts":      contracts,
        "total_premium":  total_premium,
        "total_cash":     total_cash,
        "pct_of_account": pct_of_account,
        "breakeven":      breakeven,
        "cash_required":  cash_required,
    }


# ─────────────────────────────────────────────────────────────
# OPTIONS CHAIN
# ─────────────────────────────────────────────────────────────

def find_best_call(ticker: yf.Ticker, stock_price: float,
                   config: dict = CONFIG) -> Optional[dict]:
    """
    Find the best available CALL option meeting liquidity and DTE criteria.
    Delta range is adaptive by stock price per Jason Brown's ITM preference:
      Under $100  : delta 0.55-0.80 (ITM preferred)
      $100-$300   : delta 0.50-0.70 (slight ITM bias)
      Over $300   : delta 0.40-0.65 (ATM, best liquidity)
    """
    # Adaptive delta range based on stock price
    if stock_price < 100:
        min_delta = 0.55
        max_delta = 0.80
    elif stock_price < 300:
        min_delta = 0.50
        max_delta = 0.70
    else:
        min_delta = 0.40
        max_delta = 0.65
    try:
        today = datetime.today().date()
        expirations = ticker.options

        if not expirations:
            return None

        # Find best expiry in target DTE window
        best_exp = None
        best_dte = None
        for exp in expirations:
            exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
            dte = (exp_date - today).days
            if dte >= config["min_dte"]:
                if best_dte is None or abs(dte - config["target_dte"]) < abs(best_dte - config["target_dte"]):
                    best_exp = exp
                    best_dte = dte
                if dte > 75:  # don't go too far out
                    break

        if not best_exp:
            return None

        chain  = ticker.option_chain(best_exp)
        calls  = chain.calls.copy()

        if calls.empty:
            return None

        # Filter: basic quality
        calls = calls[
            (calls["bid"]  > 0) &
            (calls["ask"]  > calls["bid"]) &
            (calls["lastPrice"] > 0)
        ].copy()

        # Filter: liquidity
        calls = calls[
            (calls["volume"].fillna(0)       >= config["min_option_volume"]) |
            (calls["openInterest"].fillna(0) >= config["min_option_oi"])
        ].copy()

        if calls.empty:
            return None

        # Filter: near ATM
        calls["dist"] = abs(calls["strike"] - stock_price) / stock_price
        calls = calls[calls["dist"] < config["atm_tolerance"]].sort_values("dist")

        if calls.empty:
            return None

        # Pick best: closest to ATM with reasonable spread
        for _, row in calls.iterrows():
            ask        = safe_float(row["ask"])
            bid        = safe_float(row["bid"])
            if ask is None or bid is None or ask == 0:
                continue

            spread_pct = (ask - bid) / ask * 100
            if spread_pct > config["max_spread_pct"]:
                continue

            iv     = safe_float(row.get("impliedVolatility", 0), 0)
            oi     = int(row.get("openInterest", 0) or 0)
            vol    = float(row.get("volume", 0) or 0)
            vol    = int(vol) if not np.isnan(vol) else 0
            strike = float(row["strike"])
            mid    = round((bid + ask) / 2, 2)
            T      = best_dte / 365.0

            greeks = black_scholes_greeks(
                "call", stock_price, strike, T, 0.045, iv if iv > 0 else 0.25
            )

            # Skip if delta out of range (uses adaptive range set above)
            delta = greeks.get("delta", 0.5)
            if not np.isnan(delta):
                if delta < min_delta or delta > max_delta:
                    continue
            else:
                continue

            return {
                "expiry":     best_exp,
                "dte":        best_dte,
                "strike":     strike,
                "bid":        round(bid, 2),
                "ask":        round(ask, 2),
                "mid":        mid,
                "iv":         round(iv * 100, 1) if iv else None,
                "volume":     vol,
                "oi":         oi,
                "spread_pct": round(spread_pct, 1),
                "delta":      greeks["delta"],
                "gamma":      greeks["gamma"],
                "theta":      greeks["theta"],
                "vega":       greeks["vega"],
                "delta_tier": f"{min_delta:.2f}-{max_delta:.2f}",
            }

    except Exception as e:
        print(f"  [find_best_call error — {type(e).__name__}: {e}]")
    return None


# ─────────────────────────────────────────────────────────────
# POSITION SIZING & EXIT RULES
# ─────────────────────────────────────────────────────────────

def size_position(option_ask: float, score: int,
                  config: dict = CONFIG) -> dict:
    """
    Calculate position size and exact exit prices.
    Returns all numbers needed to manage the trade.
    """
    account   = config["account_size"]

    # Risk percentage scales slightly with score
    if score >= 8:
        risk_pct = config["risk_pct_max"]
    elif score >= 7:
        risk_pct = (config["risk_pct_min"] + config["risk_pct_max"]) / 2
    else:
        risk_pct = config["risk_pct_min"]

    risk_budget    = account * risk_pct
    cost_per_cont  = option_ask * 100
    max_by_risk    = int(risk_budget // cost_per_cont) if cost_per_cont > 0 else 0
    max_by_conc    = int((account * 0.20) // cost_per_cont) if cost_per_cont > 0 else 0
    contracts      = max(min(max_by_risk, max_by_conc, config["max_positions"]), 0)

    # Allow 1 contract if it fits within 2x risk budget (small account reality)
    if contracts == 0 and cost_per_cont <= risk_budget * 2:
        contracts = 1

    total_cost     = contracts * cost_per_cont
    pct_of_account = round(total_cost / account * 100, 1) if account > 0 else 0

    stop_price     = round(option_ask * (1 - config["stop_loss_pct"]),    2)
    target_price   = round(option_ask * (1 + config["profit_target_pct"]), 2)

    return {
        "contracts":      contracts,
        "risk_pct":       round(risk_pct * 100, 1),
        "risk_budget":    round(risk_budget, 2),
        "cost_per_cont":  round(cost_per_cont, 2),
        "total_cost":     round(total_cost, 2),
        "pct_of_account": pct_of_account,
        "stop_price":     stop_price,
        "target_price":   target_price,
    }


# ─────────────────────────────────────────────────────────────
# DEBIT SPREAD SIZING
# ─────────────────────────────────────────────────────────────

def find_spread_call(ticker: yf.Ticker, stock_price: float,
                     long_strike: float, expiry: str, dte: int,
                     config: dict = CONFIG) -> Optional[dict]:
    """
    Find a short call leg to pair with the long call, forming a bull call spread.
    Targets a strike $10-20 above the long strike depending on stock price.
    Returns spread details or None if no suitable short leg found.
    """
    try:
        chain  = ticker.option_chain(expiry)
        calls  = chain.calls.copy()
        if calls.empty:
            return None

        # Use dollar-based width: $10 for stocks <$200, $15 for $200-500, $20 for $500+
        if stock_price < 200:
            target_width = 10
        elif stock_price < 500:
            target_width = 15
        else:
            target_width = 20

        target_short = long_strike + target_width
        otm_calls    = calls[calls["strike"] > long_strike].copy()
        if otm_calls.empty:
            return None

        # Find closest strike to target width
        otm_calls["dist"] = abs(otm_calls["strike"] - target_short)
        otm_calls = otm_calls.sort_values("dist")

        for _, row in otm_calls.head(5).iterrows():
            bid = safe_float(row.get("bid"))
            ask = safe_float(row.get("ask"))
            if bid is None or ask is None or bid <= 0:
                continue

            strike = float(row["strike"])
            T      = dte / 365.0
            iv     = safe_float(row.get("impliedVolatility", 0), 0.25)
            greeks = black_scholes_greeks(
                "call", stock_price, strike, T, 0.045, iv if iv > 0 else 0.25
            )

            return {
                "strike": strike,
                "bid":    round(bid, 2),
                "ask":    round(ask, 2),
                "delta":  greeks["delta"],
                "iv":     round(iv * 100, 1) if iv else None,
                "width":  round(strike - long_strike, 0),
            }
    except Exception:
        pass
    return None


def size_spread(long_ask: float, short_bid: float, long_strike: float,
                short_strike: float, score: int,
                config: dict = CONFIG) -> Optional[dict]:
    """
    Calculate bull call spread position size and exit rules.
    Net debit = long ask - short bid (this is the max loss per contract).
    Max profit = (strike width - net debit) * 100 per contract.
    Uses more generous sizing than naked calls since risk is fully defined.
    """
    net_debit      = round(long_ask - short_bid, 2)
    if net_debit <= 0:
        return None

    strike_width   = short_strike - long_strike
    max_profit_per = round(strike_width - net_debit, 2)
    if max_profit_per <= 0:
        return None

    cost_per_cont  = net_debit * 100
    account        = config["account_size"]

    # Spreads: allow up to 40% of account for 1 contract since max loss is capped
    max_by_conc    = int((account * 0.40) // cost_per_cont) if cost_per_cont > 0 else 0
    contracts      = min(max_by_conc, config["max_positions"])

    # Always allow 1 contract if it fits within 40% of account
    if contracts == 0 and cost_per_cont <= account * 0.40:
        contracts = 1

    if contracts == 0:
        return None

    total_cost     = round(contracts * cost_per_cont, 2)
    pct_of_account = round(total_cost / account * 100, 1)
    max_gain       = round(contracts * max_profit_per * 100, 2)
    reward_risk    = round(max_profit_per / net_debit, 2)

    # Exit rules:
    # Stop: close if spread loses 50% of net debit paid
    # Target: close at 75% of max profit
    stop_price   = round(net_debit * 0.50, 2)
    target_price = round(net_debit + max_profit_per * 0.75, 2)

    return {
        "contracts":      contracts,
        "net_debit":      net_debit,
        "strike_width":   strike_width,
        "cost_per_cont":  cost_per_cont,
        "total_cost":     total_cost,
        "pct_of_account": pct_of_account,
        "max_gain":       max_gain,
        "max_profit_per": max_profit_per,
        "reward_risk":    reward_risk,
        "stop_price":     stop_price,
        "target_price":   target_price,
    }


# ─────────────────────────────────────────────────────────────
# EARNINGS CHECK
# ─────────────────────────────────────────────────────────────

def check_earnings(ticker: yf.Ticker, warn_days: int = 14) -> dict:
    """
    Check if earnings are within warn_days of today.
    ETFs and funds have no earnings — handled silently.
    """
    result = {
        "has_earnings":      False,
        "days_to_earnings":  None,
        "earnings_date":     None,
        "warning":           None,
    }
    try:
        import logging
        # Suppress yfinance 404 errors for ETFs
        yf_logger = logging.getLogger("yfinance")
        prev_level = yf_logger.level
        yf_logger.setLevel(logging.CRITICAL)

        cal = ticker.calendar

        yf_logger.setLevel(prev_level)

        if cal is None:
            return result

        # yfinance returns calendar as dict or DataFrame depending on version
        if isinstance(cal, dict):
            dates = cal.get("Earnings Date", [])
            if not dates:
                return result
            # Take first upcoming date
            today = datetime.today().date()
            for d in dates:
                try:
                    if hasattr(d, "date"):
                        ed = d.date()
                    else:
                        ed = datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
                    days = (ed - today).days
                    if 0 <= days <= warn_days:
                        result.update({
                            "has_earnings":     True,
                            "days_to_earnings": days,
                            "earnings_date":    str(ed),
                            "warning": f"⚠ Earnings in {days} day{'s' if days != 1 else ''} ({ed}) — avoid new entries",
                        })
                        return result
                    elif days > warn_days:
                        # Store for informational display even if outside window
                        result.update({
                            "has_earnings":     False,
                            "days_to_earnings": days,
                            "earnings_date":    str(ed),
                            "warning":          None,
                        })
                        return result
                except Exception:
                    continue

        elif hasattr(cal, "loc"):
            # DataFrame format
            if "Earnings Date" in cal.index:
                raw = cal.loc["Earnings Date"]
                dates = raw.values if hasattr(raw, "values") else [raw]
                today = datetime.today().date()
                for d in dates:
                    try:
                        if hasattr(d, "date"):
                            ed = d.date()
                        else:
                            ed = datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
                        days = (ed - today).days
                        if 0 <= days <= warn_days:
                            result.update({
                                "has_earnings":     True,
                                "days_to_earnings": days,
                                "earnings_date":    str(ed),
                                "warning": f"⚠ Earnings in {days} day{'s' if days != 1 else ''} ({ed}) — avoid new entries",
                            })
                            return result
                        elif days > warn_days:
                            result.update({
                                "has_earnings":     False,
                                "days_to_earnings": days,
                                "earnings_date":    str(ed),
                                "warning":          None,
                            })
                            return result
                    except Exception:
                        continue

    except Exception:
        pass
    return result


# ─────────────────────────────────────────────────────────────
# SINGLE SYMBOL ANALYSIS
# ─────────────────────────────────────────────────────────────

def scan_symbol(symbol: str, regime: dict,
                config: dict = CONFIG) -> Optional[dict]:
    """
    Full analysis pipeline for one symbol.
    Returns a result dict if score >= min_score, otherwise None.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist   = ticker.history(period="1y")

        if hist.empty or len(hist) < 60:
            return {"symbol": symbol, "score": 0, "error": "Insufficient data"}

        close  = hist["Close"]
        volume = hist["Volume"]
        price  = round(float(close.iloc[-1]), 2)

        if price <= 0:
            return {"symbol": symbol, "score": 0, "error": "Invalid price"}

        # Indicators
        rsi_series  = compute_rsi(close)
        rsi         = round(float(rsi_series.iloc[-1]), 1)
        ma_short    = close.rolling(config["ma_short"]).mean()
        ma_long     = close.rolling(config["ma_long"]).mean()
        ma_s        = round(float(ma_short.iloc[-1]), 2)
        ma_l        = round(float(ma_long.iloc[-1]),  2)
        hv          = compute_hv(close)
        trend       = get_trend(price, ma_s, ma_l)
        pct_ma20    = round((price - ma_s) / ma_s * 100, 1)
        pct_ma50    = round((price - ma_l) / ma_l * 100, 1)

        if np.isnan(rsi):
            return {"symbol": symbol, "score": 0, "error": "RSI calculation failed"}

        # Volume analysis
        vol_data  = analyze_volume(close, volume, config["vol_avg_days"])

        # Weekly trend
        weekly    = analyze_weekly(ticker)

        # MACD and Bollinger
        macd_data = compute_macd(close)
        bb_data   = analyze_bollinger(close)

        # Earnings check
        earnings  = check_earnings(ticker, config["earnings_warn_days"])

        # Score CALL setup
        scoring = score_call_setup(
            regime        = regime["regime"],
            rsi           = rsi,
            trend         = trend,
            vol_score     = vol_data["score"],
            weekly_trend  = weekly["trend"],
            pct_from_ma50 = pct_ma50,
            close         = close,
            rsi_series    = rsi_series,
            macd          = macd_data,
            bollinger     = bb_data,
        )

        # Score PUT setup — bearish volume score is inverse of bullish
        bearish_vol_score = 2 - vol_data["score"]  # distribution=2, accumulation=0
        put_scoring = score_put_setup(
            regime             = regime["regime"],
            rsi                = rsi,
            trend              = trend,
            vol_score_bearish  = bearish_vol_score,
            weekly_trend       = weekly["trend"],
            pct_from_ma50      = pct_ma50,
            close              = close,
            rsi_series         = rsi_series,
            macd               = macd_data,
            bollinger          = bb_data,
        )

        # Score CSP setup
        iv_pct = None
        try:
            hv_series = close.pct_change().rolling(30).std() * np.sqrt(252) * 100
            iv_pct = float(round((hv_series < hv_series.iloc[-1]).mean() * 100, 1))
        except Exception:
            pass

        csp_scoring = score_csp_setup(
            regime        = regime["regime"],
            rsi           = rsi,
            trend         = trend,
            vol_score     = vol_data["score"],
            weekly_trend  = weekly["trend"],
            pct_from_ma50 = pct_ma50,
            iv_pct        = iv_pct,
            macd          = macd_data,
            bollinger     = bb_data,
        )

        # Score CSP setup
        csp_scoring = score_csp_setup(
            regime        = regime["regime"],
            rsi           = rsi,
            trend         = trend,
            vol_score     = vol_data["score"],
            weekly_trend  = weekly["trend"],
            pct_from_ma50 = pct_ma50,
            iv_pct        = hv,
            macd          = macd_data,
            bollinger     = bb_data,
        )

        # Add volume reason to scoring reasons
        vol_pts = vol_data["score"]
        scoring["reasons"].insert(
            4,
            f"{'✓' if vol_pts == 2 else ('~' if vol_pts == 1 else '✗')} "
            f"Volume  [{vol_pts}/2] {vol_data['detail']}"
        )

        score      = scoring["score"]
        put_score  = put_scoring["score"]

        # ── Hard disqualifiers for CALLs ──────────────────────
        hard_fail = None
        if rsi >= config["rsi_overbought"] and pct_ma50 > 10.0:
            hard_fail = f"Overbought (RSI {rsi:.0f}) AND extended (+{pct_ma50:.1f}% above MA50) — do not chase"
        elif rsi >= 75:
            hard_fail = f"RSI {rsi:.0f} — severely overbought, wait for pullback"
        elif pct_ma50 > 15.0 and trend == "UPTREND":
            hard_fail = f"+{pct_ma50:.1f}% above MA50 — too extended, wait for reset"
        elif earnings["has_earnings"]:
            hard_fail = earnings["warning"]

        # ── Hard disqualifiers for PUTs ───────────────────────
        put_hard_fail = None
        if rsi <= config["rsi_oversold"]:
            put_hard_fail = f"RSI {rsi:.0f} — oversold, bounce risk for PUT entry"
        elif pct_ma50 < -15.0:
            put_hard_fail = f"{pct_ma50:.1f}% below MA50 — too extended down, bounce risk"
        elif earnings["has_earnings"]:
            put_hard_fail = earnings["warning"]

        # PUT override: allow in BULLISH regime only if score >= 9
        put_regime_block = (regime["regime"] == "BULLISH" and put_score < 9)

        result = {
            "symbol":         symbol,
            "price":          price,
            "rsi":            rsi,
            "trend":          trend,
            "ma20":           ma_s,
            "ma50":           ma_l,
            "pct_ma20":       pct_ma20,
            "pct_ma50":       pct_ma50,
            "hv":             hv,
            "vol_data":       vol_data,
            "weekly":         weekly,
            "macd":           macd_data,
            "bollinger":      bb_data,
            "earnings":       earnings,
            "scoring":        scoring,
            "score":          score,
            "conviction":     scoring["conviction"],
            "hard_fail":      hard_fail,
            "put_scoring":    put_scoring,
            "put_score":      put_score,
            "put_conviction": put_scoring["conviction"],
            "put_hard_fail":  put_hard_fail,
            "put_regime_block": put_regime_block,
            "option":         None,
            "sizing":         None,
            "put_option":     None,
            "put_sizing":     None,
            "found_option":   False,
            "found_put":      False,
            "csp_scoring":    csp_scoring,
            "csp_score":      csp_scoring["score"],
            "csp_conviction": csp_scoring["conviction"],
            "csp_option":     None,
            "csp_sizing":     None,
            "found_csp":      False,
            "error":          None,
        }

        result["found_option"] = False  # tracks if option was found before R/R check

        # Hard fails block signal generation entirely
        if hard_fail:
            pass  # still continue to check PUT
        elif score >= config["min_score"]:
            option = find_best_call(ticker, price, config)
            if option:
                result["found_option"] = True
                sizing = size_position(option["ask"], score, config)
                result["option"] = option
                result["sizing"] = sizing

                if sizing["contracts"] == 0:
                    short_leg = find_spread_call(
                        ticker, price,
                        option["strike"], option["expiry"], option["dte"], config
                    )
                    if short_leg:
                        spread_siz = size_spread(
                            option["ask"], short_leg["bid"],
                            option["strike"], short_leg["strike"],
                            score, config
                        )
                        result["spread"]     = short_leg
                        result["spread_siz"] = spread_siz

                        if spread_siz and spread_siz["reward_risk"] < config["min_reward_risk"]:
                            result["rr_fail"] = spread_siz["reward_risk"]
                            result["option"]  = None
                    else:
                        result["spread"]     = None
                        result["spread_siz"] = None
                else:
                    result["spread"]     = None
                    result["spread_siz"] = None

                    if sizing["contracts"] > 0:
                        target_gain = round(sizing["target_price"] - option["ask"], 2)
                        risk        = round(option["ask"] - sizing["stop_price"], 2)
                        rr          = round(target_gain / risk, 2) if risk > 0 else 0
                        if rr < config["min_reward_risk"]:
                            result["rr_fail"] = rr
                            result["option"]  = None

        # PUT option lookup
        if not put_hard_fail and not put_regime_block and put_score >= config["min_score"]:
            put_option = find_best_put(ticker, price, config)
            if put_option:
                result["found_put"] = True
                put_sizing = size_position(put_option["ask"], put_score, config)
                result["put_option"] = put_option
                result["put_sizing"] = put_sizing

                if put_sizing["contracts"] > 0:
                    target_gain = round(put_sizing["target_price"] - put_option["ask"], 2)
                    risk        = round(put_option["ask"] - put_sizing["stop_price"], 2)
                    rr          = round(target_gain / risk, 2) if risk > 0 else 0
                    if rr < config["min_reward_risk"]:
                        result["put_rr_fail"] = rr
                        result["put_option"]  = None

        # CSP option lookup — only in BULLISH or MIXED regime
        if (not earnings["has_earnings"]
                and csp_scoring["score"] >= config["min_score"]
                and regime["regime"] in ("BULLISH", "MIXED")
                and trend != "DOWNTREND"):
            csp_option = find_best_csp(ticker, price, config)
            if csp_option:
                result["found_csp"] = True
                csp_siz = size_csp(csp_option["bid"], csp_option["strike"], config)
                result["csp_option"] = csp_option
                result["csp_sizing"] = csp_siz

        return result

    except Exception as e:
        return {"symbol": symbol, "score": 0, "error": str(e)}


# ─────────────────────────────────────────────────────────────
# FULL SCAN
# ─────────────────────────────────────────────────────────────

def run_scan(symbols: list = None, config: dict = CONFIG,
             verbose: bool = True) -> dict:
    """
    Run the scanner across a list of symbols.

    Args:
        symbols:  List of tickers. Defaults to ALL_SYMBOLS.
        config:   Configuration dict. Defaults to CONFIG.
        verbose:  Print progress as scanning.

    Returns:
        Dict with signals, near_misses, regime, and scan metadata.
    """
    if symbols is None:
        symbols = ALL_SYMBOLS

    if verbose:
        print(f"\n  Fetching market regime ({config['regime_symbol']})...")

    regime = analyze_regime(config)

    if verbose:
        print(f"  Regime: {regime['regime']} — {regime['detail']}")
        print(f"\n  Scanning {len(symbols)} symbols", end="", flush=True)

    results    = []
    for sym in symbols:
        if verbose:
            print(".", end="", flush=True)
        r = scan_symbol(sym, regime, config)
        if r:
            results.append(r)

    if verbose:
        print(" done.\n")

    # Sort by score descending
    results.sort(key=lambda x: x.get("score", 0), reverse=True)

    # Split results into clear categories
    all_qualified  = [r for r in results
                      if r.get("score", 0) >= config["min_score"]
                      and r.get("option") is not None]

    signals        = all_qualified[:config["max_signals"]]
    also_qualified = [r for r in all_qualified[config["max_signals"]:]
                      if r.get("rsi", 0) < config["rsi_overbought"]][:5]

    # PUT signals
    put_signals    = [r for r in results
                      if r.get("put_score", 0) >= config["min_score"]
                      and r.get("put_option") is not None
                      and not r.get("put_hard_fail")
                      and not r.get("put_regime_block")][:config["max_signals"]]

    # CSP signals — exclude overbought stocks (RSI >= 70 is too risky for selling puts)
    csp_signals    = [r for r in results
                      if r.get("csp_option") is not None
                      and r.get("csp_sizing", {}).get("contracts", 0) > 0
                      and r.get("rsi", 100) < 70
                      and not r.get("earnings", {}).get("has_earnings")][:config["max_signals"]]

    no_option      = [r for r in results
                      if r.get("score", 0) >= config["min_score"]
                      and r.get("option") is None
                      and not r.get("found_option")
                      and not r.get("hard_fail")]

    rr_disqualified = [r for r in results
                       if r.get("score", 0) >= config["min_score"]
                       and r.get("option") is None
                       and r.get("found_option")
                       and not r.get("hard_fail")]

    qualified_syms = set(r["symbol"] for r in all_qualified + no_option)
    near_misses    = [r for r in results
                      if r.get("score", 0) == config["min_score"] - 1
                      and r.get("symbol") not in qualified_syms
                      and not r.get("error")][:5]

    try:
        from datetime import timezone as dt_timezone
        import pytz
        et = pytz.timezone("US/Eastern")
        scan_date = datetime.now(dt_timezone.utc).astimezone(et).strftime("%Y-%m-%d %H:%M ET")
    except Exception:
        scan_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    return {
        "regime":           regime,
        "signals":          signals,
        "put_signals":      put_signals,
        "csp_signals":      csp_signals,
        "also_qualified":   also_qualified,
        "near_misses":      near_misses,
        "no_option":        no_option,
        "rr_disqualified":  rr_disqualified,
        "all_results":      results,
        "scanned":          len(results),
        "scan_date":        scan_date,
        "config":           config,
    }


# ─────────────────────────────────────────────────────────────
# OUTPUT — clean, actionable display
# ─────────────────────────────────────────────────────────────

def print_results(scan: dict):
    """Print scan results in clean, immediately actionable format."""

    regime  = scan["regime"]
    signals = scan["signals"]
    config  = scan["config"]
    W       = 62

    # ── Header ──────────────────────────────────────────────
    print("\n" + "█" * W)
    print(f"  OPTIONS SCANNER — Phase 1  v{VERSION}  |  {scan['scan_date']}")
    print(f"  Account: ${config['account_size']:,.0f}  |  "
          f"Scanned: {scan['scanned']} symbols")
    print("█" * W)

    # ── Regime ──────────────────────────────────────────────
    regime_icons = {"BULLISH": "🟢", "MIXED": "🟡", "BEARISH": "🔴", "UNKNOWN": "⚪"}
    icon = regime_icons.get(regime["regime"], "⚪")
    print(f"\n  MARKET REGIME: {icon} {regime['regime']}")
    print(f"  {regime['detail']}")

    # ── Plain English market read ────────────────────────────
    r_name   = regime["regime"]
    pct_ma50 = regime.get("pct_ma50", 0) or 0

    if r_name == "BULLISH":
        if pct_ma50 > 15:
            summary = "Market significantly extended — wait for pullback before new entries"
        elif pct_ma50 > 10:
            summary = "Market extended above MA50 — proceed only with highest conviction setups"
        elif pct_ma50 > 5:
            summary = "Market healthy and trending — proceed with qualifying setups"
        else:
            summary = "Market near MA50 support — good entry conditions if setups qualify"
    elif r_name == "MIXED":
        summary = "Market transitional — raise the bar, use smaller size, avoid marginal setups"
    elif r_name == "BEARISH":
        summary = "Market in downtrend — avoid new CALL entries, protect capital"
    else:
        summary = "Market direction unclear — wait for confirmation"

    print(f"\n  📋 {summary}")

    # ── No signals ──────────────────────────────────────────
    if not signals:
        print(f"\n{'─' * W}")
        print("  NO QUALIFYING SETUPS TODAY")
        print("  Recommendation: Wait. Do not force a trade.")

        # Show best scores anyway
        top = [r for r in scan["all_results"] if not r.get("error")][:5]
        if top:
            print(f"\n  Best scores today:")
            for r in top:
                rr_note = f"  ⚠ R/R {r['rr_fail']:.1f}x < {config['min_reward_risk']}x" \
                          if r.get("rr_fail") else ""
                print(f"    {r['symbol']:6s}  {r['score']}/10  "
                      f"Trend: {r.get('trend','—'):<10}  "
                      f"RSI: {r.get('rsi','—')}{rr_note}")

        # Hard fail symbols — scored well but disqualified
        hard_fails = [r for r in scan["all_results"]
                      if r.get("hard_fail")
                      and r.get("score", 0) >= config["min_score"]
                      and not r.get("error")][:5]
        if hard_fails:
            print(f"\n  Disqualified (do not chase):")
            for r in hard_fails:
                print(f"    {r['symbol']:6s}  {r['score']}/10 — {r['hard_fail']}")

        rr_fails = [r for r in scan["all_results"]
                    if r.get("rr_fail") and not r.get("error")]
        if rr_fails:
            print(f"\n  Scored well but failed 1:{config['min_reward_risk']:.0f} reward/risk:")
            for r in rr_fails[:5]:
                print(f"    {r['symbol']:6s}  {r['score']}/10  "
                      f"R/R: {r['rr_fail']:.1f}x — "
                      f"wait for better entry or lower IV")

        if scan["no_option"]:
            print(f"\n  Qualified but no liquid options:")
            for r in scan["no_option"]:
                print(f"    {r['symbol']:6s}  {r['score']}/10 — no qualifying option")

        print(f"\n{'─' * W}\n")
        return

    # ── Signals ─────────────────────────────────────────────
    print(f"\n  {len(signals)} signal(s) found:\n")

    for i, r in enumerate(signals, 1):
        sym      = r["symbol"]
        score    = r["score"]
        conv     = r["conviction"]
        opt      = r["option"]
        siz      = r["sizing"]
        scoring  = r["scoring"]

        print(f"{'━' * W}")
        print(f"  SIGNAL #{i}  |  {sym} — BUY CALL  |  "
              f"Score: {score}/10  [{conv}]")
        print(f"{'━' * W}")

        # Score breakdown
        print(f"\n  WHY THIS TRADE:")
        for reason in scoring["reasons"]:
            print(f"    {reason}")

        # Stock snapshot
        print(f"\n  STOCK:")
        print(f"    Price: ${r['price']:.2f}   RSI: {r['rsi']:.0f}   "
              f"Trend: {r['trend']}")
        print(f"    MA20:  ${r['ma20']:.2f} ({r['pct_ma20']:+.1f}%)   "
              f"MA50: ${r['ma50']:.2f} ({r['pct_ma50']:+.1f}%)")
        print(f"    HV30:  {r['hv']}%   "
              f"Weekly: {r['weekly']['trend']}")

        # Earnings info
        earn = r.get("earnings", {})
        if earn.get("earnings_date"):
            days = earn.get("days_to_earnings")
            ed   = earn.get("earnings_date")
            if earn.get("has_earnings"):
                print(f"    ⚠ EARNINGS: {ed} ({days} days) — signal blocked by hard filter")
            else:
                print(f"    Earnings:  {ed} ({days} days away — outside {config['earnings_warn_days']}-day window)")

        # Option
        print(f"\n  OPTION:")
        print(f"    {opt['expiry']} ${opt['strike']:.0f} CALL  |  "
              f"{opt['dte']} DTE")
        print(f"    Bid: ${opt['bid']:.2f}  Ask: ${opt['ask']:.2f}  "
              f"Mid: ${opt['mid']:.2f}  Spread: {opt['spread_pct']:.1f}%")

        iv_str = f"{opt['iv']}%" if opt['iv'] else "N/A"
        print(f"    IV: {iv_str}  |  Delta: {opt['delta']}  |  "
              f"Theta: ${opt['theta']*100:.2f}/day  |  "
              f"Vol: {opt['volume']}  OI: {opt['oi']}")

        # Position sizing
        spr      = r.get("spread")
        spr_siz  = r.get("spread_siz")

        print(f"\n  POSITION (${config['account_size']:,.0f} account):")
        if siz and siz["contracts"] > 0:
            # Single leg fits
            print(f"    Type      : Single leg CALL")
            print(f"    Contracts : {siz['contracts']}")
            print(f"    Cost      : ${siz['total_cost']:,.0f}  "
                  f"({siz['pct_of_account']}% of account)")
            # Single leg: target is min_reward_risk per Jason Brown
            target_gain = round(siz['target_price'] - opt['ask'], 2)
            rr = round(target_gain / (opt['ask'] - siz['stop_price']), 2)
            print(f"    Reward/Risk: {rr:.1f}x  "
                  f"(risking ${opt['ask'] - siz['stop_price']:.2f} "
                  f"to make ${target_gain:.2f})")
            if rr < config["min_reward_risk"]:
                print(f"    ⚠  Below {config['min_reward_risk']:.1f}x target — "
                      f"consider tighter stop or higher target")
            if siz["pct_of_account"] > 20:
                print(f"    ⚠  Large allocation — only if no other positions open")
        elif spr and spr_siz and spr_siz["contracts"] > 0:
            # Suggest bull call spread
            print(f"    Type       : Bull Call Spread  "
                  f"(${spr_siz['strike_width']:.0f} wide)")
            print(f"    Buy  : ${opt['strike']:.0f} CALL @ ${opt['ask']:.2f}  (ask)")
            print(f"    Sell : ${spr['strike']:.0f} CALL @ ${spr['bid']:.2f}  (bid)")
            print(f"    Net debit  : ${spr_siz['net_debit']:.2f}/contract  "
                  f"(max loss per contract)")
            print(f"    Contracts  : {spr_siz['contracts']}")
            print(f"    Total cost : ${spr_siz['total_cost']:,.0f}  "
                  f"({spr_siz['pct_of_account']}% of account)")
            print(f"    Max gain   : ${spr_siz['max_gain']:,.0f}  "
                  f"| Reward/Risk: {spr_siz['reward_risk']:.1f}x")
            if spr_siz["reward_risk"] < config["min_reward_risk"]:
                print(f"    ⚠  Poor reward/risk ({spr_siz['reward_risk']:.1f}x) — "
                      f"target is {config['min_reward_risk']:.1f}x minimum.")
                print(f"       Consider skipping or waiting for a better setup.")
        else:
            print(f"    ⚠  Premium too high even for a spread at this account size.")
            print(f"    Skip this trade or wait until account grows.")

        # Exit rules
        time_stop_date = (
            datetime.strptime(opt["expiry"], "%Y-%m-%d")
            - timedelta(days=config["time_stop_dte"])
        ).strftime("%b %d")

        print(f"\n  EXIT RULES — follow these exactly:")
        if siz and siz["contracts"] > 0:
            print(f"    ┌─ Stop loss     : Sell if premium drops to "
                  f"${siz['stop_price']:.2f}  "
                  f"(-{int(config['stop_loss_pct']*100)}%)")
            print(f"    ├─ Profit target : Sell if premium reaches "
                  f"${siz['target_price']:.2f}  "
                  f"(+{int(config['profit_target_pct']*100)}%)")
            print(f"    └─ Time stop     : Exit by {time_stop_date} "
                  f"({config['time_stop_dte']} DTE remaining)")
            print(f"\n  ⚠  STOP ORDER — Robinhood: use STOP LIMIT (not limit sell)")
            print(f"     Stop price : ${siz['stop_price']:.2f}")
            print(f"     Limit price: ${round(siz['stop_price'] * 0.95, 2):.2f}  (5% below stop)")
        elif spr and spr_siz and spr_siz["contracts"] > 0:
            print(f"    ┌─ Stop loss     : Close spread if value drops to "
                  f"${spr_siz['stop_price']:.2f}  (-50% of debit)")
            print(f"    ├─ Profit target : Close spread if value reaches "
                  f"${spr_siz['target_price']:.2f}  (+75% of max profit)")
            print(f"    └─ Time stop     : Close by {time_stop_date} "
                  f"({config['time_stop_dte']} DTE remaining)")
        else:
            print(f"    (No position — skip this trade)")

        print()

    # ── Hard fails ───────────────────────────────────────────
    hard_fails = [r for r in scan["all_results"]
                  if r.get("hard_fail")
                  and r.get("score", 0) >= config["min_score"]
                  and not r.get("error")][:5]
    if hard_fails:
        print(f"{'─' * W}")
        print(f"  DISQUALIFIED — do not chase:")
        for r in hard_fails:
            print(f"    {r['symbol']:6s}  {r['score']}/10 — {r['hard_fail']}")

    # ── Also qualified (cut off by signal cap) ──────────────
    if scan.get("also_qualified"):
        print(f"{'─' * W}")
        print(f"  ALSO QUALIFIED (scored {config['min_score']}+/10 — "
              f"cut off by {config['max_signals']}-signal cap):")
        for r in scan["also_qualified"]:
            opt = r.get("option")
            opt_str = f"${opt['strike']:.0f} {opt['expiry']} ask ${opt['ask']:.2f}" \
                      if opt else "no option"
            print(f"    {r['symbol']:6s}  {r['score']}/10  "
                  f"Trend: {r.get('trend','—'):<10}  "
                  f"RSI: {r.get('rsi','—'):<6}  {opt_str}")

    # ── Near misses ─────────────────────────────────────────
    if scan["near_misses"]:
        print(f"{'─' * W}")
        print(f"  NEAR MISSES (score {config['min_score']-1}/10 — "
              f"one more factor could qualify):")
        for r in scan["near_misses"]:
            print(f"    {r['symbol']:6s}  {r['score']}/10  "
                  f"Trend: {r.get('trend','—'):<10}  "
                  f"RSI: {r.get('rsi', '—')}")

    # ── R/R disqualified — found option but failed 1:2 ──────
    if scan.get("rr_disqualified"):
        print(f"{'─' * W}")
        rr_disp = scan["rr_disqualified"][:5]
        more    = len(scan["rr_disqualified"]) - 5
        print(f"  OPTION FOUND — FAILED {config['min_reward_risk']:.0f}:1 REWARD/RISK"
              f"{f' (+ {more} more)' if more > 0 else ''}:")
        for r in rr_disp:
            rr = r.get("rr_fail", "?")
            print(f"    {r['symbol']:6s}  {r['score']}/10  "
                  f"R/R: {rr:.1f}x — wait for pullback or lower IV")

    # ── Signals that scored but had no liquid option ─────────
    if scan["no_option"]:
        print(f"{'─' * W}")
        no_opt_display = scan["no_option"][:5]
        more = len(scan["no_option"]) - 5
        print(f"  NO QUALIFYING OPTION FOUND"
              f"{f' (+ {more} more)' if more > 0 else ''}:")
        for r in no_opt_display:
            print(f"    {r['symbol']:6s}  {r['score']}/10 — "
                  f"no option met delta/liquidity requirements")

    # ── PUT Signals ─────────────────────────────────────────
    put_signals = scan.get("put_signals", [])
    if put_signals:
        print(f"\n{'━' * W}")
        print(f"  PUT SIGNALS — {len(put_signals)} signal(s) found")
        print(f"{'━' * W}")

        for i, r in enumerate(put_signals, 1):
            sym      = r["symbol"]
            score    = r["put_score"]
            conv     = r["put_conviction"]
            opt      = r["put_option"]
            siz      = r["put_sizing"]
            scoring  = r["put_scoring"]
            regime   = scan["regime"]["regime"]

            print(f"\n{'━' * W}")
            override = " ⚡ INDIVIDUAL STOCK SIGNAL" if regime == "BULLISH" else ""
            print(f"  PUT #{i}  |  {sym} — BUY PUT  |  "
                  f"Score: {score}/12  [{conv}]{override}")
            print(f"{'━' * W}")

            print(f"\n  WHY THIS TRADE:")
            for reason in scoring["reasons"]:
                print(f"    {reason}")

            print(f"\n  STOCK:")
            print(f"    Price: ${r['price']:.2f}   RSI: {r['rsi']:.0f}   "
                  f"Trend: {r['trend']}")
            print(f"    MA20:  ${r['ma20']:.2f} ({r['pct_ma20']:+.1f}%)   "
                  f"MA50: ${r['ma50']:.2f} ({r['pct_ma50']:+.1f}%)")
            print(f"    HV30:  {r['hv']}%   Weekly: {r['weekly']['trend']}")

            earn = r.get("earnings", {})
            if earn.get("earnings_date"):
                days = earn.get("days_to_earnings")
                ed   = earn.get("earnings_date")
                print(f"    Earnings: {ed} ({days} days away)")

            print(f"\n  OPTION:")
            print(f"    {opt['expiry']} ${opt['strike']:.0f} PUT  |  {opt['dte']} DTE")
            print(f"    Bid: ${opt['bid']:.2f}  Ask: ${opt['ask']:.2f}  "
                  f"Mid: ${opt['mid']:.2f}  Spread: {opt['spread_pct']:.1f}%")
            iv_str = f"{opt['iv']}%" if opt['iv'] else "N/A"
            print(f"    IV: {iv_str}  |  Delta: {opt['delta']}  |  "
                  f"Theta: ${opt['theta']*100:.2f}/day  |  "
                  f"Vol: {opt['volume']}  OI: {opt['oi']}")

            print(f"\n  POSITION (${config['account_size']:,.0f} account):")
            if siz and siz["contracts"] > 0:
                target_gain = round(siz["target_price"] - opt["ask"], 2)
                risk        = round(opt["ask"] - siz["stop_price"], 2)
                rr          = round(target_gain / risk, 2) if risk > 0 else 0
                print(f"    Type      : Single leg PUT")
                print(f"    Contracts : {siz['contracts']}")
                print(f"    Cost      : ${siz['total_cost']:,.0f}  "
                      f"({siz['pct_of_account']}% of account)")
                print(f"    Reward/Risk: {rr:.1f}x")
            else:
                print(f"    ⚠ Premium too high for account size")

            time_stop_date = (
                datetime.strptime(opt["expiry"], "%Y-%m-%d")
                - timedelta(days=config["time_stop_dte"])
            ).strftime("%b %d")

            print(f"\n  EXIT RULES — follow these exactly:")
            if siz and siz["contracts"] > 0:
                print(f"    ┌─ Stop loss     : Sell if premium drops to "
                      f"${siz['stop_price']:.2f}  "
                      f"(-{int(config['stop_loss_pct']*100)}%)")
                print(f"    ├─ Profit target : Sell if premium reaches "
                      f"${siz['target_price']:.2f}  "
                      f"(+{int(config['profit_target_pct']*100)}%)")
                print(f"    └─ Time stop     : Exit by {time_stop_date} "
                      f"({config['time_stop_dte']} DTE remaining)")
                print(f"\n  ⚠  STOP ORDER — Robinhood: use STOP LIMIT (not limit sell)")
                print(f"     Stop price : ${siz['stop_price']:.2f}")
                print(f"     Limit price: ${round(siz['stop_price'] * 0.95, 2):.2f}  (5% below stop)")

    # ── CSP Signals ─────────────────────────────────────────
    csp_signals = scan.get("csp_signals", [])
    if csp_signals:
        print(f"\n{'━' * W}")
        print(f"  CASH SECURED PUT SIGNALS — {len(csp_signals)} signal(s)  "
              f"| Execute on thinkorswim")
        print(f"{'━' * W}")

        for i, r in enumerate(csp_signals, 1):
            sym     = r["symbol"]
            opt     = r["csp_option"]
            siz     = r["csp_sizing"]
            scoring = r["csp_scoring"]
            score   = r["csp_score"]
            conv    = r["csp_conviction"]

            print(f"\n{'━' * W}")
            print(f"  CSP #{i}  |  {sym} — SELL PUT  |  "
                  f"Score: {score}/10  [{conv}]")
            print(f"{'━' * W}")

            print(f"\n  WHY THIS TRADE:")
            for reason in scoring["reasons"]:
                print(f"    {reason}")

            print(f"\n  STOCK:")
            print(f"    Price: ${r['price']:.2f}   RSI: {r['rsi']:.0f}   "
                  f"Trend: {r['trend']}")
            print(f"    MA20:  ${r['ma20']:.2f} ({r['pct_ma20']:+.1f}%)   "
                  f"MA50: ${r['ma50']:.2f} ({r['pct_ma50']:+.1f}%)")

            earn = r.get("earnings", {})
            if earn.get("earnings_date"):
                print(f"    Earnings: {earn['earnings_date']} "
                      f"({earn['days_to_earnings']} days away)")

            print(f"\n  OPTION (SELL THIS PUT):")
            print(f"    {opt['expiry']} ${opt['strike']:.0f} PUT  |  "
                  f"{opt['dte']} DTE")
            print(f"    Bid: ${opt['bid']:.2f}  Ask: ${opt['ask']:.2f}  "
                  f"Spread: {opt['spread_pct']:.1f}%")
            iv_str = f"{opt['iv']}%" if opt['iv'] else "N/A"
            print(f"    IV: {iv_str}  |  Delta: {opt['delta']}  |  "
                  f"Theta: ${opt['theta']*100:.2f}/day")
            print(f"    Premium yield: {opt['premium_yield']:.2f}% of strike")

            print(f"\n  POSITION (${config['account_size']:,.0f} account):")
            print(f"    Contracts      : {siz['contracts']}")
            print(f"    Premium collect: ${siz['total_premium']:,.0f}  "
                  f"(received upfront)")
            print(f"    Cash required  : ${siz['total_cash']:,.0f}  "
                  f"({siz['pct_of_account']}% of account)")
            print(f"    Breakeven      : ${siz['breakeven']:.2f}  "
                  f"(stock must stay above this)")

            print(f"\n  OUTCOMES:")
            print(f"    ✓ Stock above ${opt['strike']:.0f} at expiry → "
                  f"keep ${siz['total_premium']:,.0f} premium, done")
            print(f"    ✗ Stock below ${opt['strike']:.0f} at expiry → "
                  f"assigned, buy 100 shares at ${opt['strike']:.0f}")
            print(f"      Effective cost basis: ${siz['breakeven']:.2f}/share")

            print(f"\n  EXIT OPTIONS (before expiry):")
            print(f"    Buy back at 50% profit : "
                  f"${round(opt['bid'] * 0.50, 2):.2f}  (50% of premium collected)")
            print(f"    Buy back to cut loss   : "
                  f"${round(opt['bid'] * 2.0, 2):.2f}  (2× premium = max loss rule)")
            print(f"\n  ⚠  Execute on thinkorswim — requires margin approval")
            print()

    # ── Footer ──────────────────────────────────────────────
    print(f"{'─' * W}")
    total_signals = len(signals) + len(put_signals) + len(csp_signals)
    print(f"  SCAN COMPLETE  |  {len(signals)} CALL + {len(put_signals)} PUT + "
          f"{len(csp_signals)} CSP signal(s)  |  "
          f"{scan['scanned']} symbols scanned")
    print(f"  Remember: No trade is always a valid choice.\n")


# ─────────────────────────────────────────────────────────────
# QUICK DEEP DIVE — single symbol detail
# ─────────────────────────────────────────────────────────────

def deep_dive(symbol: str, config: dict = CONFIG):
    """Run and print full analysis for a single symbol."""
    print(f"\n  Fetching regime and analyzing {symbol}...")
    regime = analyze_regime(config)
    result = scan_symbol(symbol, regime, config)
    if result:
        scan = {
            "regime":      regime,
            "signals":     [result] if result.get("option") else [],
            "near_misses": [],
            "no_option":   [result] if result.get("score", 0) >= config["min_score"]
                           and not result.get("option") else [],
            "all_results": [result],
            "scanned":     1,
            "scan_date":   datetime.now().strftime("%Y-%m-%d %H:%M"),
            "config":      config,
        }
        print_results(scan)
    else:
        print(f"  Could not analyze {symbol}")


# ─────────────────────────────────────────────────────────────
# TRADE JOURNAL
# ─────────────────────────────────────────────────────────────

JOURNAL_FILE = "trade_journal.csv"

JOURNAL_COLUMNS = [
    "trade_id", "entry_date", "symbol", "direction", "trade_type",
    "score", "conviction", "market_regime",
    "entry_premium", "stop_price", "target_price", "time_stop_date",
    "contracts", "total_cost",
    "exit_date", "exit_premium", "exit_reason",
    "pnl_dollars", "pnl_pct", "status", "notes"
]


def log_entry(symbol: str, direction: str, trade_type: str,
              score: int, conviction: str, market_regime: str,
              entry_premium: float, stop_price: float,
              target_price: float, time_stop_date: str,
              contracts: int, total_cost: float,
              notes: str = "", config: dict = CONFIG) -> str:
    """
    Log a new trade entry to the journal.

    Args:
        symbol:          Ticker e.g. 'BAC'
        direction:       'BUY CALL' or 'BUY PUT'
        trade_type:      'SINGLE LEG' or 'SPREAD'
        score:           Scanner score at entry (e.g. 7)
        conviction:      'MODERATE', 'HIGH', 'VERY HIGH'
        market_regime:   'BULLISH', 'MIXED', 'BEARISH'
        entry_premium:   Premium paid per contract (e.g. 3.35)
        stop_price:      Stop loss price (e.g. 2.18)
        target_price:    Profit target price (e.g. 5.86)
        time_stop_date:  Date to exit regardless (e.g. '2026-06-26')
        contracts:       Number of contracts
        total_cost:      Total dollars spent
        notes:           Any additional notes

    Returns:
        trade_id string
    """
    import os, csv
    from datetime import timezone as dt_timezone

    try:
        import pytz
        et = pytz.timezone("US/Eastern")
        entry_date = datetime.now(dt_timezone.utc).astimezone(et).strftime("%Y-%m-%d %H:%M ET")
    except Exception:
        entry_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    trade_id = f"{symbol}-{datetime.now().strftime('%Y%m%d%H%M')}"

    row = {
        "trade_id":        trade_id,
        "entry_date":      entry_date,
        "symbol":          symbol.upper(),
        "direction":       direction,
        "trade_type":      trade_type,
        "score":           score,
        "conviction":      conviction,
        "market_regime":   market_regime,
        "entry_premium":   entry_premium,
        "stop_price":      stop_price,
        "target_price":    target_price,
        "time_stop_date":  time_stop_date,
        "contracts":       contracts,
        "total_cost":      total_cost,
        "exit_date":       "",
        "exit_premium":    "",
        "exit_reason":     "",
        "pnl_dollars":     "",
        "pnl_pct":         "",
        "status":          "OPEN",
        "notes":           notes,
    }

    file_exists = os.path.isfile(JOURNAL_FILE)
    with open(JOURNAL_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=JOURNAL_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    print(f"\n  ✓ Trade logged: {trade_id}")
    print(f"    {symbol} {direction} | Entry: ${entry_premium:.2f} | "
          f"Stop: ${stop_price:.2f} | Target: ${target_price:.2f}")
    print(f"    Contracts: {contracts} | Cost: ${total_cost:.0f} | "
          f"Time stop: {time_stop_date}")
    return trade_id


def log_exit(trade_id: str, exit_premium: float,
             exit_reason: str, notes: str = "") -> None:
    """
    Update an open trade with exit details and calculate P&L.

    Args:
        trade_id:      The ID returned by log_entry (e.g. 'BAC-202605270945')
        exit_premium:  Premium received when closing (e.g. 5.20)
        exit_reason:   'STOP LOSS', 'PROFIT TARGET', 'TIME STOP', 'MANUAL'
        notes:         Any notes about the exit
    """
    import os, csv
    from datetime import timezone as dt_timezone

    if not os.path.isfile(JOURNAL_FILE):
        print("  ⚠ No journal file found.")
        return

    try:
        import pytz
        et = pytz.timezone("US/Eastern")
        exit_date = datetime.now(dt_timezone.utc).astimezone(et).strftime("%Y-%m-%d %H:%M ET")
    except Exception:
        exit_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    rows = []
    updated = False

    with open(JOURNAL_FILE, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["trade_id"] == trade_id and row["status"] == "OPEN":
                entry_premium = float(row["entry_premium"])
                contracts     = int(row["contracts"])
                pnl_per_cont  = (exit_premium - entry_premium) * 100
                pnl_dollars   = round(pnl_per_cont * contracts, 2)
                pnl_pct       = round((exit_premium - entry_premium) / entry_premium * 100, 1)
                outcome       = "WIN" if pnl_dollars > 0 else "LOSS"

                row["exit_date"]    = exit_date
                row["exit_premium"] = exit_premium
                row["exit_reason"]  = exit_reason
                row["pnl_dollars"]  = pnl_dollars
                row["pnl_pct"]      = pnl_pct
                row["status"]       = outcome
                row["notes"]        = notes if notes else row["notes"]
                updated = True

                print(f"\n  ✓ Trade closed: {trade_id}")
                print(f"    Exit: ${exit_premium:.2f} | Reason: {exit_reason}")
                print(f"    P&L: ${pnl_dollars:+.2f} ({pnl_pct:+.1f}%) — {outcome}")

            rows.append(row)

    if not updated:
        print(f"  ⚠ Trade ID '{trade_id}' not found or already closed.")
        return

    with open(JOURNAL_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=JOURNAL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def show_journal(status: str = "ALL") -> None:
    """
    Display trade journal. status: 'ALL', 'OPEN', 'WIN', 'LOSS'
    """
    import os, csv

    if not os.path.isfile(JOURNAL_FILE):
        print("  No trades logged yet.")
        return

    rows = []
    with open(JOURNAL_FILE, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if status == "ALL" or row["status"] == status:
                rows.append(row)

    if not rows:
        print(f"  No {status.lower()} trades found.")
        return

    W = 62
    print(f"\n{'─' * W}")
    print(f"  TRADE JOURNAL  |  {len(rows)} trade(s)  |  Filter: {status}")
    print(f"{'─' * W}")

    wins   = sum(1 for r in rows if r["status"] == "WIN")
    losses = sum(1 for r in rows if r["status"] == "LOSS")
    open_t = sum(1 for r in rows if r["status"] == "OPEN")
    closed = [r for r in rows if r["status"] in ("WIN", "LOSS")]

    total_pnl = sum(float(r["pnl_dollars"]) for r in closed if r["pnl_dollars"])
    win_rate  = round(wins / len(closed) * 100, 1) if closed else 0

    print(f"  Open: {open_t}  |  Wins: {wins}  |  Losses: {losses}  |  "
          f"Win rate: {win_rate}%  |  Total P&L: ${total_pnl:+.2f}")
    print(f"{'─' * W}")

    for r in rows:
        status_icon = {"OPEN": "🔵", "WIN": "🟢", "LOSS": "🔴"}.get(r["status"], "⚪")
        pnl_str = f"  P&L: ${float(r['pnl_dollars']):+.2f}" if r["pnl_dollars"] else ""
        print(f"\n  {status_icon} {r['trade_id']}")
        print(f"    {r['symbol']} {r['direction']} | Score: {r['score']}/12 | "
              f"{r['conviction']}")
        print(f"    Entry: ${r['entry_premium']} × {r['contracts']} contracts "
              f"= ${r['total_cost']} | {r['entry_date']}")
        if r["exit_date"]:
            print(f"    Exit:  ${r['exit_premium']} | {r['exit_reason']} | "
                  f"{r['exit_date']}{pnl_str}")
        else:
            print(f"    Stop: ${r['stop_price']} | Target: ${r['target_price']} | "
                  f"Time stop: {r['time_stop_date']}")
        if r["notes"]:
            print(f"    Notes: {r['notes']}")

    print(f"\n{'─' * W}\n")



# ─────────────────────────────────────────────────────────────
# BACKTESTER — v4 scoring system
# ─────────────────────────────────────────────────────────────

def run_backtest(
    symbols:    list  = None,
    start_date: str   = "2023-01-01",
    end_date:   str   = "2024-12-31",
    min_score:  int   = 6,
    hold_days:  int   = 17,
    stop_pct:   float = 0.35,
    target_pct: float = 0.75,
    slippage:   float = 0.05,
    config:     dict  = CONFIG,
    verbose:    bool  = True,
) -> pd.DataFrame:
    """
    Backtest the v4 CALL scoring system on historical data.

    Simulates trades using stock price moves and estimated delta.
    No actual historical options prices — uses simplified P&L model.

    Args:
        symbols:    List of tickers. Defaults to ALL_SYMBOLS.
        start_date: Backtest start (YYYY-MM-DD)
        end_date:   Backtest end (YYYY-MM-DD)
        min_score:  Minimum score to generate a signal
        hold_days:  Max days to hold before time stop
        stop_pct:   Stop loss on option premium
        target_pct: Profit target on option premium
        slippage:   Execution slippage on entry
        config:     Scanner config dict
        verbose:    Print progress

    Returns:
        DataFrame of all trades with P&L
    """
    if symbols is None:
        symbols = ALL_SYMBOLS

    # Fetch SPY for regime — use warmup period before start
    warmup_start = (pd.to_datetime(start_date) - pd.Timedelta(days=300)).strftime("%Y-%m-%d")

    if verbose:
        print(f"\n{'='*62}")
        print(f"  BACKTEST — v4 Scoring System")
        print(f"  Period: {start_date} to {end_date}")
        print(f"  Symbols: {len(symbols)}  |  Min score: {min_score}/12")
        print(f"  Hold: {hold_days}d  |  Stop: -{int(stop_pct*100)}%  |  Target: +{int(target_pct*100)}%")
        print(f"{'='*62}\n")

    # Fetch QQQ for regime
    if verbose:
        print("  Fetching QQQ regime data...")
    qqq_hist = yf.Ticker("QQQ").history(start=warmup_start, end=end_date)

    all_trades = []

    for sym in symbols:
        if verbose:
            print(f"  {sym}...", end=" ", flush=True)

        try:
            hist_full = yf.Ticker(sym).history(start=warmup_start, end=end_date)
            if hist_full.empty or len(hist_full) < 60:
                if verbose:
                    print("skipped (no data)")
                continue

            # Get just the backtest period
            bt_start = pd.to_datetime(start_date).tz_localize("America/New_York")
            bt_end   = pd.to_datetime(end_date).tz_localize("America/New_York")

            # Normalize index timezone
            if hist_full.index.tz is None:
                hist_full.index = hist_full.index.tz_localize("America/New_York")

            bt_dates = hist_full.index[
                (hist_full.index >= bt_start) & (hist_full.index <= bt_end)
            ]

            if len(bt_dates) < 30:
                if verbose:
                    print("skipped (insufficient range)")
                continue

            trade_count = 0
            i = 0
            while i < len(bt_dates) - hold_days - 5:
                current_date = bt_dates[i]

                # Slice history up to current date (no lookahead)
                hist_slice = hist_full.loc[:current_date]
                if len(hist_slice) < 60:
                    i += 1
                    continue

                close  = hist_slice["Close"]
                volume = hist_slice["Volume"]
                price  = float(close.iloc[-1])

                # Technical indicators
                rsi_series = compute_rsi(close)
                rsi = float(rsi_series.iloc[-1])
                if np.isnan(rsi):
                    i += 1
                    continue

                ma_short = close.rolling(CONFIG["ma_short"]).mean()
                ma_long  = close.rolling(CONFIG["ma_long"]).mean()
                ma_s     = float(ma_short.iloc[-1])
                ma_l     = float(ma_long.iloc[-1])
                trend    = get_trend(price, ma_s, ma_l)
                pct_ma50 = round((price - ma_l) / ma_l * 100, 1)

                # Volume
                vol_data = analyze_volume(close, volume, CONFIG["vol_avg_days"])

                # Weekly (simplified — use 5-day rolling for speed)
                weekly_trend = "MIXED"  # simplified for backtest speed

                # MACD and Bollinger
                macd_data = compute_macd(close)
                bb_data   = analyze_bollinger(close)

                # Regime from QQQ
                # Normalize QQQ index timezone
                if qqq_hist.index.tz is None:
                    qqq_hist.index = qqq_hist.index.tz_localize("America/New_York")
                current_date_tz = current_date if current_date.tzinfo else \
                    current_date.tz_localize("America/New_York")
                qqq_slice = qqq_hist.loc[:current_date_tz]
                regime_str = "UNKNOWN"
                if len(qqq_slice) >= 210:
                    rd = get_regime_from_history(qqq_slice["Close"],
                                                 config["regime_ma_short"] if "regime_ma_short" in config else 50,
                                                 config["regime_ma_long"]  if "regime_ma_long"  in config else 200)
                    if rd:
                        regime_str = rd["regime"]

                # Score
                scoring = score_call_setup(
                    regime        = regime_str,
                    rsi           = rsi,
                    trend         = trend,
                    vol_score     = vol_data["score"],
                    weekly_trend  = weekly_trend,
                    pct_from_ma50 = pct_ma50,
                    close         = close,
                    rsi_series    = rsi_series,
                    macd          = macd_data,
                    bollinger     = bb_data,
                )

                score = scoring["score"]

                # Hard disqualifiers
                if rsi >= 75:
                    i += 1
                    continue
                if rsi >= CONFIG["rsi_overbought"] and pct_ma50 > 10:
                    i += 1
                    continue
                if pct_ma50 > 15 and trend == "UPTREND":
                    i += 1
                    continue

                if score < min_score:
                    i += 1
                    continue

                # Simulate trade
                entry_price_stock = price
                estimated_premium = price * 0.03 * (1 + slippage)
                delta             = 0.60  # approximate ITM delta

                # Find exit
                exit_idx  = None
                exit_reason = f"TIME ({hold_days}d)"
                pnl_pct     = 0.0

                for j in range(1, hold_days + 1):
                    next_idx = bt_dates.get_loc(current_date) + j
                    if next_idx >= len(bt_dates):
                        break
                    next_date  = bt_dates[next_idx]
                    next_price = float(hist_full.loc[next_date, "Close"])
                    stock_move = next_price - entry_price_stock

                    # Estimate option move
                    weeks_held      = j / 5.0
                    theta_decay     = -0.02 * weeks_held
                    option_change   = (stock_move * delta) / estimated_premium
                    est_pnl         = option_change + theta_decay

                    if est_pnl <= -stop_pct:
                        pnl_pct     = -stop_pct
                        exit_reason = "STOP LOSS"
                        exit_idx    = next_idx
                        break
                    elif est_pnl >= target_pct:
                        pnl_pct     = target_pct
                        exit_reason = "PROFIT TARGET"
                        exit_idx    = next_idx
                        break

                if exit_idx is None:
                    # Time stop
                    exit_idx = min(bt_dates.get_loc(current_date) + hold_days,
                                   len(bt_dates) - 1)
                    next_price = float(hist_full.loc[bt_dates[exit_idx], "Close"])
                    stock_move = next_price - entry_price_stock
                    weeks_held = hold_days / 5.0
                    pnl_pct    = (stock_move * delta) / estimated_premium - 0.02 * weeks_held
                    pnl_pct    = max(-stop_pct, min(target_pct, pnl_pct))

                pnl_dollars = round(estimated_premium * 100 * pnl_pct, 2)

                all_trades.append({
                    "symbol":       sym,
                    "entry_date":   current_date.strftime("%Y-%m-%d"),
                    "exit_date":    bt_dates[exit_idx].strftime("%Y-%m-%d"),
                    "score":        score,
                    "conviction":   scoring["conviction"],
                    "regime":       regime_str,
                    "trend":        trend,
                    "rsi":          round(rsi, 1),
                    "macd_bull":    macd_data.get("bullish", False),
                    "bb_signal":    bb_data.get("signal", "UNKNOWN"),
                    "entry_stock":  round(entry_price_stock, 2),
                    "exit_stock":   round(next_price, 2),
                    "pnl_pct":      round(pnl_pct * 100, 1),
                    "pnl_dollars":  pnl_dollars,
                    "exit_reason":  exit_reason,
                    "hold_days":    j if exit_reason != f"TIME ({hold_days}d)" else hold_days,
                })

                trade_count += 1
                # Skip ahead past this trade
                i = exit_idx + 1

            if verbose:
                print(f"{trade_count} trades")

        except Exception as e:
            if verbose:
                print(f"error ({e})")

    if not all_trades:
        print("\n  No trades generated.")
        return pd.DataFrame()

    df = pd.DataFrame(all_trades)
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    df["win"]        = df["pnl_dollars"] > 0
    return df


def print_backtest_results(df: pd.DataFrame):
    """Print clean backtest summary with score-band breakdown."""
    if df.empty:
        print("No trades to analyze.")
        return

    W = 62
    total  = len(df)
    wins   = df["win"].sum()
    losses = total - wins
    wr     = round(wins / total * 100, 1)
    total_pnl = round(df["pnl_dollars"].sum(), 2)
    avg_win   = round(df[df["win"]]["pnl_dollars"].mean(), 2) if wins > 0 else 0
    avg_loss  = round(df[~df["win"]]["pnl_dollars"].mean(), 2) if losses > 0 else 0
    gross_p   = df[df["win"]]["pnl_dollars"].sum()
    gross_l   = abs(df[~df["win"]]["pnl_dollars"].sum())
    pf        = round(gross_p / gross_l, 2) if gross_l > 0 else float("inf")

    df_sorted = df.sort_values("entry_date")
    df_sorted["cum_pnl"]  = df_sorted["pnl_dollars"].cumsum()
    df_sorted["run_max"]  = df_sorted["cum_pnl"].cummax()
    df_sorted["drawdown"] = df_sorted["cum_pnl"] - df_sorted["run_max"]
    max_dd = round(df_sorted["drawdown"].min(), 2)

    print(f"\n{'='*W}")
    print(f"  BACKTEST RESULTS — v4 Scoring System")
    print(f"{'='*W}")
    print(f"  Total trades   : {total}")
    print(f"  Win rate       : {wr}%  ({wins}W / {losses}L)")
    print(f"  Total P&L      : ${total_pnl:+,.2f}")
    print(f"  Avg win        : ${avg_win:+,.2f}")
    print(f"  Avg loss       : ${avg_loss:+,.2f}")
    print(f"  Profit factor  : {pf}")
    print(f"  Max drawdown   : ${max_dd:,.2f}")

    if wr >= 60 and pf >= 2.0:
        rating = "EXCELLENT"
    elif wr >= 50 and pf >= 1.5:
        rating = "GOOD"
    elif wr >= 40 and pf >= 1.0:
        rating = "ACCEPTABLE"
    else:
        rating = "NEEDS IMPROVEMENT"
    print(f"\n  Strategy rating: {rating}")

    # Score band breakdown
    print(f"\n{'─'*W}")
    print(f"  BY SCORE BAND:")
    print(f"  {'Score':>6}  {'Trades':>6}  {'Win%':>6}  {'P&L':>10}  {'P.Factor':>9}")
    for score in sorted(df["score"].unique()):
        band = df[df["score"] == score]
        bw   = band["win"].sum()
        bwr  = round(bw / len(band) * 100, 1)
        bpnl = round(band["pnl_dollars"].sum(), 2)
        bgp  = band[band["win"]]["pnl_dollars"].sum()
        bgl  = abs(band[~band["win"]]["pnl_dollars"].sum())
        bpf  = round(bgp / bgl, 2) if bgl > 0 else float("inf")
        print(f"  {score:>6}  {len(band):>6}  {bwr:>5.1f}%  "
              f"${bpnl:>9,.2f}  {bpf:>9}")

    # By regime
    print(f"\n{'─'*W}")
    print(f"  BY MARKET REGIME:")
    for reg in ["BULLISH", "MIXED", "BEARISH"]:
        band = df[df["regime"] == reg]
        if band.empty:
            continue
        bwr  = round(band["win"].mean() * 100, 1)
        bpnl = round(band["pnl_dollars"].sum(), 2)
        print(f"  {reg:<10} {len(band):>4} trades  {bwr:>5.1f}% WR  "
              f"${bpnl:>9,.2f}")

    # By exit reason
    print(f"\n{'─'*W}")
    print(f"  BY EXIT REASON:")
    for reason, grp in df.groupby("exit_reason"):
        gwr  = round(grp["win"].mean() * 100, 1)
        gpnl = round(grp["pnl_dollars"].sum(), 2)
        print(f"  {reason:<20} {len(grp):>4} trades  {gwr:>5.1f}% WR  "
              f"${gpnl:>9,.2f}")

    # MACD filter impact
    print(f"\n{'─'*W}")
    print(f"  MACD BULLISH FILTER IMPACT:")
    for bull in [True, False]:
        band = df[df["macd_bull"] == bull]
        if band.empty:
            continue
        label = "MACD Bullish" if bull else "MACD Bearish"
        bwr   = round(band["win"].mean() * 100, 1)
        bpnl  = round(band["pnl_dollars"].sum(), 2)
        print(f"  {label:<15} {len(band):>4} trades  {bwr:>5.1f}% WR  "
              f"${bpnl:>9,.2f}")

    print(f"\n{'='*W}\n")


def export_backtest(df: pd.DataFrame,
                    filename: str = "backtest_v4.csv"):
    """Export backtest results to CSV."""
    df.to_csv(filename, index=False)
    print(f"  Exported {len(df)} trades → {filename}")


if __name__ == "__main__":
    results = run_scan()
    print_results(results)
