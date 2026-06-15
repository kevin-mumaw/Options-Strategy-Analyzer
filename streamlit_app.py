"""
Options Scanner — Streamlit Mobile App
Pulls options_scanner_v4.py from GitHub and runs the scan.
"""

import streamlit as st
import sys
import os
import requests
import time

# ─────────────────────────────────────────────────────────────
# Page config — must be first Streamlit call
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Options Scanner",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────────────────────
# Load scanner module from GitHub
# ─────────────────────────────────────────────────────────────
SCANNER_URL = (
    "https://raw.githubusercontent.com/kevin-mumaw/"
    "options-strategy-analyzer/main/options_scanner_v4.py"
)

@st.cache_resource(ttl=300)  # cache for 5 minutes
def load_scanner():
    """Download and import the scanner module."""
    for mod in list(sys.modules.keys()):
        if "options_scanner" in mod:
            del sys.modules[mod]

    if os.path.exists("options_scanner_v4.py"):
        os.remove("options_scanner_v4.py")

    r = requests.get(SCANNER_URL)
    r.raise_for_status()
    with open("options_scanner_v4.py", "w") as f:
        f.write(r.text)

    import options_scanner_v4 as s
    return s


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def regime_color(regime):
    return {"BULLISH": "🟢", "MIXED": "🟡", "BEARISH": "🔴"}.get(regime, "⚪")


def conviction_color(conviction):
    return {"VERY HIGH": "🔥", "HIGH": "✅", "MODERATE": "🔵"}.get(conviction, "⚪")


def render_signal(r, config, signal_type="CALL"):
    """Render a single CALL or PUT signal as a Streamlit card."""
    sym      = r["symbol"]
    score    = r["score"] if signal_type == "CALL" else r.get("put_score", 0)
    conv     = r["conviction"] if signal_type == "CALL" else r.get("put_conviction", "")
    opt      = r["option"] if signal_type == "CALL" else r.get("put_option")
    siz      = r["sizing"] if signal_type == "CALL" else r.get("put_sizing")
    scoring  = r["scoring"] if signal_type == "CALL" else r.get("put_scoring", {})
    spr      = r.get("spread")
    spr_siz  = r.get("spread_siz")

    direction = "BUY CALL" if signal_type == "CALL" else "BUY PUT"
    icon = conviction_color(conv)

    with st.expander(f"{icon} {sym} — {direction}  |  Score: {score}/11  [{conv}]", expanded=True):

        # Scoring breakdown
        st.markdown("**Why this trade:**")
        reasons = scoring.get("reasons", [])
        for reason in reasons:
            st.markdown(f"`{reason}`")

        st.divider()

        # Stock info
        col1, col2, col3 = st.columns(3)
        col1.metric("Price", f"${r['price']:.2f}")
        col2.metric("RSI", f"{r['rsi']:.0f}")
        col3.metric("Trend", r["trend"])

        col1, col2 = st.columns(2)
        col1.metric("MA20", f"${r['ma20']:.2f}", f"{r['pct_ma20']:+.1f}%")
        col2.metric("MA50", f"${r['ma50']:.2f}", f"{r['pct_ma50']:+.1f}%")

        earn = r.get("earnings", {})
        if earn.get("earnings_date"):
            days = earn.get("days_to_earnings")
            ed   = earn.get("earnings_date")
            if earn.get("has_earnings"):
                st.warning(f"⚠️ Earnings in {days} days ({ed})")
            else:
                st.info(f"📅 Earnings: {ed} ({days} days away)")

        st.divider()

        # Option info
        st.markdown("**Option:**")
        col1, col2 = st.columns(2)
        col1.metric("Strike", f"${opt['strike']:.0f} {signal_type}")
        col2.metric("Expiry", f"{opt['expiry']} ({opt['dte']} DTE)")

        col1, col2, col3 = st.columns(3)
        col1.metric("Bid", f"${opt['bid']:.2f}")
        col2.metric("Ask", f"${opt['ask']:.2f}")
        col3.metric("IV", f"{opt['iv']}%" if opt['iv'] else "N/A")

        col1, col2, col3 = st.columns(3)
        col1.metric("Delta", f"{opt['delta']:.3f}")
        col2.metric("Theta", f"${opt['theta']*100:.2f}/day")
        col3.metric("Spread", f"{opt['spread_pct']:.1f}%")

        st.divider()

        # Position
        st.markdown("**Position:**")
        if siz and siz["contracts"] > 0 and not (spr and spr_siz):
            target_gain       = round(siz["target_price"] - opt["ask"], 2)
            risk              = round(opt["ask"] - siz["stop_price"], 2)
            rr                = round(target_gain / risk, 2) if risk > 0 else 0
            max_loss          = round(opt["ask"] * 100 * siz["contracts"], 2)
            stop_loss_dollars = round(risk * 100 * siz["contracts"], 2)
            target_dollars    = round(target_gain * 100 * siz["contracts"], 2)

            col1, col2 = st.columns(2)
            col1.metric("Type", "Single Leg")
            col2.metric("Contracts", siz["contracts"])

            col1, col2, col3 = st.columns(3)
            col1.metric("Cost", f"${siz['total_cost']:,.0f}")
            col2.metric("Acct %", f"{siz['pct_of_account']}%")
            col3.metric("R/R", f"{rr:.1f}x")

            col1, col2, col3 = st.columns(3)
            col1.metric("Max Loss", f"${max_loss:,.0f}", "if expires worthless")
            col2.metric("Stop Loss", f"-${stop_loss_dollars:,.0f}", f"at ${siz['stop_price']:.2f}")
            col3.metric("Target", f"+${target_dollars:,.0f}", f"at ${siz['target_price']:.2f}")

        elif spr and spr_siz and spr_siz["contracts"] > 0:
            col1, col2 = st.columns(2)
            col1.metric("Type", "Bull Call Spread")
            col2.metric("Width", f"${spr_siz['strike_width']:.0f}")

            st.markdown(f"**Buy:** ${opt['strike']:.0f} @ ${opt['ask']:.2f}  |  "
                        f"**Sell:** ${spr['strike']:.0f} @ ${spr['bid']:.2f}")

            col1, col2, col3 = st.columns(3)
            col1.metric("Net Debit", f"${spr_siz['net_debit']:.2f}")
            col2.metric("Max Loss", f"${spr_siz['total_cost']:,.0f}")
            col3.metric("Max Gain", f"${spr_siz['max_gain']:,.0f}")

            col1, col2 = st.columns(2)
            col1.metric("Contracts", spr_siz["contracts"])
            col2.metric("R/R", f"{spr_siz['reward_risk']:.1f}x")

        st.divider()

        # Exit rules
        st.markdown("**Exit Rules:**")
        if siz and siz["contracts"] > 0 and not (spr and spr_siz):
            st.error(f"🛑 Stop Loss: ${siz['stop_price']:.2f}  (-35%)")
            st.success(f"🎯 Profit Target: ${siz['target_price']:.2f}  (+75%)")
        elif spr and spr_siz:
            debit    = spr_siz["net_debit"]
            st.error(f"🛑 Stop: Close spread if value < ${debit * 0.50:.2f}  (-50%)")
            st.success(f"🎯 Target: Close spread if value > ${debit * 1.75:.2f}  (+75%)")

        from datetime import datetime, timedelta
        try:
            time_stop = (
                datetime.strptime(opt["expiry"], "%Y-%m-%d")
                - timedelta(days=config["time_stop_dte"])
            ).strftime("%b %d")
            st.warning(f"⏱️ Time Stop: Exit by {time_stop}")
        except Exception:
            pass

        if signal_type in ("CALL", "PUT") and siz and siz["contracts"] > 0 and not (spr and spr_siz):
            st.markdown("---")
            st.markdown("**⚠️ Robinhood Stop Order:**")
            st.markdown(f"Use **Stop Limit** — NOT limit sell")
            st.markdown(f"Stop price: **${siz['stop_price']:.2f}**  |  "
                        f"Limit price: **${round(siz['stop_price'] * 0.95, 2):.2f}**")


def render_csp(r, config):
    """Render a CSP signal."""
    sym     = r["symbol"]
    score   = r["csp_score"]
    conv    = r["csp_conviction"]
    opt     = r["csp_option"]
    siz     = r["csp_sizing"]
    scoring = r["csp_scoring"]

    icon = conviction_color(conv)

    with st.expander(f"{icon} {sym} — SELL PUT (CSP)  |  Score: {score}/11  [{conv}]", expanded=True):

        st.markdown("**Why this trade:**")
        for reason in scoring.get("reasons", []):
            st.markdown(f"`{reason}`")

        st.divider()

        col1, col2, col3 = st.columns(3)
        col1.metric("Price", f"${r['price']:.2f}")
        col2.metric("RSI", f"{r['rsi']:.0f}")
        col3.metric("Trend", r["trend"])

        earn = r.get("earnings", {})
        if earn.get("earnings_date"):
            st.info(f"📅 Earnings: {earn['earnings_date']} ({earn['days_to_earnings']} days)")

        st.divider()

        st.markdown("**Option (SELL THIS PUT):**")
        col1, col2 = st.columns(2)
        col1.metric("Strike", f"${opt['strike']:.0f} PUT")
        col2.metric("Expiry", f"{opt['expiry']} ({opt['dte']} DTE)")

        col1, col2, col3 = st.columns(3)
        col1.metric("Bid", f"${opt['bid']:.2f}")
        col2.metric("IV", f"{opt['iv']}%" if opt['iv'] else "N/A")
        col3.metric("Yield", f"{opt['premium_yield']:.2f}%")

        st.divider()

        max_loss = round((opt['strike'] * 100 * siz['contracts']) - siz['total_premium'], 2)

        st.markdown("**Position:**")
        col1, col2, col3 = st.columns(3)
        col1.metric("Max Gain", f"${siz['total_premium']:,.0f}", "premium collected")
        col2.metric("Max Loss", f"${max_loss:,.0f}", "stock → $0")
        col3.metric("Breakeven", f"${siz['breakeven']:.2f}")

        col1, col2 = st.columns(2)
        col1.metric("Cash Required", f"${siz['total_cash']:,.0f}")
        col2.metric("Acct %", f"{siz['pct_of_account']}%")

        st.divider()

        st.markdown("**Outcomes:**")
        st.success(f"✓ Stock above ${opt['strike']:.0f} at expiry → keep ${siz['total_premium']:,.0f}")
        st.error(f"✗ Stock below ${opt['strike']:.0f} → assigned at ${opt['strike']:.0f} "
                 f"(cost basis ${siz['breakeven']:.2f})")

        st.divider()
        st.markdown("**Exit Options:**")
        st.info(f"Buy back at 50% profit: ${round(opt['bid'] * 0.50, 2):.2f}")
        st.warning(f"Buy back to cut loss: ${round(opt['bid'] * 2.0, 2):.2f}  (2× rule)")

        st.markdown("---")
        st.markdown("⚠️ **Execute on thinkorswim — requires margin approval**")


# ─────────────────────────────────────────────────────────────
# Google Sheets — read open positions
# ─────────────────────────────────────────────────────────────
SHEET_ID = "1tcNnijOAzxfn9M3bwwBvKZ72ENRLL7cnW2Y774w6ev0"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"

@st.cache_data(ttl=60)  # refresh every 60 seconds
def load_journal():
    """Load trade journal from public Google Sheet."""
    try:
        import pandas as pd
        df = pd.read_csv(SHEET_URL)
        return df
    except Exception as e:
        return None


def get_current_premium(symbol: str, strike: float,
                         expiry: str, direction: str) -> float:
    """Fetch current option premium from yfinance."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        chain  = ticker.option_chain(expiry)
        if direction == "BUY CALL":
            opts = chain.calls
        else:
            opts = chain.puts
        row = opts[opts["strike"] == strike]
        if not row.empty:
            bid = float(row.iloc[0]["bid"])
            ask = float(row.iloc[0]["ask"])
            return round((bid + ask) / 2, 2)
    except Exception:
        pass
    return None


def render_position_tracker():
    """Display open positions with live P&L."""
    st.subheader("📋 Open Positions")

    df = load_journal()

    if df is None:
        st.error("Could not load journal from Google Sheets.")
        return

    open_trades = df[df["status"] == "OPEN"].copy()

    if open_trades.empty:
        st.info("No open positions.")
        return

    from datetime import datetime
    today = datetime.today().date()

    for _, trade in open_trades.iterrows():
        sym           = trade["symbol"]
        direction     = trade["direction"]
        entry_premium = float(trade["entry_premium"])
        stop_price    = float(trade["stop_price"])
        target_price  = float(trade["target_price"])
        contracts     = int(trade["contracts"])
        time_stop     = trade["time_stop_date"]
        trade_id      = trade["trade_id"]
        score         = trade["score"]

        # Days to time stop
        try:
            stop_date  = datetime.strptime(str(time_stop), "%Y-%m-%d").date()
            days_left  = (stop_date - today).days
        except Exception:
            days_left  = None

        # Current premium
        try:
            # Parse strike and expiry from trade_id or notes
            # Use yfinance to get ATM option price as proxy
            import yfinance as yf
            ticker     = yf.Ticker(sym)
            hist       = ticker.history(period="1d")
            stock_price = float(hist["Close"].iloc[-1]) if not hist.empty else None
        except Exception:
            stock_price = None

        # Try to get actual option premium
        current_premium = None
        # We don't store strike/expiry in journal so use stock price as proxy
        # Show what we have and note it's approximate
        if stock_price:
            # Estimate current option value based on stock move
            pass

        # P&L based on last known vs entry
        # Show entry-based metrics
        pnl_at_stop   = round((stop_price - entry_premium) * 100 * contracts, 2)
        pnl_at_target = round((target_price - entry_premium) * 100 * contracts, 2)

        # Status color
        if days_left is not None and days_left <= 5:
            status_color = "🔴"
        elif days_left is not None and days_left <= 10:
            status_color = "🟡"
        else:
            status_color = "🟢"

        with st.expander(
            f"{status_color} {sym} — {direction}  |  "
            f"Entry: ${entry_premium:.2f}  |  "
            f"{days_left}d to time stop",
            expanded=True
        ):
            col1, col2, col3 = st.columns(3)
            col1.metric("Entry Premium", f"${entry_premium:.2f}")
            col2.metric("Contracts", contracts)
            col3.metric("Score", f"{score}/11")

            col1, col2, col3 = st.columns(3)
            col1.metric("Stop Loss", f"${stop_price:.2f}",
                        f"${pnl_at_stop:+.0f} if hit")
            col2.metric("Target", f"${target_price:.2f}",
                        f"${pnl_at_target:+.0f} if hit")
            col3.metric("Time Stop", str(time_stop),
                        f"{days_left}d remaining" if days_left else "")

            if stock_price:
                st.metric(f"{sym} Stock Price", f"${stock_price:.2f}")

            # Progress bar — where is premium between stop and target
            range_total = target_price - stop_price
            current_pos = entry_premium - stop_price
            progress    = max(0.0, min(1.0, current_pos / range_total))
            st.progress(progress, text=f"Entry position: stop ◄──── ${entry_premium:.2f} ────► target")

            if trade["notes"]:
                st.caption(f"Notes: {trade['notes']}")

            st.caption(f"Trade ID: {trade_id} | Entered: {trade['entry_date']}")

    # Summary stats
    all_closed = df[df["status"].isin(["WIN", "LOSS"])]
    if not all_closed.empty:
        st.divider()
        wins      = len(df[df["status"] == "WIN"])
        losses    = len(df[df["status"] == "LOSS"])
        total_pnl = df[df["pnl_dollars"].notna()]["pnl_dollars"].astype(float).sum()
        win_rate  = round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Wins", wins)
        col2.metric("Losses", losses)
        col3.metric("Win Rate", f"{win_rate}%")
        col4.metric("Total P&L", f"${total_pnl:+.2f}")


# ─────────────────────────────────────────────────────────────
# CAN SLIM Scanner — load from GitHub
# ─────────────────────────────────────────────────────────────
CANSLIM_URL = (
    "https://raw.githubusercontent.com/kevin-mumaw/"
    "canslim_scanner/main/canslim_scanner.py"
)

CANSLIM_SYMBOLS = [
    "NVDA", "AAPL", "MSFT", "GOOGL", "META",
    "JPM", "GS", "V", "MA", "UNH", "LLY", "CAT", "DE"
]

@st.cache_resource(ttl=300)
def load_canslim():
    """Download and import the CAN SLIM scanner module."""
    import importlib
    for mod in list(sys.modules.keys()):
        if "canslim" in mod:
            del sys.modules[mod]
    if os.path.exists("canslim_scanner.py"):
        os.remove("canslim_scanner.py")
    r = requests.get(CANSLIM_URL)
    r.raise_for_status()
    with open("canslim_scanner.py", "w") as f:
        f.write(r.text)
    import canslim_scanner as cs
    return cs


def render_canslim():
    """Display CAN SLIM scan results."""
    st.subheader("📊 CAN SLIM Scanner")
    st.caption("William O'Neil methodology · 7 criteria · Min 4/7 to qualify")

    with st.spinner("Loading CAN SLIM scanner..."):
        try:
            cs = load_canslim()
        except Exception as e:
            st.error(f"Failed to load CAN SLIM scanner: {e}")
            return

    if st.button("🔍 Run CAN SLIM Scan", type="primary", use_container_width=True):
        with st.spinner("Scanning 13 symbols..."):
            try:
                import io
                from contextlib import redirect_stdout
                scanner = cs.CANSLIMScanner()
                # Suppress print output
                f = io.StringIO()
                with redirect_stdout(f):
                    results = scanner.scan(CANSLIM_SYMBOLS, min_passes=4)
                st.session_state["canslim_results"] = results
            except Exception as e:
                st.error(f"Scan error: {e}")
                return

    if "canslim_results" not in st.session_state:
        st.info("👆 Hit Run CAN SLIM Scan to screen stocks.")
        return

    results = st.session_state["canslim_results"]

    if not results:
        st.info("No stocks passed 4/7 criteria today.")
        return

    criteria_labels = {
        "C": "Current Earnings (Q EPS growth)",
        "A": "Annual Earnings (3-yr avg)",
        "N": "Near 52-week High",
        "S": "Supply/Demand (Up/Down vol)",
        "L": "Leader vs Laggard (RS Rating)",
        "I": "Institutional Sponsorship",
        "M": "Market Direction (SPY)",
    }

    for r in results:
        sym    = r["symbol"]
        passes = r["passes"]
        bar    = "█" * passes + "░" * (7 - passes)

        with st.expander(
            f"**{sym}** [{bar}] {passes}/7 criteria",
            expanded=passes >= 6
        ):
            if r.get("error"):
                st.error(f"Error: {r['error']}")
                continue

            for key, label in criteria_labels.items():
                crit   = r.get(key, {})
                passed = crit.get("score", False)
                detail = crit.get("detail", "No data")
                icon   = "✅" if passed else "❌"
                st.markdown(f"{icon} **{key} — {label}**")
                st.caption(f"   {detail}")


# ─────────────────────────────────────────────────────────────
# Main App
# ─────────────────────────────────────────────────────────────
def main():
    st.title("📊 Options Scanner")
    st.caption("Systematic options signals · Jason Brown / PTU Framework")

    # Tabs
    tab1, tab2, tab3 = st.tabs(["🔍 Scanner", "📋 Positions", "📊 CAN SLIM"])

    with tab2:
        render_position_tracker()

    with tab3:
        render_canslim()

    with tab1:
        # Account size slider
        account_size = st.slider(
            "Account Size",
            min_value=1000,
            max_value=25000,
            value=5000,
            step=500,
            format="$%d",
        )

    # Load scanner
    with st.spinner("Loading scanner..."):
        try:
            s = load_scanner()
            st.caption(f"Scanner v{s.VERSION}")
        except Exception as e:
            st.error(f"Failed to load scanner: {e}")
            return

    # Run scan button
    if st.button("🔍 Run Scan", type="primary", use_container_width=True):
        with st.spinner("Scanning 34 symbols..."):
            start = time.time()
            try:
                config = dict(s.CONFIG)
                config["account_size"] = account_size
                results = s.run_scan(symbols=s.ALL_SYMBOLS, config=config)
                elapsed = round(time.time() - start, 1)
                st.session_state["results"]     = results
                st.session_state["elapsed"]     = elapsed
                st.session_state["account_size"] = account_size
            except Exception as e:
                st.error(f"Scan error: {e}")
                return

    # Use stored results if available
    if "results" not in st.session_state:
        st.info("👆 Hit Run Scan to get today's signals.")
        return

    results      = st.session_state["results"]
    elapsed      = st.session_state["elapsed"]
    config       = dict(s.CONFIG)
    config["account_size"] = st.session_state.get("account_size", account_size)

    # ── Market Regime ────────────────────────────────────
    regime    = results["regime"]
    r_name    = regime["regime"]
    r_dir     = regime.get("direction", "STABLE")
    icon      = regime_color(r_name)
    pct_ma50  = regime.get("pct_ma50", 0) or 0

    st.markdown("---")
    st.subheader(f"{icon} Market Regime: {r_name}")
    st.caption(regime["detail"])

    # Market summary
    if r_name == "BULLISH":
        if r_dir == "IMPROVING":
            st.info("🔄 Market recovering to BULLISH — early entries acceptable")
        elif pct_ma50 > 10:
            st.warning("Market extended above MA50 — highest conviction only")
        elif pct_ma50 > 5:
            st.success("Market healthy — proceed with qualifying setups")
        else:
            st.success("Market near support — good entry conditions")
    elif r_name == "MIXED":
        if r_dir == "DETERIORATING":
            st.error("⚠️ Market deteriorating — no new CALL entries")
        elif r_dir == "IMPROVING":
            st.warning("⚠️ Recovering from BEARISH — wait for BULLISH confirmation")
        else:
            st.warning("⚠️ Transitional market — score 9+ required for CALLs")
    elif r_name == "BEARISH":
        st.error("🔴 Market in downtrend — no CALLs, no CSPs. PUT signals only.")

    st.caption(f"Scan completed in {elapsed}s · {results['scan_date']}")

    # ── CALL Signals ─────────────────────────────────────
    signals = results.get("signals", [])
    st.markdown("---")
    st.subheader(f"📈 CALL Signals ({len(signals)})")

    if signals:
        for r in signals:
            render_signal(r, config, "CALL")
    else:
        st.info("No qualifying CALL setups today. No trade is always a valid choice.")

    # ── PUT Signals ──────────────────────────────────────
    put_signals = results.get("put_signals", [])
    if put_signals:
        st.markdown("---")
        st.subheader(f"📉 PUT Signals ({len(put_signals)})")
        for r in put_signals:
            render_signal(r, config, "PUT")

    # ── CSP Signals ──────────────────────────────────────
    csp_signals = results.get("csp_signals", [])
    if csp_signals:
        st.markdown("---")
        st.subheader(f"💰 CSP Signals ({len(csp_signals)}) — thinkorswim only")
        for r in csp_signals:
            render_csp(r, config)

    # ── Near Misses ──────────────────────────────────────
    near_misses = results.get("near_misses", [])
    if near_misses:
        st.markdown("---")
        with st.expander(f"🔍 Near Misses ({len(near_misses)})"):
            for r in near_misses:
                st.markdown(
                    f"**{r['symbol']}** {r['score']}/11 — "
                    f"Trend: {r['trend']} | RSI: {r['rsi']:.1f}"
                )

    # ── Disqualified ─────────────────────────────────────
    hard_fails = [r for r in results.get("all_results", [])
                  if r.get("hard_fail")
                  and r.get("score", 0) >= config["min_score"]][:5]
    if hard_fails:
        with st.expander(f"🚫 Disqualified ({len(hard_fails)})"):
            for r in hard_fails:
                st.markdown(f"**{r['symbol']}** {r['score']}/11 — {r['hard_fail']}")

    # ── R/R Failures ─────────────────────────────────────
    rr_fails = results.get("rr_disqualified", [])
    if rr_fails:
        with st.expander(f"⏳ Found Option — Failed R/R ({len(rr_fails)})"):
            for r in rr_fails:
                rr = r.get("rr_fail", "?")
                st.markdown(
                    f"**{r['symbol']}** {r['score']}/11 — "
                    f"R/R: {rr:.1f}x — wait for pullback or lower IV"
                )


if __name__ == "__main__":
    main()
