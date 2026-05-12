"""History view — browse past analyses and the memory/reflection log."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

from dashboard.utils import (
    RATING_COLORS, RATING_ORDER, list_history, load_memory_entries, rating_badge,
    sanitize_report,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _decision_card(rating: str, text: str):
    color = RATING_COLORS.get(rating, "#6b7280")
    st.markdown(
        f'<div style="background:{color}22;border:2px solid {color};'
        f'border-radius:10px;padding:14px;margin-bottom:12px">'
        f'<b style="color:{color};font-size:18px">Decision: {rating}</b>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _rating_pill(rating: str) -> str:
    """Return an HTML pill span colored by rating."""
    color = RATING_COLORS.get(rating, "#6b7280")
    return (
        f'<span style="background:{color}22;border:1px solid {color};color:{color};'
        f'padding:2px 10px;border-radius:10px;font-weight:700;font-size:13px">'
        f'{rating}</span>'
    )


def _render_run_detail(data: Dict[str, Any], record: Dict[str, Any]):
    """Render the full detail of a saved run, with action shortcuts."""
    import re as _re

    rating = data.get("_rating", "—")
    _decision_card(rating, data.get("final_trade_decision", ""))

    # ── Price target / time horizon metrics ───────────────────────────────────
    text = data.get("final_trade_decision", "")
    pt_match = _re.search(r'\*\*Price Target\*\*[:\s]+([^\n]+)', text)
    th_match = _re.search(r'\*\*Time Horizon\*\*[:\s]+([^\n]+)', text)
    if pt_match or th_match:
        mc = st.columns(2)
        if pt_match:
            mc[0].metric("🎯 Price Target", pt_match.group(1).strip())
        if th_match:
            mc[1].metric("⏳ Time Horizon", th_match.group(1).strip())

    # ── Shortcut buttons ──────────────────────────────────────────────────────
    b1, b2, _ = st.columns([1, 1, 3])
    if b1.button("💬 Open in Chat", key=f"open_chat_{record['ticker']}_{record['date']}",
                 use_container_width=True):
        st.session_state["chat_analysis_key"]   = None
        st.session_state["chat_prefill_ticker"] = record["ticker"]
        st.session_state["chat_prefill_date"]   = record["date"]
        st.session_state["_nav_target"] = "💬 Analysis Chat"
        st.rerun()

    if b2.button("🔄 Run Again", key=f"run_again_{record['ticker']}_{record['date']}",
                 use_container_width=True):
        st.session_state["st_ticker_validated"] = record["ticker"]
        st.session_state["_nav_target"] = "🔍 Single Ticker"
        st.rerun()

    st.divider()

    # Analyst reports
    analyst_sections = [
        ("📊 Market Analysis",    data.get("market_report")),
        ("📰 News Analysis",      data.get("news_report")),
        ("🏦 Fundamentals",       data.get("fundamentals_report")),
        ("💬 Social Sentiment",   data.get("sentiment_report")),
    ]
    available_analysts = [(l, c) for l, c in analyst_sections if c]
    if available_analysts:
        st.markdown("##### Analyst Reports")
        tabs = st.tabs([l for l, _ in available_analysts])
        for tab, (_, content) in zip(tabs, available_analysts):
            with tab:
                st.markdown(sanitize_report(content))

    # Research debate
    debate = data.get("investment_debate_state", {})
    if debate:
        with st.expander("🧠 Research Debate", expanded=False):
            d1, d2 = st.columns(2)
            with d1:
                st.markdown("**Bull Researcher**")
                st.markdown(sanitize_report(debate.get("bull_history") or "*No history*"))
            with d2:
                st.markdown("**Bear Researcher**")
                st.markdown(sanitize_report(debate.get("bear_history") or "*No history*"))
            if debate.get("judge_decision"):
                st.markdown("**Research Manager Decision**")
                st.markdown(sanitize_report(debate["judge_decision"]))

    # Trader plan
    if data.get("trader_investment_plan"):
        with st.expander("💼 Trader Plan", expanded=False):
            st.markdown(sanitize_report(data["trader_investment_plan"]))

    # Risk debate
    risk = data.get("risk_debate_state", {})
    if risk:
        with st.expander("⚖️ Risk Management Debate", expanded=False):
            r1, r2, r3 = st.columns(3)
            with r1:
                st.markdown("**Aggressive**")
                st.markdown(sanitize_report(risk.get("aggressive_history") or "*No history*"))
            with r2:
                st.markdown("**Conservative**")
                st.markdown(sanitize_report(risk.get("conservative_history") or "*No history*"))
            with r3:
                st.markdown("**Neutral**")
                st.markdown(sanitize_report(risk.get("neutral_history") or "*No history*"))

    # Final decision
    if data.get("final_trade_decision"):
        with st.expander("🎯 Final Portfolio Manager Decision", expanded=True):
            st.markdown(sanitize_report(data["final_trade_decision"]))


# ── Main view ─────────────────────────────────────────────────────────────────

def render_history():
    st.title("📜 History")
    st.caption("Browse past analyses and the memory/reflection log.")

    tab_runs, tab_memory = st.tabs(["📁 Past Analyses", "🧠 Memory & Reflections"])

    # ── Past Analyses tab ─────────────────────────────────────────────────────
    with tab_runs:
        records = list_history()

        if not records:
            st.info(
                "No past analyses found. Run an analysis from the **Single Ticker** "
                "or **Watchlist** view to see results here."
            )
        else:
            # ── Filters ───────────────────────────────────────────────────────
            f1, f2, f3 = st.columns([2, 2, 2])
            with f1:
                all_tickers = sorted({r["ticker"] for r in records})
                ticker_filter = st.multiselect("Filter by Ticker", all_tickers)
            with f2:
                rating_filter = st.multiselect("Filter by Rating", RATING_ORDER)
            with f3:
                sort_by = st.selectbox("Sort by", ["Date (newest)", "Date (oldest)", "Ticker", "Rating"])

            # Apply filters
            filtered = records
            if ticker_filter:
                filtered = [r for r in filtered if r["ticker"] in ticker_filter]
            if rating_filter:
                filtered = [r for r in filtered if r["rating"] in rating_filter]

            # Sort
            if sort_by == "Date (newest)":
                filtered = sorted(filtered, key=lambda r: r["date"], reverse=True)
            elif sort_by == "Date (oldest)":
                filtered = sorted(filtered, key=lambda r: r["date"])
            elif sort_by == "Ticker":
                filtered = sorted(filtered, key=lambda r: r["ticker"])
            elif sort_by == "Rating":
                filtered = sorted(filtered, key=lambda r: RATING_ORDER.index(r["rating"]) if r["rating"] in RATING_ORDER else 99)

            st.markdown(f"**{len(filtered)} run(s)** found")
            st.divider()

            # ── Summary table with colored rating pills ────────────────────────
            # Build HTML table for color-coded ratings
            rows_html = ""
            for r in filtered:
                pill = _rating_pill(r["rating"])
                rows_html += (
                    f"<tr>"
                    f"<td style='padding:6px 12px;font-weight:600'>{r['ticker']}</td>"
                    f"<td style='padding:6px 12px;color:#94a3b8'>{r['date']}</td>"
                    f"<td style='padding:6px 12px'>{pill}</td>"
                    f"</tr>"
                )
            st.markdown(
                f"""
                <table style="width:100%;border-collapse:collapse;
                              background:#1e293b;border-radius:8px;overflow:hidden;
                              margin-bottom:16px">
                  <thead>
                    <tr style="background:#0f172a;color:#64748b;font-size:12px;text-transform:uppercase">
                      <th style="padding:8px 12px;text-align:left">Ticker</th>
                      <th style="padding:8px 12px;text-align:left">Date</th>
                      <th style="padding:8px 12px;text-align:left">Decision</th>
                    </tr>
                  </thead>
                  <tbody>{rows_html}</tbody>
                </table>
                """,
                unsafe_allow_html=True,
            )

            st.divider()

            # ── Expandable detail per run ─────────────────────────────────────
            for r in filtered:
                color  = RATING_COLORS.get(r["rating"], "#6b7280")
                label  = f"**{r['ticker']}** — {r['date']} — {r['rating']}"
                with st.expander(label, expanded=False):
                    detail = dict(r["data"])
                    detail["_rating"] = r["rating"]
                    _render_run_detail(detail, r)

    # ── Memory & Reflections tab ──────────────────────────────────────────────
    with tab_memory:
        entries = load_memory_entries()

        if not entries:
            st.info(
                "No memory entries yet. The memory log is populated after analyses "
                "complete and outcomes are resolved on subsequent runs."
            )
        else:
            # Stats
            pending   = [e for e in entries if e.get("pending")]
            resolved  = [e for e in entries if not e.get("pending")]

            m1, m2, m3 = st.columns(3)
            m1.metric("Total Entries",    len(entries))
            m2.metric("Resolved",         len(resolved))
            m3.metric("Pending Outcome",  len(pending))

            st.divider()

            # ── Resolved entries with returns ─────────────────────────────────
            if resolved:
                st.markdown("#### Resolved Decisions (with actual returns)")

                import pandas as pd
                rows = []
                for e in resolved:
                    raw   = e.get("raw",   "n/a")
                    alpha = e.get("alpha", "n/a")
                    rows.append({
                        "Date":    e["date"],
                        "Ticker":  e["ticker"],
                        "Rating":  e["rating"],
                        "Raw Return":   raw,
                        "Alpha vs SPY": alpha,
                        "Holding":      e.get("holding", "n/a"),
                    })
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True, hide_index=True)

                # Expandable reflections
                st.markdown("#### Reflections")
                for e in reversed(resolved):
                    color = RATING_COLORS.get(e["rating"], "#6b7280")
                    label = f"**{e['ticker']}** — {e['date']} — {e['rating']} | raw: {e.get('raw','n/a')} | alpha: {e.get('alpha','n/a')}"
                    with st.expander(label, expanded=False):
                        if e.get("reflection"):
                            st.markdown(
                                f'<div style="background:#1e293b;border-left:4px solid {color};'
                                f'padding:12px 16px;border-radius:0 8px 8px 0;margin-bottom:12px">'
                                f'<b>Reflection</b><br>{e["reflection"]}'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                        if e.get("decision"):
                            with st.expander("Original Decision", expanded=False):
                                st.markdown(e["decision"])

            # ── Pending entries ───────────────────────────────────────────────
            if pending:
                st.divider()
                st.markdown("#### ⏳ Pending Outcome (awaiting next run)")
                for e in pending:
                    st.markdown(
                        f"- **{e['ticker']}** on {e['date']} — rated **{e['rating']}** "
                        f"*(outcome will be resolved on next {e['ticker']} run)*"
                    )
