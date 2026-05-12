"""Multi-Ticker Analysis view (formerly Watchlist).

Features:
- Parallel execution via WorkerPool (configurable concurrency 1-5)
- Per-ticker date override
- Ticker validation before queuing
- Import from Portfolio
- Skip button per active ticker
- Rating distribution chart
- Fast Mode for batch
- Mid-batch ticker addition
- Global run guard
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any, Dict, List, Optional

import streamlit as st

from dashboard.utils import (
    ALL_ANALYSTS, DASHBOARD_CONFIG, RATING_COLORS,
    validate_ticker, invalidate_history_cache, find_recent_run,
    fast_mode_summary, check_stale_fundamentals, sanitize_report,
)
from dashboard.worker_pool import WorkerPool


# ── Session-state helpers ─────────────────────────────────────────────────────

def _init_wl():
    defaults = {
        "wl_queue": [],
        "wl_results": [],
        "wl_running": False,
        "wl_total": 0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if "_wl_session_id" not in st.session_state:
        from uuid import uuid4
        st.session_state["_wl_session_id"] = str(uuid4())
    if "_wl_pool" not in st.session_state:
        st.session_state["_wl_pool"] = WorkerPool(
            st.session_state["_wl_session_id"], max_concurrency=3
        )


def _get_pool() -> WorkerPool:
    return st.session_state["_wl_pool"]


def _dispatch_from_queue():
    """Dispatch items from queue into pool slots. Main thread only."""
    pool = _get_pool()
    queue = st.session_state["wl_queue"]
    while queue and pool.active_count() < pool.max_concurrency:
        item = queue.pop(0)
        pool.dispatch(
            item["ticker"], item["date"], item["analysts"], item["config"],
            prior_run=item.get("prior_run"),
        )


def _drain_and_advance():
    """Drain completed results and dispatch more. Main thread only."""
    pool = _get_pool()
    results = pool.drain_results()
    if results:
        st.session_state["wl_results"].extend(results)
    # Dispatch more from queue
    _dispatch_from_queue()
    # Update running state
    st.session_state["wl_running"] = not pool.is_idle() or bool(st.session_state["wl_queue"])


def _rating_pill(rating: str) -> str:
    color = RATING_COLORS.get(rating, "#6b7280")
    return (
        f'<span style="background:{color}22;border:1px solid {color};color:{color};'
        f'padding:2px 10px;border-radius:10px;font-weight:700;font-size:13px">{rating}</span>'
    )


# ── Main view ─────────────────────────────────────────────────────────────────

def render_watchlist():
    st.title("📊 Multi-Ticker Analysis")
    st.caption("Queue multiple tickers — they run in parallel and results accumulate below.")

    _init_wl()
    _drain_and_advance()

    pool = _get_pool()
    is_running = st.session_state["wl_running"]

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### Add Tickers")

        raw_tickers = st.text_area(
            "Tickers (one per line or comma-separated)",
            placeholder="NVDA\nAAPL\nTSLA",
            height=100,
        )

        use_per_ticker_date = st.toggle(
            "Per-ticker date override", value=False,
            help="Format: TICKER YYYY-MM-DD per line",
        )

        if not use_per_ticker_date:
            wl_date = st.date_input(
                "Analysis Date (all tickers)", value=date.today(),
                max_value=date.today(), key="wl_date",
            ).strftime("%Y-%m-%d")
        else:
            wl_date = date.today().strftime("%Y-%m-%d")
            st.caption("Format: `TICKER YYYY-MM-DD` per line")

        validate_before_queue = st.toggle("✅ Validate tickers before queuing", value=True)

        st.markdown("**Analysts**")
        wl_analysts = {
            a: st.checkbox(a.capitalize(),
                           value=(a in ["market", "news", "fundamentals"]),
                           key=f"wl_analyst_{a}")
            for a in ALL_ANALYSTS
        }
        selected_analysts = [a for a, checked in wl_analysts.items() if checked]

        # Max Concurrency slider
        st.markdown("**Concurrency**")
        max_conc = st.slider("Max parallel analyses", 1, 5, pool.max_concurrency, key="wl_concurrency")
        pool.update_max_concurrency(max_conc)

        st.markdown("**LLM Provider**")
        wl_provider = st.selectbox(
            "Provider", ["OpenAI", "Google", "Anthropic", "DeepSeek", "xAI", "Ollama"],
            index=3, key="wl_provider",
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
        deep_model = st.selectbox("Deep thinker", pm["deep"], index=0, key="wl_deep")
        quick_model = st.selectbox("Quick thinker", pm["quick"], index=0, key="wl_quick")

        # Fast Mode
        st.divider()
        st.markdown("**Analysis Mode**")
        fast_mode_on = st.toggle("⚡ Fast Mode", value=False, key="wl_fast_mode")
        fast_mode_days = 7
        if fast_mode_on:
            fast_mode_days = st.slider("Max days to look back", 1, 14, 7, key="wl_fast_days")

        st.divider()

        # Add to Queue button (enabled even during batch for mid-batch addition)
        if st.button("➕ Add to Queue", use_container_width=True):
            _add_tickers_to_queue(
                raw_tickers, use_per_ticker_date, wl_date, validate_before_queue,
                selected_analysts, wl_provider, deep_model, quick_model,
                fast_mode_on, fast_mode_days,
            )

        # Import from Portfolio
        if st.button("📥 Import from Portfolio", use_container_width=True):
            try:
                from dashboard.db import is_db_available
                if is_db_available():
                    from dashboard.db import get_db
                    conn = get_db()
                    rows = conn.execute("SELECT ticker FROM portfolio_positions").fetchall()
                    if rows:
                        tickers = [r["ticker"] for r in rows]
                        st.session_state["_wl_import_tickers"] = "\n".join(tickers)
                        st.success(f"Imported {len(tickers)} tickers from portfolio")
                    else:
                        st.info("No portfolio positions found. Add positions in the Portfolio view.")
                else:
                    st.info("Portfolio not available (SQLite not initialized)")
            except Exception:
                st.info("Portfolio not available")

        # Show imported tickers if any
        if st.session_state.get("_wl_import_tickers"):
            st.text_area("Imported tickers", st.session_state.pop("_wl_import_tickers"), height=60)

        col_start, col_clear = st.columns(2)
        with col_start:
            if st.button("▶ Start", use_container_width=True, type="primary",
                         disabled=is_running or not st.session_state["wl_queue"]):
                st.session_state["wl_total"] = len(st.session_state["wl_queue"])
                st.session_state["wl_running"] = True
                st.session_state["_global_run_active"] = True
                _dispatch_from_queue()
                st.rerun()
        with col_clear:
            if st.button("🗑 Clear All", use_container_width=True, disabled=is_running):
                st.session_state["wl_queue"] = []
                st.session_state["wl_results"] = []
                st.session_state["wl_running"] = False
                st.session_state["wl_total"] = 0
                st.session_state.pop("_global_run_active", None)
                st.rerun()

        if is_running:
            if st.button("⏹ Cancel All", use_container_width=True):
                pool.cancel_all()
                st.session_state["wl_queue"] = []
                st.session_state["wl_running"] = False
                st.session_state.pop("_global_run_active", None)
                st.rerun()

    # ── Summary metrics ───────────────────────────────────────────────────────
    queue = st.session_state["wl_queue"]
    results = st.session_state["wl_results"]
    total = st.session_state.get("wl_total", 0)
    active = pool.active_count()
    errors = sum(1 for r in results if r.get("error"))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Queued", len(queue))
    m2.metric("Active", active)
    m3.metric("Completed", len(results))
    m4.metric("Errors", errors)

    # Overall progress bar
    if total > 0:
        done = len(results)
        st.progress(done / total, text=f"Overall: {done}/{total} complete")

    st.divider()

    # ── Currently running (with Skip buttons) ─────────────────────────────────
    active_tickers = pool.active_tickers()
    if active_tickers:
        st.markdown("#### 🔄 Currently Running")
        for ticker, rs in active_tickers.items():
            snap = rs.snapshot()
            c1, c2, c3 = st.columns([3, 1, 1])
            with c1:
                st.markdown(f"**{snap['ticker']}** — {snap['trade_date']}")
                done_a = sum(1 for s in snap["agent_status"].values() if s in ("done", "reused"))
                total_a = len(snap["agent_status"]) or 1
                st.progress(done_a / total_a, text=f"{done_a}/{total_a} agents")
            with c2:
                last_log = snap["log_lines"][-1] if snap["log_lines"] else "Starting…"
                st.caption(last_log[:50])
            with c3:
                if st.button("⏭ Skip", key=f"skip_{ticker}", use_container_width=True):
                    pool.cancel(ticker)
                    st.rerun()
        st.divider()

    # ── Pending queue ─────────────────────────────────────────────────────────
    if queue:
        st.markdown("#### ⏳ Pending Queue")
        for i, item in enumerate(queue):
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"`{i+1}.` **{item['ticker']}** — {item['date']}")
            if c2.button("✕", key=f"remove_{i}_{item['ticker']}", help="Remove"):
                st.session_state["wl_queue"].pop(i)
                st.rerun()
        st.divider()

    # ── Results ───────────────────────────────────────────────────────────────
    if results:
        st.markdown("#### ✅ Completed Analyses")

        # Rating distribution chart
        if len(results) >= 2:
            from collections import Counter
            rating_counts = Counter(r["decision"] for r in results if r["decision"] != "—")
            if rating_counts:
                chart_cols = st.columns(len(rating_counts))
                for col, (rating, count) in zip(chart_cols, sorted(rating_counts.items())):
                    color = RATING_COLORS.get(rating, "#6b7280")
                    col.markdown(
                        f'<div style="text-align:center;background:{color}22;border:1px solid {color};'
                        f'border-radius:8px;padding:8px">'
                        f'<div style="font-size:24px;font-weight:800;color:{color}">{count}</div>'
                        f'<div style="font-size:12px;color:{color}">{rating}</div></div>',
                        unsafe_allow_html=True,
                    )
                st.divider()

        # Results table
        rows_html = ""
        for r in results:
            rating = r["decision"] or "—"
            pill = _rating_pill(rating)
            status = "❌ Error" if r["error"] else "✅ Done"
            rows_html += (
                f"<tr><td style='padding:6px 12px;font-weight:600'>{r['ticker']}</td>"
                f"<td style='padding:6px 12px;color:#94a3b8'>{r['date']}</td>"
                f"<td style='padding:6px 12px'>{pill}</td>"
                f"<td style='padding:6px 12px'>{status}</td></tr>"
            )
        st.markdown(
            f"""<table style="width:100%;border-collapse:collapse;background:#1e293b;
                border-radius:8px;overflow:hidden;margin-bottom:16px">
            <thead><tr style="background:#0f172a;color:#64748b;font-size:12px;text-transform:uppercase">
                <th style="padding:8px 12px;text-align:left">Ticker</th>
                <th style="padding:8px 12px;text-align:left">Date</th>
                <th style="padding:8px 12px;text-align:left">Decision</th>
                <th style="padding:8px 12px;text-align:left">Status</th>
            </tr></thead><tbody>{rows_html}</tbody></table>""",
            unsafe_allow_html=True,
        )

        # Expandable detail per result
        for r in reversed(results):
            rating = r["decision"] or "—"
            color = RATING_COLORS.get(rating, "#6b7280")
            with st.expander(f"**{r['ticker']}** — {r['date']} — {rating}"):
                if r["error"]:
                    st.error(f"Error: {r['error']}")
                elif r["final_state"]:
                    from dashboard.utils import render_decision_first
                    render_decision_first(r["final_state"])

                    # Stale fundamentals warning for Fast Mode results
                    if r.get("portfolio_context"):
                        st.caption(f"🏦 Portfolio context was injected")

                    # Open in Chat shortcut
                    if st.button("💬 Analyze in Chat", key=f"wl_chat_{r['ticker']}_{r['date']}"):
                        invalidate_history_cache()
                        st.session_state["chat_analysis_key"] = None
                        st.session_state["chat_prefill_ticker"] = r["ticker"]
                        st.session_state["chat_prefill_date"] = r["date"]
                        st.session_state["_nav_target"] = "💬 Analysis Chat"
                        st.rerun()

    elif not is_running:
        st.info("Add tickers in the sidebar and press **▶ Start** to begin.")

    # ── Auto-refresh while running ────────────────────────────────────────────
    if is_running:
        # Clear global run guard when done
        if pool.is_idle() and not queue:
            st.session_state["wl_running"] = False
            st.session_state.pop("_global_run_active", None)
            invalidate_history_cache()
            st.rerun()
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=3000, key="wl_autorefresh")
        except ImportError:
            time.sleep(3)
            st.rerun()


# ── Helper: Add tickers to queue ──────────────────────────────────────────────

def _add_tickers_to_queue(
    raw_tickers, use_per_ticker_date, wl_date, validate_before_queue,
    selected_analysts, wl_provider, deep_model, quick_model,
    fast_mode_on, fast_mode_days,
):
    lines = [
        l.strip()
        for part in raw_tickers.replace(",", "\n").splitlines()
        for l in [part.strip()] if l.strip()
    ]

    added, skipped = 0, []
    for line in lines:
        parts = line.split()
        ticker = parts[0].upper()

        item_date = wl_date
        if use_per_ticker_date and len(parts) >= 2:
            try:
                from datetime import datetime as _dt
                _dt.strptime(parts[1], "%Y-%m-%d")
                item_date = parts[1]
            except ValueError:
                st.warning(f"{ticker}: date '{parts[1]}' is not valid (use YYYY-MM-DD) — using global date")

        if validate_before_queue:
            with st.spinner(f"Validating {ticker}…"):
                ok, msg = validate_ticker(ticker)
            if not ok:
                skipped.append(f"{ticker}: {msg}")
                continue

        cfg = {
            **DASHBOARD_CONFIG,
            "llm_provider": wl_provider.lower(),
            "deep_think_llm": deep_model,
            "quick_think_llm": quick_model,
        }

        # Fast Mode: find prior run
        prior_run = None
        if fast_mode_on:
            prior_run = find_recent_run(ticker, item_date, max_days=fast_mode_days)

        st.session_state["wl_queue"].append({
            "ticker": ticker,
            "date": item_date,
            "analysts": selected_analysts,
            "config": cfg,
            "prior_run": prior_run,
        })
        added += 1

    if added:
        st.success(f"Added {added} ticker(s) to queue.")
    for s in skipped:
        st.error(s)
