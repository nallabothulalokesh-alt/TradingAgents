"""History view — browse past analyses and the memory/reflection log."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

from dashboard.utils import (
    RATING_COLORS, RATING_ORDER, list_history, load_memory_entries, rating_badge,
    sanitize_report, render_decision_first,
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
            f1, f2, f3, f4 = st.columns([2, 2, 2, 2])
            with f1:
                ticker_search = st.text_input("🔍 Search ticker", key="hist_search",
                                             placeholder="e.g. NVDA")
            with f2:
                rating_filter = st.multiselect("Filter by Rating", RATING_ORDER)
            with f3:
                from datetime import datetime as _dt, timedelta as _td
                date_from = st.date_input("From date",
                                         value=_dt.today().date() - _td(days=90),
                                         key="hist_date_from")
            with f4:
                date_to = st.date_input("To date",
                                       value=_dt.today().date(),
                                       key="hist_date_to")

            # Return filter (only when SQLite has memory data)
            from dashboard.db import is_db_available, load_memory_entries_db
            show_return_filter = False
            if is_db_available():
                memory_entries = load_memory_entries_db()
                if any(e.get("raw_return") is not None for e in memory_entries):
                    show_return_filter = True

            min_return = None
            if show_return_filter:
                min_return = st.slider("Min return %", -50, 100, -50, key="hist_return_filter",
                                      help="Filter by actual return (requires resolved memory entries)")

            sort_by = st.selectbox("Sort by", ["Date (newest)", "Date (oldest)", "Ticker", "Rating"])

            # Apply filters
            filtered = records
            if ticker_search:
                filtered = [r for r in filtered if ticker_search.upper() in r["ticker"].upper()]
            if rating_filter:
                filtered = [r for r in filtered if r["rating"] in rating_filter]
            if date_from:
                filtered = [r for r in filtered if r["date"] >= date_from.strftime("%Y-%m-%d")]
            if date_to:
                filtered = [r for r in filtered if r["date"] <= date_to.strftime("%Y-%m-%d")]

            # Return filter — join with memory entries
            if min_return is not None and min_return > -50 and show_return_filter:
                memory_map = {(e["ticker"], e["trade_date"]): e.get("raw_return")
                             for e in memory_entries if e.get("raw_return") is not None}
                filtered = [r for r in filtered
                           if memory_map.get((r["ticker"], r["date"]), -999) >= min_return / 100]

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
                    # Action buttons
                    b1, b2, b3 = st.columns([1, 1, 1])
                    if b1.button("💬 Open in Chat", key=f"open_chat_{r['ticker']}_{r['date']}",
                                 use_container_width=True):
                        st.session_state["chat_analysis_key"]   = None
                        st.session_state["chat_prefill_ticker"] = r["ticker"]
                        st.session_state["chat_prefill_date"]   = r["date"]
                        st.session_state["_nav_target"] = "💬 Analysis Chat"
                        st.rerun()
                    if b2.button("🔄 Run Again", key=f"run_again_{r['ticker']}_{r['date']}",
                                 use_container_width=True):
                        st.session_state["st_ticker_validated"] = r["ticker"]
                        st.session_state["st_prefill_date"] = r["date"]
                        st.session_state["_nav_target"] = "🔍 Single Ticker"
                        st.rerun()
                    # Export report as text file
                    data = r["data"]
                    report_lines = [
                        f"TradingAgents Analysis Report",
                        f"Ticker: {r['ticker']}  |  Date: {r['date']}  |  Rating: {r['rating']}",
                        "=" * 60, "",
                    ]
                    for section, label in [
                        ("market_report", "MARKET ANALYSIS"),
                        ("news_report", "NEWS ANALYSIS"),
                        ("fundamentals_report", "FUNDAMENTALS"),
                        ("sentiment_report", "SOCIAL SENTIMENT"),
                        ("investment_plan", "RESEARCH DECISION"),
                        ("trader_investment_plan", "TRADER PLAN"),
                        ("final_trade_decision", "FINAL DECISION"),
                    ]:
                        content = data.get(section) or data.get("trader_investment_decision", "") if section == "trader_investment_plan" else data.get(section)
                        if content:
                            report_lines.extend([f"\n{'─' * 40}", f"## {label}", "─" * 40, content, ""])
                    b3.download_button(
                        "📄 Export Report",
                        data="\n".join(report_lines),
                        file_name=f"report_{r['ticker']}_{r['date']}.txt",
                        mime="text/plain",
                        key=f"export_{r['ticker']}_{r['date']}",
                        use_container_width=True,
                    )
                    st.divider()
                    # Decision-first layout
                    render_decision_first(r["data"])

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
