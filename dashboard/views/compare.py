"""Side-by-side comparison of two saved analyses.

Pick any two analyses from history (same or different tickers, same or
different dates) and see their reports, ratings, and price charts
rendered in two columns for easy comparison.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Optional

import streamlit as st

from dashboard.utils import (
    RATING_COLORS, RATING_ORDER, list_history, sanitize_report,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rating_banner(rating: str) -> str:
    color = RATING_COLORS.get(rating, "#6b7280")
    return (
        f'<div style="background:{color}22;border:2px solid {color};border-radius:10px;'
        f'padding:12px 18px;text-align:center;margin-bottom:12px">'
        f'<span style="font-size:20px;font-weight:800;color:{color}">{rating}</span>'
        f'</div>'
    )


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_price(ticker: str, analysis_date: str):
    import yfinance as yf
    from datetime import datetime as _dt
    try:
        end   = _dt.strptime(analysis_date, "%Y-%m-%d").date()
        start = end - timedelta(days=180)
        df = yf.Ticker(ticker).history(
            start=start.strftime("%Y-%m-%d"),
            end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
        )
        if df.empty:
            df = yf.Ticker(ticker).history(period="6mo")
        return df if not df.empty else None
    except Exception:
        return None


def _mini_chart(ticker: str, analysis_date: str):
    """Render a compact line chart with the analysis date marked."""
    try:
        import plotly.graph_objects as go
    except ImportError:
        st.caption("Install plotly for charts")
        return

    df = _fetch_price(ticker, analysis_date)
    if df is None or df.empty:
        st.caption("No price data")
        return

    from datetime import datetime as _dt
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df.index, y=df["Close"],
        mode="lines",
        line=dict(color="#3b82f6", width=2),
        name="Close",
        fill="tozeroy",
        fillcolor="rgba(59,130,246,0.08)",
    ))
    # MA20
    ma20 = df["Close"].rolling(20).mean()
    fig.add_trace(go.Scatter(
        x=df.index, y=ma20,
        mode="lines",
        line=dict(color="#f59e0b", width=1, dash="dot"),
        name="MA20",
    ))
    try:
        ad = _dt.strptime(analysis_date, "%Y-%m-%d")
        fig.add_vline(
            x=ad.timestamp() * 1000,
            line_width=2, line_dash="dash", line_color="#ef4444",
            annotation_text="Analysis",
            annotation_font_color="#ef4444",
            annotation_position="top right",
        )
    except Exception:
        pass

    fig.update_layout(
        height=220,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0f172a",
        font=dict(color="#94a3b8", size=10),
        showlegend=False,
        xaxis=dict(gridcolor="#1e293b", rangeslider_visible=False),
        yaxis=dict(gridcolor="#1e293b"),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _render_side(data: Dict[str, Any], rating: str, label: str):
    """Render one side of the comparison."""
    ticker = data.get("company_of_interest", "—")
    date   = data.get("trade_date", "—")

    st.markdown(f"#### {label}: **{ticker}** · {date}")
    st.markdown(_rating_banner(rating), unsafe_allow_html=True)

    # Price chart
    _mini_chart(ticker, date)

    # Key metrics
    import re as _re
    text = data.get("final_trade_decision", "")
    pt = _re.search(r'\*\*Price Target\*\*[:\s]+([^\n]+)', text)
    th = _re.search(r'\*\*Time Horizon\*\*[:\s]+([^\n]+)', text)
    if pt or th:
        mc = st.columns(2)
        if pt: mc[0].metric("🎯 Price Target", pt.group(1).strip())
        if th: mc[1].metric("⏳ Time Horizon", th.group(1).strip())

    # Reports in expanders
    sections = [
        ("📊 Market",         data.get("market_report")),
        ("📰 News",           data.get("news_report")),
        ("🏦 Fundamentals",   data.get("fundamentals_report")),
        ("💬 Sentiment",      data.get("sentiment_report")),
        ("🧠 Research Plan",  data.get("investment_plan")),
        ("💼 Trader",         data.get("trader_investment_decision") or data.get("trader_investment_plan")),
        ("🎯 Final Decision", data.get("final_trade_decision")),
    ]
    available = [(lbl, c) for lbl, c in sections if c]
    if available:
        for lbl, content in available:
            with st.expander(lbl, expanded=(lbl == "🎯 Final Decision")):
                st.markdown(sanitize_report(content))


# ── Main view ─────────────────────────────────────────────────────────────────

def render_compare():
    st.title("⚖️ Compare Analyses")
    st.caption("Pick any two saved analyses and compare them side by side.")

    records = list_history()
    if len(records) < 2:
        st.info("You need at least 2 saved analyses to compare. Run more analyses first.")
        return

    # Build option labels
    options = {
        f"{r['ticker']}  ·  {r['date']}  [{r['rating']}]": r
        for r in records
    }
    labels = list(options.keys())

    # Ticker filter above dropdowns
    col_a, col_b = st.columns(2)
    with col_a:
        filter_a = st.text_input("Filter A by ticker", key="cmp_filter_a", placeholder="e.g. NVDA")
        filtered_labels_a = [l for l in labels if not filter_a or filter_a.upper() in l.upper()]
        if not filtered_labels_a:
            st.info("No analyses match this filter")
            return
        sel_a = st.selectbox("Analysis A", filtered_labels_a, index=0, key="cmp_a")
    with col_b:
        filter_b = st.text_input("Filter B by ticker", key="cmp_filter_b", placeholder="e.g. AAPL")
        filtered_labels_b = [l for l in labels if not filter_b or filter_b.upper() in l.upper()]
        if not filtered_labels_b:
            st.info("No analyses match this filter")
            return
        sel_b = st.selectbox("Analysis B", filtered_labels_b,
                             index=min(1, len(filtered_labels_b) - 1), key="cmp_b")

    if sel_a == sel_b:
        st.warning("Select two different analyses to compare.")
        return

    rec_a = options[sel_a]
    rec_b = options[sel_b]

    st.divider()

    # ── Comparison table ──────────────────────────────────────────────────────
    from dashboard.utils import compute_conviction
    import re as _cmp_re

    def _extract_field(text, pattern):
        m = _cmp_re.search(pattern, text or "")
        return m.group(1).strip() if m else "—"

    dec_a = rec_a["data"].get("final_trade_decision", "")
    dec_b = rec_b["data"].get("final_trade_decision", "")
    conv_a, _ = compute_conviction(rec_a["data"])
    conv_b, _ = compute_conviction(rec_b["data"])
    pt_a = _extract_field(dec_a, r'(?i)\*\*Price\s+Target\*\*[:\s]*([^\n]+)')
    pt_b = _extract_field(dec_b, r'(?i)\*\*Price\s+Target\*\*[:\s]*([^\n]+)')
    th_a = _extract_field(dec_a, r'(?i)\*\*Time\s+Horizon\*\*[:\s]*([^\n]+)')
    th_b = _extract_field(dec_b, r'(?i)\*\*Time\s+Horizon\*\*[:\s]*([^\n]+)')

    color_a = RATING_COLORS.get(rec_a["rating"], "#6b7280")
    color_b = RATING_COLORS.get(rec_b["rating"], "#6b7280")
    idx_a = RATING_ORDER.index(rec_a["rating"]) if rec_a["rating"] in RATING_ORDER else 2
    idx_b = RATING_ORDER.index(rec_b["rating"]) if rec_b["rating"] in RATING_ORDER else 2

    if idx_a < idx_b:
        verdict = f"A is more bullish ({rec_a['rating']} vs {rec_b['rating']})"
        verdict_color = color_a
    elif idx_b < idx_a:
        verdict = f"B is more bullish ({rec_b['rating']} vs {rec_a['rating']})"
        verdict_color = color_b
    else:
        verdict = f"Same rating — both {rec_a['rating']}"
        verdict_color = color_a

    st.markdown(
        f"""<table style="width:100%;border-collapse:collapse;background:#1e293b;border-radius:8px;overflow:hidden;margin-bottom:16px">
        <thead><tr style="background:#0f172a;color:#64748b;font-size:12px;text-transform:uppercase">
            <th style="padding:8px 12px;text-align:left">Metric</th>
            <th style="padding:8px 12px;text-align:center">A: {rec_a['ticker']}</th>
            <th style="padding:8px 12px;text-align:center">B: {rec_b['ticker']}</th>
        </tr></thead>
        <tbody>
            <tr><td style="padding:6px 12px">Rating</td>
                <td style="padding:6px 12px;text-align:center;color:{color_a};font-weight:700">{rec_a['rating']}</td>
                <td style="padding:6px 12px;text-align:center;color:{color_b};font-weight:700">{rec_b['rating']}</td></tr>
            <tr><td style="padding:6px 12px">Conviction</td>
                <td style="padding:6px 12px;text-align:center">{conv_a}</td>
                <td style="padding:6px 12px;text-align:center">{conv_b}</td></tr>
            <tr><td style="padding:6px 12px">Price Target</td>
                <td style="padding:6px 12px;text-align:center">{pt_a}</td>
                <td style="padding:6px 12px;text-align:center">{pt_b}</td></tr>
            <tr><td style="padding:6px 12px">Time Horizon</td>
                <td style="padding:6px 12px;text-align:center">{th_a}</td>
                <td style="padding:6px 12px;text-align:center">{th_b}</td></tr>
            <tr style="background:#0f172a"><td style="padding:8px 12px;font-weight:700">Verdict</td>
                <td colspan="2" style="padding:8px 12px;text-align:center;color:{verdict_color};font-weight:700">{verdict}</td></tr>
        </tbody></table>""",
        unsafe_allow_html=True,
    )

    # ── Side-by-side columns ──────────────────────────────────────────────────
    left, right = st.columns(2)
    with left:
        _render_side(rec_a["data"], rec_a["rating"], "A")
    with right:
        _render_side(rec_b["data"], rec_b["rating"], "B")

    # ── Open in Chat shortcuts ────────────────────────────────────────────────
    st.divider()
    ca, cb, cc = st.columns([1, 1, 1])
    if ca.button("💬 Chat about A", use_container_width=True):
        st.session_state["chat_analysis_key"]   = None
        st.session_state["chat_prefill_ticker"] = rec_a["ticker"]
        st.session_state["chat_prefill_date"]   = rec_a["date"]
        st.session_state["_nav_target"] = "💬 Analysis Chat"
        st.rerun()
    if cb.button("💬 Chat about B", use_container_width=True):
        st.session_state["chat_analysis_key"]   = None
        st.session_state["chat_prefill_ticker"] = rec_b["ticker"]
        st.session_state["chat_prefill_date"]   = rec_b["date"]
        st.session_state["_nav_target"] = "💬 Analysis Chat"
        st.rerun()
    if cc.button("💬 Compare both in Chat", use_container_width=True, type="primary"):
        st.session_state["chat_multi_prefill"] = [
            f"{rec_a['ticker']}|{rec_a['date']}",
            f"{rec_b['ticker']}|{rec_b['date']}",
        ]
        st.session_state["_nav_target"] = "💬 Analysis Chat"
        st.rerun()
