"""Portfolio Management view.

Features:
- Add/update/remove positions (ticker + shares + optional cost basis)
- Live overview with current prices, P&L, allocation
- Last analysis date + rating per position
- Batch analysis with WorkerPool
- Individual drill-in with render_decision_first
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List

import streamlit as st

from dashboard.utils import (
    ALL_ANALYSTS, DASHBOARD_CONFIG, RATING_COLORS,
    validate_ticker, render_decision_first, invalidate_history_cache,
)
from dashboard.db import (
    is_db_available, add_position, update_position, remove_position, list_positions,
)
from dashboard.worker_pool import WorkerPool


def _init_portfolio():
    if "_pf_pool" not in st.session_state:
        from uuid import uuid4
        st.session_state["_pf_pool"] = WorkerPool(str(uuid4()), max_concurrency=3)
    if "_pf_results" not in st.session_state:
        st.session_state["_pf_results"] = []


def render_portfolio():
    st.title("💼 Portfolio")
    st.caption("Manage your positions, track P&L, and run batch analyses with portfolio context.")

    if not is_db_available():
        st.error("SQLite database not available. Portfolio requires the database to be initialized.")
        return

    _init_portfolio()

    # ── Sidebar: Add Position ─────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### Add Position")
        ticker_input = st.text_input("Ticker", placeholder="NVDA", key="pf_ticker").upper().strip()
        shares_input = st.number_input("Shares", min_value=0.01, value=10.0, step=1.0, key="pf_shares")
        cost_basis_input = st.number_input("Cost basis ($/share, optional)", min_value=0.0, value=0.0, step=1.0, key="pf_cost")

        # Check if ticker already exists
        positions = list_positions()
        existing = next((p for p in positions if p["ticker"] == ticker_input), None)
        if existing and ticker_input:
            st.warning(f"⚠️ You currently hold {existing['shares']} shares. Submitting will replace this with {shares_input} shares.")

        if st.button("➕ Add / Update Position", use_container_width=True):
            if not ticker_input:
                st.error("Enter a ticker symbol")
            else:
                with st.spinner(f"Validating {ticker_input}…"):
                    ok, msg = validate_ticker(ticker_input)
                if not ok:
                    st.error(msg)
                else:
                    cost = cost_basis_input if cost_basis_input > 0 else None
                    if add_position(ticker_input, shares_input, cost):
                        st.success(f"{'Updated' if existing else 'Added'} {ticker_input}: {shares_input} shares")
                        st.rerun()
                    else:
                        st.error("Failed to save position")

        st.divider()
        st.markdown("### Batch Analysis")
        pf_analysts = {
            a: st.checkbox(a.capitalize(), value=(a in ["market", "news", "fundamentals"]),
                          key=f"pf_analyst_{a}")
            for a in ALL_ANALYSTS
        }
        pf_selected = [a for a, c in pf_analysts.items() if c]

        if st.button("🚀 Analyze All Positions", use_container_width=True, type="primary",
                    disabled=not positions or st.session_state.get("_global_run_active", False)):
            st.session_state["_global_run_active"] = True
            pool = st.session_state["_pf_pool"]
            trade_date = date.today().strftime("%Y-%m-%d")
            cfg = {**DASHBOARD_CONFIG}
            for p in positions:
                ctx = f"User holds {p['shares']} shares of {p['ticker']}"
                if p.get("cost_basis"):
                    ctx += f" at cost basis ${p['cost_basis']:.2f}/share"
                pool.dispatch(p["ticker"], trade_date, pf_selected, cfg,
                            portfolio_context=ctx)
            st.rerun()

    # ── Main area ─────────────────────────────────────────────────────────────
    positions = list_positions()

    if not positions:
        st.info("No positions yet. Add tickers in the sidebar to build your portfolio.")
        return

    # ── Live Overview ─────────────────────────────────────────────────────────
    st.markdown("### Portfolio Overview")

    # Fetch current prices
    prices = _fetch_prices([p["ticker"] for p in positions])

    # Build overview table
    total_value = 0
    rows_html = ""
    for p in positions:
        ticker = p["ticker"]
        shares = p["shares"]
        cost = p.get("cost_basis")
        price = prices.get(ticker)
        value = price * shares if price else None
        pnl_pct = ((price - cost) / cost * 100) if price and cost else None

        if value:
            total_value += value

        price_str = f"${price:.2f}" if price else "—"
        value_str = f"${value:,.0f}" if value else "—"
        pnl_str = f"{pnl_pct:+.1f}%" if pnl_pct is not None else "—"
        pnl_color = "#22c55e" if pnl_pct and pnl_pct >= 0 else "#ef4444" if pnl_pct else "#6b7280"

        rating = p.get("last_rating") or "—"
        rating_color = RATING_COLORS.get(rating, "#6b7280")
        last_date = p.get("last_analysis_date") or "Never"

        rows_html += (
            f"<tr>"
            f"<td style='padding:6px 12px;font-weight:600'>{ticker}</td>"
            f"<td style='padding:6px 12px'>{shares}</td>"
            f"<td style='padding:6px 12px'>{price_str}</td>"
            f"<td style='padding:6px 12px'>{value_str}</td>"
            f"<td style='padding:6px 12px;color:{pnl_color};font-weight:600'>{pnl_str}</td>"
            f"<td style='padding:6px 12px;color:{rating_color}'>{rating}</td>"
            f"<td style='padding:6px 12px;color:#94a3b8;font-size:12px'>{last_date}</td>"
            f"</tr>"
        )

    st.markdown(
        f"""<table style="width:100%;border-collapse:collapse;background:#1e293b;border-radius:8px;overflow:hidden">
        <thead><tr style="background:#0f172a;color:#64748b;font-size:12px;text-transform:uppercase">
            <th style="padding:8px 12px;text-align:left">Ticker</th>
            <th style="padding:8px 12px;text-align:left">Shares</th>
            <th style="padding:8px 12px;text-align:left">Price</th>
            <th style="padding:8px 12px;text-align:left">Value</th>
            <th style="padding:8px 12px;text-align:left">P&L</th>
            <th style="padding:8px 12px;text-align:left">Rating</th>
            <th style="padding:8px 12px;text-align:left">Last Analysis</th>
        </tr></thead><tbody>{rows_html}</tbody></table>""",
        unsafe_allow_html=True,
    )

    if total_value:
        st.metric("Total Portfolio Value", f"${total_value:,.0f}")

    st.divider()

    # ── Batch analysis results ────────────────────────────────────────────────
    pool = st.session_state["_pf_pool"]
    new_results = pool.drain_results()
    if new_results:
        st.session_state["_pf_results"].extend(new_results)

    pf_results = st.session_state.get("_pf_results", [])
    if pf_results:
        st.markdown("### Analysis Results")
        for r in pf_results:
            rating = r["decision"] or "—"
            color = RATING_COLORS.get(rating, "#6b7280")
            with st.expander(f"**{r['ticker']}** — {rating}"):
                if r["error"]:
                    st.error(r["error"])
                elif r["final_state"]:
                    render_decision_first(r["final_state"])

    # Check if batch is still running
    if not pool.is_idle():
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=3000, key="pf_autorefresh")
        except ImportError:
            import time
            time.sleep(3)
            st.rerun()
    elif st.session_state.get("_global_run_active") and pool.is_idle():
        st.session_state.pop("_global_run_active", None)
        invalidate_history_cache()

    st.divider()

    # ── Per-position management ───────────────────────────────────────────────
    st.markdown("### Manage Positions")
    for p in positions:
        with st.expander(f"{p['ticker']} — {p['shares']} shares"):
            if st.button("🗑 Remove", key=f"pf_remove_{p['ticker']}", use_container_width=True):
                remove_position(p["ticker"])
                st.rerun()


# ── Price fetching ────────────────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def _fetch_prices(tickers: list) -> Dict[str, float]:
    """Fetch current prices for all tickers. Uses yf.download batch call."""
    if not tickers:
        return {}
    try:
        import yfinance as yf
        import pandas as pd
        df = yf.download(tickers, period="1d", progress=False)
        prices = {}
        if df.empty:
            return prices
        if len(tickers) == 1:
            # Single ticker: columns are just ['Open', 'High', 'Low', 'Close', ...]
            close = df["Close"].iloc[-1] if "Close" in df.columns else None
            if close and not pd.isna(close):
                prices[tickers[0]] = float(close)
        else:
            # Multi ticker: MultiIndex columns
            for t in tickers:
                try:
                    close = df[("Close", t)].iloc[-1]
                    if not pd.isna(close):
                        prices[t] = float(close)
                except (KeyError, IndexError):
                    pass
        # Fallback for missing tickers
        for t in tickers:
            if t not in prices:
                try:
                    info = yf.Ticker(t).info
                    p = info.get("currentPrice") or info.get("regularMarketPrice")
                    if p:
                        prices[t] = float(p)
                except Exception:
                    pass
        return prices
    except Exception:
        return {}
