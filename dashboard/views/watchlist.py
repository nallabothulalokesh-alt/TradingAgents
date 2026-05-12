"""Multi-Ticker Watchlist view.

Improvements:
- Per-ticker date override (each ticker can have its own analysis date)
- Ticker validation before adding to queue (invalid tickers rejected upfront)
- Remove individual items from the queue
- Color-coded results table
- Overall queue progress bar
"""

from __future__ import annotations

import threading
import time
from datetime import date
from typing import Any, Dict, List, Optional

import streamlit as st

from dashboard.utils import (
    ALL_ANALYSTS, DASHBOARD_CONFIG, RATING_COLORS,
    validate_ticker, invalidate_history_cache,
)
from dashboard.runner import run_analysis, RunState

# Thread-safe buffer: background threads append here; main thread drains into session_state
_results_buffer: List[Dict[str, Any]] = []
_results_lock = threading.Lock()


# ── Session-state helpers ─────────────────────────────────────────────────────

def _init_wl():
    defaults = {
        "wl_queue":   [],
        "wl_results": [],
        "wl_current": None,
        "wl_running": False,
        "wl_thread":  None,
        "wl_total":   0,   # total items when queue was started (for progress bar)
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _dispatch_next():
    """Start the next queued item. MUST be called from main thread only."""
    queue = st.session_state["wl_queue"]
    if not queue:
        st.session_state["wl_running"] = False
        st.session_state["wl_current"] = None
        invalidate_history_cache()
        return

    item = queue.pop(0)
    rs   = RunState()
    st.session_state["wl_current"] = rs
    st.session_state["wl_running"] = True

    def _worker():
        run_analysis(rs, item["ticker"], item["date"], item["analysts"], item["config"])
        # Wait for run_analysis background thread to finish
        while rs.snapshot()["running"]:
            time.sleep(1)
        # Append result to module-level buffer (thread-safe)
        snap = rs.snapshot()
        result = {
            "ticker":      snap["ticker"],
            "date":        snap["trade_date"],
            "decision":    snap["decision"] or "—",
            "error":       snap["error"],
            "final_state": snap["final_state"],
        }
        with _results_lock:
            _results_buffer.append(result)
        # Do NOT call _dispatch_next() here — main thread handles advancement

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    st.session_state["wl_thread"] = t


def _drain_results_and_advance():
    """Drain completed results from buffer and advance queue. Main thread only."""
    with _results_lock:
        pending = list(_results_buffer)
        _results_buffer.clear()
    if pending:
        st.session_state["wl_results"].extend(pending)
    # If current run is done and there are more items, start next
    current: Optional[RunState] = st.session_state.get("wl_current")
    if current is not None and not current.snapshot()["running"]:
        if pending or current.snapshot()["done"]:
            _dispatch_next()


def _rating_pill(rating: str) -> str:
    color = RATING_COLORS.get(rating, "#6b7280")
    return (
        f'<span style="background:{color}22;border:1px solid {color};color:{color};'
        f'padding:2px 10px;border-radius:10px;font-weight:700;font-size:13px">{rating}</span>'
    )


# ── Main view ─────────────────────────────────────────────────────────────────

def render_watchlist():
    st.title("📋 Watchlist")
    st.caption("Queue multiple tickers — they run one at a time and results accumulate below.")

    _init_wl()

    # Drain completed results and advance queue (main thread only)
    _drain_results_and_advance()

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### Add Tickers")

        raw_tickers = st.text_area(
            "Tickers (one per line or comma-separated)",
            placeholder="NVDA\nAAPL\nTSLA",
            height=100,
        )

        use_per_ticker_date = st.toggle(
            "Per-ticker date override",
            value=False,
            help="When off, all tickers share one date. When on, enter date after each ticker: NVDA 2026-05-01",
        )

        if not use_per_ticker_date:
            wl_date = st.date_input(
                "Analysis Date (all tickers)",
                value=date.today(),
                max_value=date.today(),
                key="wl_date",
            ).strftime("%Y-%m-%d")
        else:
            wl_date = date.today().strftime("%Y-%m-%d")
            st.caption("Format: `TICKER YYYY-MM-DD` per line, e.g. `NVDA 2026-05-01`")

        validate_before_queue = st.toggle(
            "✅ Validate tickers before queuing",
            value=True,
            help="Checks each ticker against yfinance before adding. Adds a few seconds but prevents mid-run failures.",
        )

        st.markdown("**Analysts**")
        wl_analysts = {
            a: st.checkbox(a.capitalize(),
                           value=(a in ["market", "news", "fundamentals"]),
                           key=f"wl_analyst_{a}")
            for a in ALL_ANALYSTS
        }
        selected_analysts = [a for a, checked in wl_analysts.items() if checked]

        st.markdown("**LLM Provider**")
        wl_provider = st.selectbox(
            "Provider",
            ["OpenAI", "Google", "Anthropic", "DeepSeek", "xAI", "Ollama"],
            index=3,
            key="wl_provider",
        )
        WL_MODELS = {
            "OpenAI":    {"deep": ["gpt-5.4", "gpt-4o"],           "quick": ["gpt-5.4-mini", "gpt-4o-mini"]},
            "Google":    {"deep": ["gemini-3.1-pro", "gemini-2.5-pro"], "quick": ["gemini-3.1-flash", "gemini-2.5-flash"]},
            "Anthropic": {"deep": ["claude-4.6-sonnet", "claude-4-opus"], "quick": ["claude-4.6-haiku"]},
            "DeepSeek":  {"deep": ["deepseek-v4-pro", "deepseek-chat"], "quick": ["deepseek-v4-flash", "deepseek-chat"]},
            "xAI":       {"deep": ["grok-4-turbo", "grok-4"],      "quick": ["grok-4-turbo"]},
            "Ollama":    {"deep": ["llama3.1:70b", "llama3.1:8b"], "quick": ["llama3.1:8b", "mistral:latest"]},
        }
        pm = WL_MODELS.get(wl_provider, WL_MODELS["DeepSeek"])
        deep_model  = st.selectbox("Deep thinker",  pm["deep"],  index=0, key="wl_deep")
        quick_model = st.selectbox("Quick thinker", pm["quick"], index=0, key="wl_quick")

        st.markdown("**Output Language**")
        wl_language = st.selectbox(
            "Language",
            ["English", "Spanish", "French", "German", "Japanese",
             "Chinese (Simplified)", "Korean", "Portuguese", "Hindi"],
            index=0, key="wl_language", label_visibility="collapsed",
        )

        st.divider()

        if st.button("➕ Add to Queue", use_container_width=True,
                     disabled=st.session_state["wl_running"]):
            lines = [
                l.strip()
                for part in raw_tickers.replace(",", "\n").splitlines()
                for l in [part.strip()] if l.strip()
            ]

            added, skipped = 0, []
            for line in lines:
                parts = line.split()
                ticker = parts[0].upper()

                # Parse per-ticker date if provided
                item_date = wl_date
                if use_per_ticker_date and len(parts) >= 2:
                    try:
                        from datetime import datetime as _dt
                        _dt.strptime(parts[1], "%Y-%m-%d")
                        item_date = parts[1]
                    except ValueError:
                        pass

                # Validate if requested
                if validate_before_queue:
                    with st.spinner(f"Validating {ticker}…"):
                        ok, msg = validate_ticker(ticker)
                    if not ok:
                        skipped.append(f"{ticker}: {msg}")
                        continue

                cfg = {
                    **DASHBOARD_CONFIG,
                    "llm_provider":    wl_provider.lower(),
                    "deep_think_llm":  deep_model,
                    "quick_think_llm": quick_model,
                    "output_language": wl_language,
                }
                st.session_state["wl_queue"].append({
                    "ticker":   ticker,
                    "date":     item_date,
                    "analysts": selected_analysts,
                    "config":   cfg,
                })
                added += 1

            if added:
                st.success(f"Added {added} ticker(s) to queue.")
            for s in skipped:
                st.error(s)

        col_start, col_clear = st.columns(2)
        with col_start:
            if st.button("▶ Start", use_container_width=True, type="primary",
                         disabled=st.session_state["wl_running"] or not st.session_state["wl_queue"]):
                st.session_state["wl_total"] = len(st.session_state["wl_queue"])
                _dispatch_next()
                st.rerun()
        with col_clear:
            if st.button("🗑 Clear", use_container_width=True,
                         disabled=st.session_state["wl_running"]):
                st.session_state["wl_queue"]   = []
                st.session_state["wl_results"] = []
                st.session_state["wl_current"] = None
                st.session_state["wl_running"] = False
                st.session_state["wl_total"]   = 0
                st.rerun()

    # ── Summary metrics ───────────────────────────────────────────────────────
    queue   = st.session_state["wl_queue"]
    results = st.session_state["wl_results"]
    current: Optional[RunState] = st.session_state["wl_current"]
    total   = st.session_state.get("wl_total", 0)
    errors  = sum(1 for r in results if r.get("error"))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Queued",    len(queue))
    m2.metric("Completed", len(results))
    m3.metric("Running",   "Yes" if st.session_state["wl_running"] else "No")
    m4.metric("Errors",    errors)

    # Overall progress bar
    if total > 0:
        done = len(results)
        pct  = done / total
        st.progress(pct, text=f"Overall: {done} / {total} complete")

    st.divider()

    # ── Currently running ─────────────────────────────────────────────────────
    if current is not None:
        snap = current.snapshot()
        if snap["running"]:
            st.markdown("#### 🔄 Currently Running")
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"**{snap['ticker']}** — {snap['trade_date']}")
                done_a  = sum(1 for s in snap["agent_status"].values() if s == "done")
                total_a = len(snap["agent_status"])
                if total_a:
                    st.progress(done_a / total_a, text=f"{done_a}/{total_a} agents")
            with c2:
                last_log = snap["log_lines"][-1] if snap["log_lines"] else "Starting…"
                st.caption(last_log)
            st.divider()

    # ── Pending queue ─────────────────────────────────────────────────────────
    if queue:
        st.markdown("#### ⏳ Pending Queue")
        for i, item in enumerate(queue):
            c1, c2 = st.columns([5, 1])
            c1.markdown(
                f"`{i+1}.` **{item['ticker']}** — {item['date']} "
                f"| analysts: {', '.join(item['analysts'])}"
            )
            if c2.button("✕", key=f"remove_{i}_{item['ticker']}",
                         help="Remove from queue"):
                st.session_state["wl_queue"].pop(i)
                st.rerun()
        st.divider()

    # ── Results ───────────────────────────────────────────────────────────────
    if results:
        st.markdown("#### ✅ Completed Analyses")

        # Color-coded HTML summary table
        rows_html = ""
        for r in results:
            rating = r["decision"] or "—"
            pill   = _rating_pill(rating)
            status = "❌ Error" if r["error"] else "✅ Done"
            rows_html += (
                f"<tr>"
                f"<td style='padding:6px 12px;font-weight:600'>{r['ticker']}</td>"
                f"<td style='padding:6px 12px;color:#94a3b8'>{r['date']}</td>"
                f"<td style='padding:6px 12px'>{pill}</td>"
                f"<td style='padding:6px 12px'>{status}</td>"
                f"</tr>"
            )
        st.markdown(
            f"""
            <table style="width:100%;border-collapse:collapse;background:#1e293b;
                          border-radius:8px;overflow:hidden;margin-bottom:16px">
              <thead>
                <tr style="background:#0f172a;color:#64748b;font-size:12px;text-transform:uppercase">
                  <th style="padding:8px 12px;text-align:left">Ticker</th>
                  <th style="padding:8px 12px;text-align:left">Date</th>
                  <th style="padding:8px 12px;text-align:left">Decision</th>
                  <th style="padding:8px 12px;text-align:left">Status</th>
                </tr>
              </thead>
              <tbody>{rows_html}</tbody>
            </table>
            """,
            unsafe_allow_html=True,
        )

        # Expandable detail per result
        st.markdown("#### Detailed Results")
        for r in reversed(results):
            rating = r["decision"] or "—"
            color  = RATING_COLORS.get(rating, "#6b7280")
            label  = f"**{r['ticker']}** — {r['date']} — {rating}"
            with st.expander(label):
                if r["error"]:
                    st.error(f"Error: {r['error']}")
                elif r["final_state"]:
                    fs = r["final_state"]
                    st.markdown(
                        f'<div style="background:{color}22;border:2px solid {color};'
                        f'border-radius:10px;padding:14px;margin-bottom:12px">'
                        f'<b style="color:{color};font-size:18px">Decision: {rating}</b>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    sections = [
                        ("📊 Market",         fs.get("market_report")),
                        ("📰 News",           fs.get("news_report")),
                        ("🏦 Fundamentals",   fs.get("fundamentals_report")),
                        ("💬 Sentiment",      fs.get("sentiment_report")),
                        ("🧠 Research Plan",  fs.get("investment_plan")),
                        ("💼 Trader",         fs.get("trader_investment_plan")),
                        ("🎯 Final Decision", fs.get("final_trade_decision")),
                    ]
                    available = [(lbl, c) for lbl, c in sections if c]
                    if available:
                        tabs = st.tabs([lbl for lbl, _ in available])
                        for tab, (_, content) in zip(tabs, available):
                            with tab:
                                from dashboard.utils import sanitize_report
                                st.markdown(sanitize_report(content))

                    # Open in Chat shortcut
                    if st.button("💬 Open in Chat",
                                 key=f"wl_chat_{r['ticker']}_{r['date']}",
                                 use_container_width=False):
                        st.session_state["chat_analysis_key"]   = None
                        st.session_state["chat_prefill_ticker"] = r["ticker"]
                        st.session_state["chat_prefill_date"]   = r["date"]
                        st.session_state["_nav_target"] = "💬 Analysis Chat"
                        st.rerun()

    elif not st.session_state["wl_running"]:
        st.info("Add tickers in the sidebar and press **▶ Start** to begin.")

    # ── Auto-refresh while running ────────────────────────────────────────────
    if st.session_state["wl_running"]:
        time.sleep(3)
        st.rerun()
