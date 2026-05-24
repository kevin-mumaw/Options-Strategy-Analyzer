"""
options_scanner_v4.py
=====================
Phase 1 — CALL-side scanner with quality scoring gate.

Design philosophy:
  - Only generate a signal when conviction score >= 6/10
  - If nothing qualifies, say so clearly — no trade is a valid result
  - Every signal includes exact exit prices — no guessing required
  - Risk management is built in, not optional
  - Output is clean and immediately actionable

Scoring system (10 points total):
  Regime    0-2  Market direction via QQQ
  RSI       0-2  Momentum positioning
  Trend     0-2  Price structure vs moving averages
  Volume    0-2  Institutional activity
  Weekly    0-1  Multi-timeframe confirmation
  Support   0-1  Entry quality relative to key levels

  Score >= 6  → Signal generated
  Score  < 6  → No signal (wait for better setup)
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
# WATCHLIST — 25 names with highly liquid options markets
# ─────────────────────────────────────────────────────────────
WATCHLIST = {
    "mega_cap_tech": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA"],
    "financials":    ["JPM", "GS", "V", "MA", "BAC"],
    "healthcare":    ["UNH", "LLY", "JNJ"],
    "consumer":      ["HD", "WMT", "COST"],
    "etfs":          ["SPY", "QQQ", "XLF", "GLD"],
    "industrials":   ["CAT", "DE"],
    "energy":        ["XOM", "CVX"],
}

ALL_SYMBOLS = [s for group in WATCHLIST.values() for s in group]

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
    "max_signals":        3,           # cap output at top 3 signals

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

    # Options selection
    "min_dte":            30,
    "target_dte":         45,
    "min_delta":          0.35,
    "max_delta":          0.65,
    "min_option_volume":  50,
    "min_option_oi":      200,
    "max_spread_pct":     25.0,
    "atm_tolerance":      0.10,

    # Exit rules — these are fixed, not suggestions
    "stop_loss_pct":      0.35,        # exit if premium drops 35%
    "profit_target_pct":  0.75,        # exit if premium rises 75%
    "time_stop_dte":      21,          # exit when 21 DTE remains
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
    regime:      str,
    rsi:         float,
    trend:       str,
    vol_score:   int,
    weekly_trend: str,
    pct_from_ma50: float,
    close:       pd.Series,
    rsi_series:  pd.Series,
) -> dict:
    """
    Score a potential CALL setup on a 10-point scale.

    Returns:
        score        int 0-10
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

    # ── Total ────────────────────────────────────────────────
    total = sum(breakdown.values())

    if total >= 9:
        conviction = "VERY HIGH"
    elif total >= 7:
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
# OPTIONS CHAIN
# ─────────────────────────────────────────────────────────────

def find_best_call(ticker: yf.Ticker, stock_price: float,
                   config: dict = CONFIG) -> Optional[dict]:
    """
    Find the best available CALL option meeting liquidity and DTE criteria.
    Targets near-ATM strikes with 30-60 DTE.
    Returns a dict with all option details, or None if nothing qualifies.
    """
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
            vol    = int(row.get("volume", 0) or 0)
            strike = float(row["strike"])
            mid    = round((bid + ask) / 2, 2)
            T      = best_dte / 365.0

            greeks = black_scholes_greeks(
                "call", stock_price, strike, T, 0.045, iv if iv > 0 else 0.25
            )

            # Skip if delta out of range
            delta = greeks.get("delta", 0.5)
            if not np.isnan(delta):
                if delta < config["min_delta"] or delta > config["max_delta"]:
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
            }

    except Exception:
        pass
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
        vol_data = analyze_volume(close, volume, config["vol_avg_days"])

        # Weekly trend
        weekly = analyze_weekly(ticker)

        # Score
        scoring = score_call_setup(
            regime      = regime["regime"],
            rsi         = rsi,
            trend       = trend,
            vol_score   = vol_data["score"],
            weekly_trend= weekly["trend"],
            pct_from_ma50 = pct_ma50,
            close       = close,
            rsi_series  = rsi_series,
        )

        # Add volume reason to scoring reasons
        vol_pts = vol_data["score"]
        scoring["reasons"].insert(
            4,
            f"{'✓' if vol_pts == 2 else ('~' if vol_pts == 1 else '✗')} "
            f"Volume  [{vol_pts}/2] {vol_data['detail']}"
        )

        score = scoring["score"]

        # Return even if below threshold — used for "near misses" display
        result = {
            "symbol":     symbol,
            "price":      price,
            "rsi":        rsi,
            "trend":      trend,
            "ma20":       ma_s,
            "ma50":       ma_l,
            "pct_ma20":   pct_ma20,
            "pct_ma50":   pct_ma50,
            "hv":         hv,
            "vol_data":   vol_data,
            "weekly":     weekly,
            "scoring":    scoring,
            "score":      score,
            "conviction": scoring["conviction"],
            "option":     None,
            "sizing":     None,
            "error":      None,
        }

        if score >= config["min_score"]:
            option = find_best_call(ticker, price, config)
            if option:
                sizing = size_position(option["ask"], score, config)
                result["option"] = option
                result["sizing"] = sizing

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

    # Split into signals and near misses
    signals    = [r for r in results
                  if r.get("score", 0) >= config["min_score"]
                  and r.get("option") is not None][:config["max_signals"]]

    near_misses = [r for r in results
                   if r.get("score", 0) >= config["min_score"] - 1
                   and r not in signals][:5]

    no_option   = [r for r in results
                   if r.get("score", 0) >= config["min_score"]
                   and r.get("option") is None]

    return {
        "regime":      regime,
        "signals":     signals,
        "near_misses": near_misses,
        "no_option":   no_option,
        "all_results": results,
        "scanned":     len(results),
        "scan_date":   datetime.now().strftime("%Y-%m-%d %H:%M"),
        "config":      config,
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
    print(f"  OPTIONS SCANNER — Phase 1  |  {scan['scan_date']}")
    print(f"  Account: ${config['account_size']:,.0f}  |  "
          f"Scanned: {scan['scanned']} symbols")
    print("█" * W)

    # ── Regime ──────────────────────────────────────────────
    regime_icons = {"BULLISH": "🟢", "MIXED": "🟡", "BEARISH": "🔴", "UNKNOWN": "⚪"}
    icon = regime_icons.get(regime["regime"], "⚪")
    print(f"\n  MARKET REGIME: {icon} {regime['regime']}")
    print(f"  {regime['detail']}")

    # ── No signals ──────────────────────────────────────────
    if not signals:
        print(f"\n{'─' * W}")
        print("  NO QUALIFYING SETUPS TODAY")
        print(f"  Nothing scored {config['min_score']}+/10 with available options.")
        print("  Recommendation: Wait. Do not force a trade.")

        # Show best scores anyway
        top = [r for r in scan["all_results"] if not r.get("error")][:5]
        if top:
            print(f"\n  Best scores today:")
            for r in top:
                print(f"    {r['symbol']:6s}  {r['score']}/10  "
                      f"({r.get('conviction','—')})  "
                      f"Trend: {r.get('trend','—')}  RSI: {r.get('rsi','—')}")

        # Check if any scored but had no option
        if scan["no_option"]:
            print(f"\n  Signals found but no liquid options available:")
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
        print(f"\n  POSITION (${config['account_size']:,.0f} account):")
        if siz and siz["contracts"] > 0:
            print(f"    Contracts : {siz['contracts']}")
            print(f"    Cost      : ${siz['total_cost']:,.0f}  "
                  f"({siz['pct_of_account']}% of account)")
            if siz["pct_of_account"] > 20:
                print(f"    ⚠  This is a large allocation — "
                      f"only take if no other positions open")
        else:
            print(f"    ⚠  Premium too high for account size.")
            print(f"    Consider a debit spread to reduce cost.")

        # Exit rules — the most important section
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
        else:
            print(f"    (Size position first)")

        print()

    # ── Near misses ─────────────────────────────────────────
    if scan["near_misses"]:
        print(f"{'─' * W}")
        print(f"  NEAR MISSES (score {config['min_score']-1}/10 — "
              f"watch these):")
        for r in scan["near_misses"]:
            print(f"    {r['symbol']:6s}  {r['score']}/10  "
                  f"Trend: {r.get('trend','—'):<10}  "
                  f"RSI: {r.get('rsi', '—')}")

    # ── Footer ──────────────────────────────────────────────
    print(f"{'─' * W}")
    print(f"  SCAN COMPLETE  |  {len(signals)} signal(s)  |  "
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
# ENTRY POINT
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    results = run_scan()
    print_results(results)
