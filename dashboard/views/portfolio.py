"""Portfolio Management view.

Features:
- Add/update/remove positions (ticker + shares + optional cost basis)
- Live overview with current prices, P&L, allocation
- Last analysis date + rating per position
- Batch analysis with WorkerPool
- Individual drill-in with render_decision_first
"""

from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st

from dashboard.utils import (
    DASHBOARD_CONFIG, RATING_COLORS,
    validate_ticker, render_decision_first, invalidate_history_cache,
)
from dashboard.db import (
    is_db_available, add_position, update_position, remove_position, list_positions,
)


def _init_portfolio():
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
        cost_basis_input = st.number_input("Buy price ($/share)", min_value=0.01, value=100.0, step=0.01, key="pf_cost",
                                          help="The price you paid per share")

        # Check if ticker already exists — show existing lots
        positions = list_positions()
        existing_lots = [p for p in positions if p["ticker"] == ticker_input]
        if existing_lots and ticker_input:
            total_shares = sum(p["shares"] for p in existing_lots)
            st.info(f"You already hold {total_shares} shares of {ticker_input} across {len(existing_lots)} lot(s). New entry will be added as a separate lot.")

        if st.button("➕ Add Position", use_container_width=True):
            if not ticker_input:
                st.error("Enter a ticker symbol")
            else:
                with st.spinner(f"Validating {ticker_input}…"):
                    ok, msg = validate_ticker(ticker_input)
                if not ok:
                    st.error(msg)
                else:
                    if add_position(ticker_input, shares_input, cost_basis_input):
                        st.success(f"Added {ticker_input}: {shares_input} shares @ ${cost_basis_input:.2f}")
                        st.rerun()
                    else:
                        st.error("Failed to save position")

    # ── Main area ─────────────────────────────────────────────────────────────
    positions = list_positions()

    if not positions:
        st.info("No positions yet. Add tickers in the sidebar to build your portfolio.")
        return

    # ── Live Overview ─────────────────────────────────────────────────────────
    st.markdown("### Portfolio Overview")

    # Fetch current prices (unique tickers only)
    unique_tickers = list({p["ticker"] for p in positions})
    prices = _fetch_prices(unique_tickers)

    # Build overview table — show each lot
    total_value = 0
    total_cost_value = 0
    rows_html = ""
    for p in positions:
        ticker = p["ticker"]
        shares = p["shares"]
        cost = p.get("cost_basis")
        price = prices.get(ticker)
        value = price * shares if price else None
        cost_value = cost * shares if cost else None
        pnl_pct = ((price - cost) / cost * 100) if price and cost else None

        if value:
            total_value += value
        if cost_value:
            total_cost_value += cost_value

        price_str = f"${price:.2f}" if price else "—"
        value_str = f"${value:,.0f}" if value else "—"
        cost_str = f"${cost:.2f}" if cost else "—"
        pnl_str = f"{pnl_pct:+.1f}%" if pnl_pct is not None else "—"
        pnl_color = "#22c55e" if pnl_pct and pnl_pct >= 0 else "#ef4444" if pnl_pct else "#6b7280"

        rating = p.get("last_rating") or "—"
        rating_color = RATING_COLORS.get(rating, "#6b7280")
        last_date = p.get("last_analysis_date") or "—"

        rows_html += (
            f"<tr>"
            f"<td style='padding:6px 12px;font-weight:600'>{ticker}</td>"
            f"<td style='padding:6px 12px'>{shares}</td>"
            f"<td style='padding:6px 12px'>{cost_str}</td>"
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
            <th style="padding:8px 12px;text-align:left">Buy Price</th>
            <th style="padding:8px 12px;text-align:left">Current</th>
            <th style="padding:8px 12px;text-align:left">Value</th>
            <th style="padding:8px 12px;text-align:left">P&L</th>
            <th style="padding:8px 12px;text-align:left">Rating</th>
            <th style="padding:8px 12px;text-align:left">Last Analysis</th>
        </tr></thead><tbody>{rows_html}</tbody></table>""",
        unsafe_allow_html=True,
    )

    if total_value:
        mc1, mc2, mc3 = st.columns(3)
        mc1.metric("Total Value", f"${total_value:,.0f}")
        if total_cost_value:
            mc2.metric("Total Cost", f"${total_cost_value:,.0f}")
            total_pnl = ((total_value - total_cost_value) / total_cost_value) * 100
            mc3.metric("Total P&L", f"{total_pnl:+.1f}%")

    st.divider()

    st.divider()

    # ── Per-position management (edit + remove) ───────────────────────────────
    st.markdown("### Manage Positions")
    for p in positions:
        pid = p["id"]
        cost_str = f" @ ${p['cost_basis']:.2f}" if p.get("cost_basis") else ""
        with st.expander(f"{p['ticker']} — {p['shares']} shares{cost_str}"):
            ec1, ec2 = st.columns(2)
            new_shares = ec1.number_input("Shares", min_value=0.01, value=float(p["shares"]),
                                         step=1.0, key=f"pf_edit_shares_{pid}")
            new_cost = ec2.number_input("Buy price ($/share)", min_value=0.01,
                                       value=float(p["cost_basis"]) if p.get("cost_basis") else 100.0,
                                       step=0.01, key=f"pf_edit_cost_{pid}")

            bc1, bc2 = st.columns(2)
            if bc1.button("💾 Save", key=f"pf_save_{pid}", use_container_width=True):
                update_position(p["ticker"], pid, new_shares, new_cost)
                st.success(f"Updated {p['ticker']}: {new_shares} shares @ ${new_cost:.2f}")
                st.rerun()
            if bc2.button("🗑 Remove", key=f"pf_remove_{pid}", use_container_width=True):
                remove_position(pid)
                st.rerun()


# ── Price fetching ────────────────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def _fetch_prices(tickers: list) -> Dict[str, float]:
    """Fetch current prices for all tickers."""
    if not tickers:
        return {}
    prices = {}
    try:
        import yfinance as yf
        import pandas as pd
        # Use 5d to handle weekends/holidays where 1d returns empty
        df = yf.download(tickers, period="5d", progress=False)
        if not df.empty:
            if len(tickers) == 1:
                if "Close" in df.columns and len(df) > 0:
                    close = df["Close"].iloc[-1]
                    if not pd.isna(close):
                        prices[tickers[0]] = float(close)
            else:
                for t in tickers:
                    try:
                        close = df[("Close", t)].iloc[-1]
                        if not pd.isna(close):
                            prices[t] = float(close)
                    except (KeyError, IndexError):
                        pass
    except Exception:
        pass

    # Fallback for any tickers still missing — use Ticker.info
    import yfinance as yf
    for t in tickers:
        if t not in prices:
            try:
                info = yf.Ticker(t).info
                p = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
                if p:
                    prices[t] = float(p)
            except Exception:
                pass
    return prices
