"""Single Ticker Deep Dive view.

Improvements over v1:
- Cache check: if ticker+date already exists in logs, load instantly — no LLM cost
- Cached dates hint: sidebar shows which dates already have results for the ticker
- Inline validation: validate fires automatically when Run is clicked, no separate step
- Elapsed timer: shows how long the current run has been going
- Retry button: on error, one click to re-run with same settings
- Re-run button: when viewing cached result, offer to force a fresh analysis
- Source badge: "Loaded from cache" vs "Live analysis" so user always knows
- All sidebar inputs locked while running
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import Dict, Optional
import html as _html

import streamlit as st

from dashboard.utils import (
    ALL_ANALYSTS, AGENT_TEAMS, ANALYST_TO_AGENT,
    DASHBOARD_CONFIG, RATING_COLORS, RunState,
    validate_ticker, find_cached_run, cached_dates_for_ticker,
    find_recent_run, fast_mode_summary, sanitize_report,
    check_stale_fundamentals, compute_conviction, render_decision_first,
)
from dashboard.runner import run_analysis

# ── Session-state keys ────────────────────────────────────────────────────────
_STATE_KEY      = "st_run_state"
_THREAD_KEY     = "st_run_thread"
_VALIDATED_KEY  = "st_ticker_validated"
_VALIDATE_MSG   = "st_ticker_val_msg"
_CACHED_KEY     = "st_cached_result"      # dict | None — loaded from logs
_FROM_CACHE_KEY = "st_result_from_cache"  # bool
_RUN_START_KEY  = "st_run_start_time"     # float timestamp


def _get_run_state() -> RunState:
    if _STATE_KEY not in st.session_state:
        st.session_state[_STATE_KEY] = RunState()
    return st.session_state[_STATE_KEY]


def _reports_from_cached(data: dict) -> Dict[str, str]:
    """Extract report sections from a saved JSON run."""
    mapping = {
        "market_report":          data.get("market_report", ""),
        "sentiment_report":       data.get("sentiment_report", ""),
        "news_report":            data.get("news_report", ""),
        "fundamentals_report":    data.get("fundamentals_report", ""),
        "investment_plan":        data.get("investment_plan", ""),
        "trader_investment_plan": data.get("trader_investment_decision", "")
                                  or data.get("trader_investment_plan", ""),
        "final_trade_decision":   data.get("final_trade_decision", ""),
    }
    return {k: v for k, v in mapping.items() if v}


# ── Agent progress ────────────────────────────────────────────────────────────

def _render_progress(agent_status: Dict[str, str], selected_analysts: list,
                     from_cache: bool = False):
    if from_cache:
        st.markdown(
            '<div style="background:#1e3a5f;border:1px solid #3b82f6;border-radius:8px;'
            'padding:10px 16px;color:#93c5fd;font-size:13px">'
            '📦 Result loaded from cache — all agents completed in a previous run'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    STATUS_ICON  = {
        "pending": "⏳", "running": "🔄", "done": "✅",
        "error": "❌", "reused": "📦", "failed": "❌",
    }
    STATUS_COLOR = {
        "pending": "#6b7280", "running": "#3b82f6", "done": "#22c55e",
        "error": "#ef4444",   "reused": "#7c3aed", "failed": "#ef4444",
    }

    visible_analyst_agents = [ANALYST_TO_AGENT[a] for a in selected_analysts if a in ANALYST_TO_AGENT]
    fixed_teams = {k: v for k, v in AGENT_TEAMS.items() if k != "Analyst Team"}
    teams_to_show = {}
    if visible_analyst_agents:
        teams_to_show["Analyst Team"] = visible_analyst_agents
    teams_to_show.update(fixed_teams)

    # Timeline stepper — horizontal pipeline phases
    phase_names = list(teams_to_show.keys())
    phase_statuses = []
    for team, agents in teams_to_show.items():
        statuses = [agent_status.get(a, "pending") for a in agents]
        if all(s in ("done", "reused") for s in statuses):
            phase_statuses.append("done")
        elif any(s == "running" for s in statuses):
            phase_statuses.append("running")
        elif any(s in ("error", "failed") for s in statuses):
            phase_statuses.append("error")
        else:
            phase_statuses.append("pending")

    # Render horizontal stepper
    step_html = '<div style="display:flex;align-items:center;gap:4px;margin-bottom:12px;flex-wrap:wrap">'
    for i, (name, status) in enumerate(zip(phase_names, phase_statuses)):
        color = STATUS_COLOR.get(status, "#6b7280")
        icon = STATUS_ICON.get(status, "⏳")
        bg = f"{color}22"
        border = color
        step_html += (
            f'<div style="background:{bg};border:1px solid {border};border-radius:8px;'
            f'padding:6px 12px;text-align:center;min-width:100px">'
            f'<div style="font-size:16px">{icon}</div>'
            f'<div style="font-size:11px;color:{color};font-weight:600">{name}</div>'
            f'</div>'
        )
        if i < len(phase_names) - 1:
            arrow_color = "#22c55e" if phase_statuses[i] == "done" else "#334155"
            step_html += f'<div style="color:{arrow_color};font-size:18px">→</div>'
    step_html += '</div>'
    st.markdown(step_html, unsafe_allow_html=True)

    # Detailed agent list below stepper
    cols = st.columns(len(teams_to_show))
    for col, (team, agents) in zip(cols, teams_to_show.items()):
        with col:
            st.markdown(f"**{team}**")
            for agent in agents:
                status = agent_status.get(agent, "pending")
                icon   = STATUS_ICON.get(status, "⏳")
                color  = STATUS_COLOR.get(status, "#6b7280")
                short  = (agent.replace(" Analyst", "")
                               .replace(" Researcher", "")
                               .replace(" Manager", " Mgr"))
                st.markdown(
                    f'<div style="color:{color};font-size:13px;margin:2px 0">'
                    f'{icon} {short}</div>',
                    unsafe_allow_html=True,
                )


# ── Price chart ───────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _fetch_price_data(ticker: str, analysis_date: str):
    """Fetch 6 months of OHLCV data ending on analysis_date. Cached 5 min."""
    import yfinance as yf
    from datetime import datetime as _dt
    try:
        end   = _dt.strptime(analysis_date, "%Y-%m-%d").date()
        start = end - timedelta(days=180)
        df = yf.Ticker(ticker).history(
            start=start.strftime("%Y-%m-%d"),
            end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
        )
        # If empty (e.g. analysis date is today before market open), try period-based
        if df.empty:
            df = yf.Ticker(ticker).history(period="6mo")
        return df if not df.empty else None
    except Exception:
        return None


def _render_price_chart(ticker: str, analysis_date: str):
    """Render a 6-month candlestick + volume chart with the analysis date marked."""
    if not ticker:
        return

    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        st.caption("Install plotly for price charts: `pip install plotly`")
        return

    with st.spinner(f"Loading {ticker} price data…"):
        df = _fetch_price_data(ticker, analysis_date)

    if df is None or df.empty:
        st.caption(f"No price data available for {ticker}")
        return

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.75, 0.25],
        vertical_spacing=0.03,
    )

    # ── Candlestick ───────────────────────────────────────────────────────────
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"], high=df["High"],
            low=df["Low"],   close=df["Close"],
            name=ticker,
            increasing_line_color="#22c55e",
            decreasing_line_color="#ef4444",
            increasing_fillcolor="#22c55e",
            decreasing_fillcolor="#ef4444",
        ),
        row=1, col=1,
    )

    # ── 20-day moving average ─────────────────────────────────────────────────
    ma20 = df["Close"].rolling(20).mean()
    fig.add_trace(
        go.Scatter(
            x=df.index, y=ma20,
            name="MA20",
            line=dict(color="#f59e0b", width=1.5, dash="dot"),
        ),
        row=1, col=1,
    )

    # ── Volume bars ───────────────────────────────────────────────────────────
    colors = ["#22c55e" if c >= o else "#ef4444"
              for c, o in zip(df["Close"], df["Open"])]
    fig.add_trace(
        go.Bar(x=df.index, y=df["Volume"], name="Volume",
               marker_color=colors, opacity=0.6),
        row=2, col=1,
    )

    # ── Analysis date vertical line ───────────────────────────────────────────
    from datetime import datetime as _dt
    try:
        ad = _dt.strptime(analysis_date, "%Y-%m-%d")
        fig.add_vline(
            x=ad.timestamp() * 1000,
            line_width=2, line_dash="dash", line_color="#3b82f6",
            annotation_text="Analysis date",
            annotation_position="top right",
            annotation_font_color="#3b82f6",
        )
    except Exception:
        pass

    fig.update_layout(
        height=380,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0f172a",
        font=dict(color="#94a3b8", size=11),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"),
        xaxis_rangeslider_visible=False,
        xaxis2=dict(showgrid=False),
        yaxis=dict(gridcolor="#1e293b", zerolinecolor="#1e293b"),
        yaxis2=dict(gridcolor="#1e293b", zerolinecolor="#1e293b"),
        xaxis=dict(gridcolor="#1e293b"),
    )

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ── Report renderer ───────────────────────────────────────────────────────────

_SECTION_LABELS = {
    "market_report":          "📊 Market Analysis",
    "sentiment_report":       "💬 Social Sentiment",
    "news_report":            "📰 News Analysis",
    "fundamentals_report":    "🏦 Fundamentals",
    "investment_plan":        "🧠 Research Decision",
    "trader_investment_plan": "💼 Trader Plan",
    "final_trade_decision":   "🎯 Final Decision",
}


def _render_reports(reports: Dict[str, str]):
    if not reports:
        st.info("Reports will appear here as agents complete their work.")
        return

    if "final_trade_decision" in reports:
        from tradingagents.agents.utils.rating import parse_rating
        import re as _re
        rating = parse_rating(reports["final_trade_decision"])
        color  = RATING_COLORS.get(rating, "#6b7280")

        # Extract structured fields if present
        text = reports["final_trade_decision"]
        price_target = None
        time_horizon = None
        exec_summary = None
        pt_match = _re.search(r'\*\*Price Target\*\*[:\s]+([^\n]+)', text)
        th_match = _re.search(r'\*\*Time Horizon\*\*[:\s]+([^\n]+)', text)
        es_match = _re.search(r'\*\*Executive Summary\*\*[:\s]+([^\n]+)', text)
        if pt_match:
            price_target = _html.escape(pt_match.group(1).strip())
        if th_match:
            time_horizon = _html.escape(th_match.group(1).strip())
        if es_match:
            exec_summary = _html.escape(es_match.group(1).strip())

        # Decision banner
        st.markdown(
            f'<div style="background:{color}22;border:2px solid {color};'
            f'border-radius:12px;padding:18px;margin-bottom:12px">'
            f'<span style="font-size:22px;font-weight:800;color:{color}">'
            f'Final Decision: {rating}</span></div>',
            unsafe_allow_html=True,
        )

        # Key metrics row — price target, time horizon, conviction, exec summary
        conviction_label, conviction_color = compute_conviction(reports)
        metric_items = []
        if price_target:
            metric_items.append(("🎯 Price Target", price_target))
        if time_horizon:
            metric_items.append(("⏳ Time Horizon", time_horizon))
        metric_items.append(("💡 Conviction", conviction_label))

        if metric_items:
            cols = st.columns(len(metric_items))
            for col, (label, val) in zip(cols, metric_items):
                if label == "💡 Conviction":
                    col.markdown(
                        f'<div style="background:{conviction_color}22;border:1px solid {conviction_color};'
                        f'border-radius:8px;padding:10px 14px;text-align:center">'
                        f'<div style="font-size:11px;color:#94a3b8;margin-bottom:2px">{label}</div>'
                        f'<div style="font-size:18px;font-weight:700;color:{conviction_color}">{val}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    col.metric(label, val)

        if exec_summary:
            st.markdown(
                f'<div style="background:#1e293b;border-radius:8px;padding:10px 14px;'
                f'font-size:13px;color:#cbd5e1;margin-top:8px"><b>Executive Summary</b><br>{exec_summary}</div>',
                unsafe_allow_html=True,
            )

    analyst_keys = [s for s in
                    ["market_report", "sentiment_report", "news_report", "fundamentals_report"]
                    if s in reports]
    if analyst_keys:
        st.markdown("#### Analyst Reports")
        tabs = st.tabs([_SECTION_LABELS[s] for s in analyst_keys])
        for tab, section in zip(tabs, analyst_keys):
            with tab:
                st.markdown(sanitize_report(reports[section]))

    decision_keys = [s for s in
                     ["investment_plan", "trader_investment_plan", "final_trade_decision"]
                     if s in reports]
    if decision_keys:
        st.markdown("#### Decision Pipeline")
        for section in decision_keys:
            with st.expander(_SECTION_LABELS[section],
                             expanded=(section == "final_trade_decision")):
                st.markdown(sanitize_report(reports[section]))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _elapsed_str(start_ts: float) -> str:
    secs = int(time.time() - start_ts)
    return f"{secs // 60:02d}:{secs % 60:02d}"


def _launch_run(run_state: RunState, ticker: str, trade_date: str,
                selected_analysts: list, llm_provider: str,
                deep_model: str, quick_model: str,
                debate_rounds: int, risk_rounds: int,
                output_language: str = "English",
                prior_run: dict = None):
    """Start a fresh (or fast-mode) analysis run."""
    run_state.reset()
    st.session_state[_FROM_CACHE_KEY] = False
    st.session_state[_CACHED_KEY]     = None
    st.session_state[_RUN_START_KEY]  = time.time()
    cfg = {
        **DASHBOARD_CONFIG,
        "llm_provider":            llm_provider.lower(),
        "deep_think_llm":          deep_model,
        "quick_think_llm":         quick_model,
        "max_debate_rounds":       debate_rounds,
        "max_risk_discuss_rounds": risk_rounds,
        "output_language":         output_language,
    }
    st.session_state[_THREAD_KEY] = run_analysis(
        run_state, ticker, trade_date, selected_analysts, cfg,
        prior_run=prior_run,
    )


# ── Main view ─────────────────────────────────────────────────────────────────

def render_single_ticker():
    st.title("🔍 Single Ticker Deep Dive")

    run_state = _get_run_state()
    snap      = run_state.snapshot()
    from_cache = st.session_state.get(_FROM_CACHE_KEY, False)

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### Analysis Settings")

        ticker_input = st.text_input(
            "Ticker Symbol",
            value=st.session_state.get(_VALIDATED_KEY, "NVDA"),
            placeholder="e.g. NVDA, AAPL, 7203.T",
            help="Official ticker symbol. Use AAPL not Apple.",
            disabled=snap["running"],
        ).upper().strip()

        # Show cached dates for this ticker as a hint
        if ticker_input and not snap["running"]:
            cached = cached_dates_for_ticker(ticker_input)
            if cached:
                st.caption(f"📦 Cached: {', '.join(cached[:5])}"
                           + (" …" if len(cached) > 5 else ""))

        # Inline ticker validation with debounce (600ms between validations)
        if ticker_input and not snap["running"]:
            _last_val_ticker = st.session_state.get("_st_last_val_ticker", "")
            _last_val_time = st.session_state.get("_st_last_val_time", 0)
            _last_val_result = st.session_state.get("_st_last_val_result")

            if ticker_input != _last_val_ticker and (time.time() - _last_val_time) >= 0.6:
                ok, msg = validate_ticker(ticker_input)
                st.session_state["_st_last_val_ticker"] = ticker_input
                st.session_state["_st_last_val_time"] = time.time()
                st.session_state["_st_last_val_result"] = (ok, msg)
                _last_val_result = (ok, msg)

            if _last_val_result:
                ok, msg = _last_val_result
                if ok:
                    st.success(msg, icon="✅")
                else:
                    st.error(msg)
        else:
            # Show manual validation result (from Run button click)
            val_result = st.session_state.get(_VALIDATE_MSG)
            if val_result:
                ok, msg = val_result
                if ok:
                    st.success(msg, icon="✅")
                else:
                    st.error(msg)

        st.divider()

        # Consume date prefill from "Run Again" (one-shot)
        _prefill_date = st.session_state.pop("st_prefill_date", None)
        _default_date = date.today()
        if _prefill_date:
            try:
                _default_date = datetime.strptime(_prefill_date, "%Y-%m-%d").date()
            except ValueError:
                pass

        trade_date = st.date_input(
            "Analysis Date",
            value=_default_date,
            max_value=date.today(),
            disabled=snap["running"],
        ).strftime("%Y-%m-%d")

        st.markdown("**Analysts**")
        analyst_checks = {
            a: st.checkbox(a.capitalize(), value=True,
                           key=f"analyst_{a}", disabled=snap["running"])
            for a in ALL_ANALYSTS
        }
        selected_analysts = [a for a, checked in analyst_checks.items() if checked]

        st.markdown("**Debate Rounds**")
        debate_rounds = st.slider("Research debate rounds", 1, 3, 1, disabled=snap["running"])
        risk_rounds   = st.slider("Risk debate rounds",     1, 3, 1, disabled=snap["running"])

        st.markdown("**LLM Provider**")
        llm_provider = st.selectbox(
            "Provider",
            ["OpenAI", "Google", "Anthropic", "DeepSeek", "xAI", "Ollama"],
            index=3,
            disabled=snap["running"],
            help="Choose your LLM provider"
        )
        
        # Model options based on provider
        MODEL_OPTIONS = {
            "OpenAI": {
                "deep": ["gpt-5.4", "gpt-5.4-turbo", "gpt-4o", "gpt-4-turbo"],
                "quick": ["gpt-5.4-mini", "gpt-4o-mini", "gpt-4-turbo"]
            },
            "Google": {
                "deep": ["gemini-3.1-pro", "gemini-2.5-pro", "gemini-2.0-flash-thinking-exp"],
                "quick": ["gemini-3.1-flash", "gemini-2.5-flash", "gemini-2.0-flash-exp"]
            },
            "Anthropic": {
                "deep": ["claude-4.6-sonnet", "claude-4.5-sonnet", "claude-4-opus"],
                "quick": ["claude-4.6-haiku", "claude-4.5-haiku", "claude-4-haiku"]
            },
            "DeepSeek": {
                "deep": ["deepseek-v4-pro", "deepseek-chat"],
                "quick": ["deepseek-v4-flash", "deepseek-chat"]
            },
            "xAI": {
                "deep": ["grok-4-turbo", "grok-4"],
                "quick": ["grok-4-turbo", "grok-4"]
            },
            "Ollama": {
                "deep": ["llama3.1:70b", "llama3.1:8b", "mistral:latest"],
                "quick": ["llama3.1:8b", "mistral:latest", "phi3:latest"]
            }
        }
        
        provider_models = MODEL_OPTIONS.get(llm_provider, MODEL_OPTIONS["OpenAI"])
        
        st.markdown("**Models**")
        deep_model  = st.selectbox(
            "Deep thinker",
            provider_models["deep"],
            index=0,
            disabled=snap["running"],
            help="Model for complex reasoning (Research Manager, Portfolio Manager)"
        )
        quick_model = st.selectbox(
            "Quick thinker",
            provider_models["quick"],
            index=0,
            disabled=snap["running"],
            help="Model for quick tasks (Analysts, Trader, Risk Team)"
        )

        st.divider()

        # ── Fast Mode toggle ──────────────────────────────────────────────────
        st.markdown("**Analysis Mode**")
        fast_mode_on = st.toggle(
            "⚡ Fast Mode",
            value=False,
            disabled=snap["running"],
            help=(
                "Reuses fundamentals + research plan from a recent prior run "
                "(within 7 days). Only re-runs market, news, trader, risk team, "
                "and portfolio manager. ~60% faster and cheaper."
            ),
        )
        fast_mode_days = 7
        if fast_mode_on:
            fast_mode_days = st.slider(
                "Max days to look back", 1, 14, 7,
                disabled=snap["running"],
                help="How old the prior run can be for reuse.",
            )
            # Preview what would be reused
            if ticker_input and not snap["running"]:
                prior = find_recent_run(ticker_input, trade_date, max_days=fast_mode_days)
                if prior:
                    st.success(fast_mode_summary(prior, trade_date), icon="📦")
                    # Check for stale fundamentals
                    prior_date = prior.get("_prior_date", prior.get("trade_date"))
                    if prior_date:
                        stale_warning = check_stale_fundamentals(ticker_input, prior_date, trade_date)
                        if stale_warning:
                            st.warning(stale_warning, icon="⚠️")
                else:
                    st.warning(
                        f"No prior run found within {fast_mode_days} days — "
                        "will run full analysis.",
                        icon="⚠️",
                    )

        st.divider()

        # ── Output language ───────────────────────────────────────────────────
        st.markdown("**Output Language**")
        output_language = st.selectbox(
            "Report language",
            ["English", "Spanish", "French", "German", "Japanese",
             "Chinese (Simplified)", "Korean", "Portuguese", "Hindi"],
            index=0,
            disabled=snap["running"],
            help="Language for analyst reports and final decision",
            label_visibility="collapsed",
        )

        st.divider()

        # ── Action buttons ────────────────────────────────────────────────────
        if snap["running"]:
            elapsed = _elapsed_str(st.session_state.get(_RUN_START_KEY, time.time()))
            st.markdown(f"⏱ Running: **{elapsed}**")
            if st.button("⏹ Stop", use_container_width=True):
                run_state.request_cancel()
                st.rerun()

        elif snap.get("error"):
            # Retry button on error
            if st.button("🔁 Retry", use_container_width=True, type="primary"):
                ok, msg = validate_ticker(ticker_input)
                st.session_state[_VALIDATE_MSG] = (ok, msg)
                if ok:
                    st.session_state[_VALIDATED_KEY] = ticker_input
                    _launch_run(run_state, ticker_input, trade_date,
                                selected_analysts, llm_provider,
                                deep_model, quick_model,
                                debate_rounds, risk_rounds,
                                output_language=output_language)
                    st.rerun()

        else:
            # Global run guard — prevent concurrent runs across views
            _global_busy = st.session_state.get("_global_run_active", False)
            if _global_busy:
                st.warning("Another analysis is running. Wait for it to complete or cancel it.")

            # Normal Run / Load from Cache button
            if st.button("🚀 Run Analysis", use_container_width=True, type="primary",
                         disabled=not selected_analysts or _global_busy):
                # Step 1: validate ticker
                with st.spinner(f"Validating {ticker_input}…"):
                    ok, msg = validate_ticker(ticker_input)
                st.session_state[_VALIDATE_MSG] = (ok, msg)

                if not ok:
                    st.rerun()   # show error, don't proceed
                else:
                    st.session_state[_VALIDATED_KEY] = ticker_input
                    # Step 2: check exact cache hit
                    cached_data = find_cached_run(ticker_input, trade_date)
                    if cached_data:
                        st.session_state[_CACHED_KEY]     = cached_data
                        st.session_state[_FROM_CACHE_KEY] = True
                        run_state.reset()
                    else:
                        # Step 3: Fast Mode — look for a recent prior run
                        prior_run = None
                        if fast_mode_on:
                            prior_run = find_recent_run(
                                ticker_input, trade_date, max_days=fast_mode_days
                            )
                            if prior_run is None:
                                run_state.append_log(
                                    "No prior run found — falling back to full analysis"
                                )
                        _launch_run(run_state, ticker_input, trade_date,
                                    selected_analysts, llm_provider,
                                    deep_model, quick_model,
                                    debate_rounds, risk_rounds,
                                    output_language=output_language,
                                    prior_run=prior_run)
                    st.rerun()

            # Re-run fresh button when showing a cached result
            if from_cache and st.session_state.get(_CACHED_KEY):
                if st.button("🔄 Re-run Fresh Analysis", use_container_width=True):
                    st.session_state[_CACHED_KEY]     = None
                    st.session_state[_FROM_CACHE_KEY] = False
                    _launch_run(run_state,
                                st.session_state.get(_VALIDATED_KEY, ticker_input),
                                trade_date, selected_analysts,
                                llm_provider, deep_model, quick_model,
                                debate_rounds, risk_rounds,
                                output_language=output_language)
                    st.rerun()

    # ── Re-read snap ──────────────────────────────────────────────────────────
    snap       = run_state.snapshot()
    from_cache = st.session_state.get(_FROM_CACHE_KEY, False)
    cached_data: Optional[dict] = st.session_state.get(_CACHED_KEY)

    # ── Idle / welcome ────────────────────────────────────────────────────────
    if not snap["running"] and not snap["done"] and not cached_data:
        st.markdown("""
        ### How to use
        1. **Enter a ticker** in the sidebar (`AAPL`, `NVDA`, `7203.T` — symbol, not company name)
        2. **Pick a date** — if you've analysed this ticker+date before, it loads instantly from cache
        3. **Click "Run Analysis"** — validates the ticker, checks cache, then runs if needed

        **Pipeline:**  
        Analysts → Bull/Bear Debate → Research Manager → Trader → Risk Team → Portfolio Manager
        """)
        _val = st.session_state.get(_VALIDATE_MSG)
        if _val and not _val[0]:
            st.error(_val[1])
        return

    # ── Determine what to display ─────────────────────────────────────────────
    if cached_data:
        display_ticker = cached_data.get("company_of_interest",
                                         st.session_state.get(_VALIDATED_KEY, ""))
        display_date   = cached_data.get("trade_date", trade_date)
        from tradingagents.agents.utils.rating import parse_rating
        display_decision = parse_rating(cached_data.get("final_trade_decision", ""))
        display_reports  = _reports_from_cached(cached_data)
        display_agents   = {}   # not needed for cache view
    else:
        display_ticker   = snap["ticker"]
        display_date     = snap["trade_date"]
        display_decision = snap["decision"]
        display_reports  = snap["reports"]
        display_agents   = snap["agent_status"]

    # ── Header ────────────────────────────────────────────────────────────────
    h1, h2, h3 = st.columns([2, 2, 1])
    with h1:
        st.markdown(f"### {display_ticker}  ·  {display_date}")
        if from_cache:
            st.markdown(
                '<span style="background:#1e3a5f;color:#93c5fd;padding:2px 10px;'
                'border-radius:10px;font-size:12px">📦 From cache</span>',
                unsafe_allow_html=True,
            )
        elif snap["done"]:
            st.markdown(
                '<span style="background:#14532d;color:#86efac;padding:2px 10px;'
                'border-radius:10px;font-size:12px">✨ Live analysis</span>',
                unsafe_allow_html=True,
            )
    with h2:
        if display_decision:
            color = RATING_COLORS.get(display_decision, "#6b7280")
            st.markdown(
                f'<div style="font-size:24px;font-weight:800;color:{color};margin-top:4px">'
                f'{display_decision}</div>',
                unsafe_allow_html=True,
            )
    with h3:
        if snap["running"]:
            elapsed = _elapsed_str(st.session_state.get(_RUN_START_KEY, time.time()))
            st.markdown(f"🔄 **{elapsed}**")
        elif snap.get("error"):
            st.error("Failed — click Retry")
        elif from_cache:
            st.info("Cached")
        else:
            st.success("✅ Complete")

    st.divider()

    # ── Price chart ───────────────────────────────────────────────────────────
    _render_price_chart(display_ticker, display_date)

    # ── Display warnings if any ───────────────────────────────────────────────
    if snap.get("warnings"):
        for warning in snap["warnings"]:
            st.warning(warning, icon="⚠️")

    # ── Progress / cache badge ────────────────────────────────────────────────
    if not from_cache:
        done_count   = sum(1 for v in display_agents.values() if v in ("done", "reused"))
        total_count  = len(display_agents) or 1
        reused_count = sum(1 for v in display_agents.values() if v == "reused")
        report_count = len(display_reports)

        # Overall progress bar
        pct = done_count / total_count
        st.progress(pct, text=f"Pipeline: {done_count}/{total_count} agents complete")

        st.markdown("#### Agent Pipeline Progress")
        _render_progress(display_agents, selected_analysts, from_cache=False)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Agents Completed", f"{done_count} / {total_count}")
        m2.metric("Reused (Fast Mode)", reused_count if reused_count else "—")
        m3.metric("Reports Ready",    report_count)
        if snap["running"]:
            elapsed = _elapsed_str(st.session_state.get(_RUN_START_KEY, time.time()))
            m4.metric("Elapsed", elapsed)
        else:
            m4.metric("Status", "Done" if snap["done"] else "Error")
    else:
        _render_progress({}, [], from_cache=True)

    st.divider()

    # ── Reports + log ─────────────────────────────────────────────────────────
    if from_cache or (not snap["running"] and snap["done"]):
        # Full width decision-first layout for completed / cached results
        if cached_data:
            render_decision_first(cached_data)
        elif snap.get("final_state"):
            render_decision_first(snap["final_state"])
        else:
            _render_reports(display_reports)
    elif not snap["running"] and not snap["done"]:
        # Idle state — no reports yet
        pass
    else:
        # Side-by-side with live log while running
        rep_col, log_col = st.columns([3, 1])
        with rep_col:
            st.markdown("#### Analysis Reports")
            _render_reports(display_reports)
        with log_col:
            st.markdown("#### Live Log")
            log_text = "\n".join(snap["log_lines"][-80:]) if snap["log_lines"] else "Waiting…"
            st.text_area(
                "Live Log",
                value=log_text,
                height=520,
                key="live_log_area",
                label_visibility="collapsed",
            )

    # ── Auto-rerun while running ──────────────────────────────────────────────
    # ── Auto-rerun while running (Bug 17 fix) ───────────────────────────────
    if snap["running"]:
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=2000, key="st_autorefresh")
        except ImportError:
            # Fallback: blocking sleep — upgrade Streamlit to 1.33+ or install
            # streamlit-autorefresh for non-blocking refresh
            time.sleep(2)
            st.rerun()
