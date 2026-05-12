"""Analysis Chat view — with persistent chat history.

Each analysis has its own chat history saved to disk alongside the analysis
JSON file as  chat_history_<DATE>.json.  When you reopen an analysis the
conversation is restored exactly as you left it.

Session-state keys (all prefixed with "chat_"):
  chat_analysis_key   – "<TICKER>|<DATE>" of the currently loaded analysis
  chat_analysis_data  – raw dict from the analysis JSON
  chat_analysis_file  – Path to the analysis JSON (used to locate chat file)
  chat_context_str    – pre-built system-prompt context string
  chat_history        – list of {"role": "user"|"assistant", "content": str,
                                  "timestamp": str}
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from dashboard.utils import (
    RATING_COLORS,
    list_history,
    sanitize_report,
    load_chat_history,
    save_chat_history,
    _cached_chat_msg_count,
)

# ── LLM provider / model options ─────────────────────────────────────────────
_PROVIDER_MODELS = {
    "DeepSeek":  {"models": ["deepseek-v4-pro", "deepseek-chat", "deepseek-v4-flash"],              "default": 0},
    "OpenAI":    {"models": ["gpt-5.4", "gpt-5.4-mini", "gpt-5.4-turbo", "gpt-4o", "gpt-4o-mini"], "default": 0},
    "Google":    {"models": ["gemini-3.1-pro", "gemini-3.1-flash", "gemini-2.5-pro"],               "default": 1},
    "Anthropic": {"models": ["claude-4.6-sonnet", "claude-4.5-sonnet", "claude-4.6-haiku"],         "default": 0},
    "xAI":       {"models": ["grok-4-turbo", "grok-4"],                                             "default": 0},
    "Ollama":    {"models": ["llama3.1:70b", "llama3.1:8b", "mistral:latest"],                      "default": 1},
}
_DEFAULT_PROVIDER = "DeepSeek"


# ── Context builder ───────────────────────────────────────────────────────────

def _build_context(data: Dict[str, Any]) -> str:
    """Flatten all report sections into a single system-prompt context string."""
    ticker = data.get("company_of_interest", "Unknown")
    date   = data.get("trade_date", "Unknown")

    parts = [
        "# TradingAgents Analysis Report",
        f"**Ticker:** {ticker}  |  **Date:** {date}",
        "",
        "You are a financial analysis assistant. The user has reviewed a "
        "multi-agent LLM trading analysis and wants to ask questions about it. "
        "Answer clearly and concisely, referencing specific parts of the reports "
        "when relevant. Do not make up information not present in the reports. "
        "If asked for a personal opinion on whether to trade, remind the user "
        "this is for research purposes only and not financial advice.",
        "",
        "---",
        "## Full Analysis Context",
        "",
    ]

    if data.get("market_report"):
        parts += ["### Market Analysis", sanitize_report(data["market_report"]), ""]
    if data.get("news_report"):
        parts += ["### News Analysis", sanitize_report(data["news_report"]), ""]
    if data.get("fundamentals_report"):
        parts += ["### Fundamentals Analysis", sanitize_report(data["fundamentals_report"]), ""]
    if data.get("sentiment_report"):
        parts += ["### Social Sentiment Analysis", sanitize_report(data["sentiment_report"]), ""]

    debate = data.get("investment_debate_state") or {}
    if debate.get("bull_history"):
        parts += ["### Bull Researcher Argument", sanitize_report(debate["bull_history"]), ""]
    if debate.get("bear_history"):
        parts += ["### Bear Researcher Argument", sanitize_report(debate["bear_history"]), ""]
    if debate.get("judge_decision"):
        parts += ["### Research Manager Decision", sanitize_report(debate["judge_decision"]), ""]

    if data.get("trader_investment_plan"):
        parts += ["### Trader Plan", sanitize_report(data["trader_investment_plan"]), ""]

    risk = data.get("risk_debate_state") or {}
    if risk.get("aggressive_history"):
        parts += ["### Aggressive Risk Analyst", sanitize_report(risk["aggressive_history"]), ""]
    if risk.get("conservative_history"):
        parts += ["### Conservative Risk Analyst", sanitize_report(risk["conservative_history"]), ""]
    if risk.get("neutral_history"):
        parts += ["### Neutral Risk Analyst", sanitize_report(risk["neutral_history"]), ""]

    if data.get("final_trade_decision"):
        parts += ["### Final Portfolio Manager Decision",
                  sanitize_report(data["final_trade_decision"]), ""]

    return "\n".join(parts)


# ── LLM call ──────────────────────────────────────────────────────────────────

def _call_llm(provider: str, model: str,
              system_prompt: str,
              messages: List[Dict[str, str]]) -> str:
    """Invoke the chosen LLM and return the assistant reply as a string."""
    from tradingagents.llm_clients.factory import create_llm_client
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

    try:
        client = create_llm_client(provider=provider.lower(), model=model)
    except Exception as exc:
        return f"❌ Could not initialise LLM client: {exc}"

    lc_msgs = [SystemMessage(content=system_prompt)]
    for m in messages:
        if m["role"] == "user":
            lc_msgs.append(HumanMessage(content=m["content"]))
        else:
            lc_msgs.append(AIMessage(content=m["content"]))

    try:
        llm      = client.get_llm()
        response = llm.invoke(lc_msgs)
        return response.content if hasattr(response, "content") else str(response)
    except Exception as exc:
        return f"❌ LLM error: {exc}"


# Model context window limits (tokens)
_MODEL_CONTEXT_LIMITS = {
    "gpt-5.4": 128_000, "gpt-5.4-mini": 128_000, "gpt-5.4-turbo": 128_000,
    "gpt-4o": 128_000, "gpt-4o-mini": 128_000,
    "deepseek-v4-pro": 64_000, "deepseek-v4-flash": 64_000, "deepseek-chat": 64_000,
    "claude-4.6-sonnet": 200_000, "claude-4.5-sonnet": 200_000, "claude-4.6-haiku": 200_000,
    "gemini-3.1-pro": 1_000_000, "gemini-3.1-flash": 1_000_000, "gemini-2.5-pro": 1_000_000,
    "grok-4-turbo": 128_000, "grok-4": 128_000,
}
_DEFAULT_CONTEXT_LIMIT = 8_000


def _estimate_tokens(text: str) -> int:
    return int(len(text.split()) * 1.3)


def _trim_messages_to_fit(system_prompt: str, messages: List[Dict[str, str]], model: str):
    """Trim oldest messages to fit within 80% of model context window.

    Returns (trimmed_messages, was_trimmed).
    """
    limit = _MODEL_CONTEXT_LIMITS.get(model, _DEFAULT_CONTEXT_LIMIT)
    budget = int(limit * 0.8)
    sys_tokens = _estimate_tokens(system_prompt)

    if sys_tokens >= budget:
        # System prompt alone exceeds budget — truncate it
        return messages, True  # caller should warn

    remaining = budget - sys_tokens
    # Keep messages from newest to oldest until budget exhausted
    kept = []
    for m in reversed(messages):
        msg_tokens = _estimate_tokens(m["content"])
        if remaining - msg_tokens < 0 and kept:
            break
        kept.append(m)
        remaining -= msg_tokens
    kept.reverse()
    return kept, len(kept) < len(messages)


def _stream_llm(provider: str, model: str,
                system_prompt: str,
                messages: List[Dict[str, str]]):
    """Stream tokens from the LLM. Yields str chunks; yields full reply at end as sentinel."""
    from tradingagents.llm_clients.factory import create_llm_client
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

    # Context window overflow protection (Bug 9 fix)
    trimmed_messages, was_trimmed = _trim_messages_to_fit(system_prompt, messages, model)
    if was_trimmed:
        yield "ℹ️ *Older messages were trimmed to fit the model's context window.*\n\n"

    try:
        client = create_llm_client(provider=provider.lower(), model=model)
    except Exception as exc:
        yield f"❌ Could not initialise LLM client: {exc}"
        return

    lc_msgs = [SystemMessage(content=system_prompt)]
    for m in trimmed_messages:
        if m["role"] == "user":
            lc_msgs.append(HumanMessage(content=m["content"]))
        else:
            lc_msgs.append(AIMessage(content=m["content"]))

    try:
        llm = client.get_llm()
        full = ""
        for chunk in llm.stream(lc_msgs):
            text = chunk.content if hasattr(chunk, "content") else str(chunk)
            if text:
                full += text
                yield text
        # Final sentinel — the complete reply
        yield ("__DONE__", full)
    except Exception as exc:
        yield f"❌ LLM error: {exc}"


# ── UI helpers ────────────────────────────────────────────────────────────────

def _analysis_card(data: Dict[str, Any], rating: str, msg_count: int):
    ticker = data.get("company_of_interest", "—")
    date   = data.get("trade_date", "—")
    color  = RATING_COLORS.get(rating, "#6b7280")
    chat_badge = (
        f'<span style="background:#1e3a5f;color:#93c5fd;padding:2px 10px;'
        f'border-radius:10px;font-size:12px;margin-left:12px">'
        f'💬 {msg_count} message{"s" if msg_count != 1 else ""} saved</span>'
        if msg_count else ""
    )
    st.markdown(
        f"""
        <div style="background:#1e293b;border:1px solid #334155;border-radius:10px;
                    padding:14px 18px;margin-bottom:4px;display:flex;
                    align-items:center;gap:16px;flex-wrap:wrap">
          <div>
            <span style="font-size:22px;font-weight:800">{ticker}</span>
            <span style="color:#94a3b8;font-size:13px;margin-left:10px">{date}</span>
            {chat_badge}
          </div>
          <div style="background:{color}22;border:2px solid {color};border-radius:8px;
                      padding:4px 14px;font-weight:700;color:{color};font-size:15px;
                      margin-left:auto">
            {rating}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _suggested_questions(ticker: str, rating: str) -> List[str]:
    return [
        f"Why did the agents recommend {rating} for {ticker}?",
        f"What are the biggest risks for {ticker} right now?",
        "Summarise the bull vs bear debate in simple terms.",
        "What would change this recommendation to a Buy?",
        "Explain the key technical indicators mentioned.",
        "What does the fundamentals report say about valuation?",
        "How confident should I be in this analysis?",
    ]


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ── Main view ─────────────────────────────────────────────────────────────────

def render_chat():
    st.title("💬 Analysis Chat")
    st.caption(
        "Chat about your analyses. **Single mode**: deep-dive one analysis. "
        "**Multi mode**: compare and discuss 2-5 analyses together."
    )

    # ── Mode toggle ───────────────────────────────────────────────────────────
    chat_mode = st.radio("Mode", ["Single", "Multi"], horizontal=True,
                        key="chat_mode_toggle",
                        index=1 if st.session_state.get("chat_multi_prefill") else 0)

    if chat_mode == "Multi":
        _render_multi_chat()
    else:
        _render_single_chat()


# ── Multi-Mode Chat ───────────────────────────────────────────────────────────

def _build_multi_context(analyses: List[Dict[str, Any]]) -> str:
    """Build combined system prompt from multiple analyses."""
    parts = [
        "# Multi-Analysis Comparison Chat",
        "",
        "You are a financial analysis assistant. The user has selected multiple "
        "analyses and wants to compare, contrast, and discuss them together. "
        "Reference specific analyses by their ticker and date when answering. "
        "Do not make up information not present in the reports.",
        "",
        "---",
    ]
    for i, data in enumerate(analyses, 1):
        ticker = data.get("company_of_interest", "Unknown")
        date = data.get("trade_date", "Unknown")
        parts.append(f"\n## Analysis {i}: {ticker} ({date})")
        parts.append("")
        if data.get("final_trade_decision"):
            parts.append(f"### Final Decision\n{sanitize_report(data['final_trade_decision'])}\n")
        if data.get("market_report"):
            parts.append(f"### Market Analysis\n{sanitize_report(data['market_report'])}\n")
        if data.get("news_report"):
            parts.append(f"### News\n{sanitize_report(data['news_report'])}\n")
        if data.get("fundamentals_report"):
            parts.append(f"### Fundamentals\n{sanitize_report(data['fundamentals_report'])}\n")
        parts.append("---")
    return "\n".join(parts)


def _render_multi_chat():
    """Render the multi-analysis chat mode."""
    records = list_history()
    if len(records) < 2:
        st.info("You need at least 2 saved analyses for multi-mode. Run more analyses first.")
        return

    with st.sidebar:
        st.markdown("### Select Analyses (2-5)")

        # Build options
        options_map = {f"{r['ticker']}  ·  {r['date']}  [{r['rating']}]": r for r in records}
        labels = list(options_map.keys())

        # Handle prefill from Compare view
        prefill = st.session_state.pop("chat_multi_prefill", None)
        default_selections = []
        if prefill:
            for key in prefill:
                parts = key.split("|")
                if len(parts) == 2:
                    for lbl, r in options_map.items():
                        if r["ticker"] == parts[0] and r["date"] == parts[1]:
                            default_selections.append(lbl)
                            break

        selected_labels = st.multiselect(
            "Analyses", labels, default=default_selections or None,
            max_selections=5, key="chat_multi_select",
        )

        st.divider()
        st.markdown("### Chat Model")
        provider = st.selectbox("Provider", list(_PROVIDER_MODELS.keys()),
                               index=list(_PROVIDER_MODELS.keys()).index(_DEFAULT_PROVIDER),
                               key="chat_multi_provider")
        model = st.selectbox("Model", _PROVIDER_MODELS[provider]["models"],
                            index=_PROVIDER_MODELS[provider]["default"],
                            key="chat_multi_model")

        st.divider()
        if st.button("🗑 Clear Chat", use_container_width=True, key="chat_multi_clear"):
            st.session_state["chat_multi_history"] = []
            st.rerun()

    # ── Guard: need at least 2 ────────────────────────────────────────────────
    if len(selected_labels) < 2:
        st.info("Select at least 2 analyses to start a multi-analysis chat.")
        # Preserve existing history if user deselects
        if st.session_state.get("chat_multi_history"):
            st.caption(f"💬 {len(st.session_state['chat_multi_history'])} messages saved — select 2+ analyses to continue.")
        return

    # Build context
    selected_data = [options_map[lbl]["data"] for lbl in selected_labels]
    context = _build_multi_context(selected_data)

    # Context size warning
    est_tokens = int(len(context.split()) * 1.3)
    limit = _MODEL_CONTEXT_LIMITS.get(model, _DEFAULT_CONTEXT_LIMIT)
    if est_tokens > limit * 0.5:
        st.warning(f"⚠️ Combined context is large (~{est_tokens:,} tokens). Consider fewer analyses or a larger model.")

    # Show selected analyses summary
    for lbl in selected_labels:
        r = options_map[lbl]
        color = RATING_COLORS.get(r["rating"], "#6b7280")
        st.markdown(
            f'<span style="background:{color}22;border:1px solid {color};color:{color};'
            f'padding:2px 8px;border-radius:6px;font-size:12px;margin-right:4px">'
            f'{r["ticker"]} {r["rating"]}</span>',
            unsafe_allow_html=True,
        )

    st.divider()

    # Load/init history
    history: List[Dict[str, str]] = st.session_state.get("chat_multi_history", [])

    # Render conversation
    for msg in history:
        with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
            st.markdown(msg["content"])

    # Chat input
    user_input = st.chat_input("Compare these analyses...")
    if user_input:
        user_msg = {"role": "user", "content": user_input, "timestamp": _timestamp()}
        history.append(user_msg)
        st.session_state["chat_multi_history"] = history

        with st.chat_message("user", avatar="🧑"):
            st.markdown(user_input)

        with st.chat_message("assistant", avatar="🤖"):
            placeholder = st.empty()
            streamed = ""
            full_reply = ""
            for chunk in _stream_llm(provider, model, context, history):
                if isinstance(chunk, tuple) and chunk[0] == "__DONE__":
                    full_reply = chunk[1]
                    break
                streamed += chunk
                placeholder.markdown(streamed + "▌")
            final = full_reply or streamed
            placeholder.markdown(final)

        reply_msg = {"role": "assistant", "content": final, "timestamp": _timestamp()}
        history.append(reply_msg)
        st.session_state["chat_multi_history"] = history

        # Persist to SQLite
        try:
            from dashboard.db import is_db_available, get_db
            if is_db_available():
                conn = get_db()
                conv_id = st.session_state.get("_chat_multi_conv_id")
                if not conv_id:
                    from uuid import uuid4
                    conv_id = f"multi_{uuid4().hex[:8]}"
                    st.session_state["_chat_multi_conv_id"] = conv_id
                for msg in [user_msg, reply_msg]:
                    for r in selected_data:
                        conn.execute(
                            "INSERT INTO chat_messages (conversation_id, analysis_ticker, analysis_date, mode, role, content) VALUES (?,?,?,?,?,?)",
                            (conv_id, r.get("company_of_interest", ""), r.get("trade_date", ""),
                             "multi", msg["role"], msg["content"]),
                        )
                conn.commit()
        except Exception:
            pass

        st.rerun()


# ── Single-Mode Chat (original) ──────────────────────────────────────────────

def _render_single_chat():

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### Load Analysis")

        records = list_history()
        if not records:
            st.warning("No past analyses found. Run an analysis first.")
            st.stop()

        # Annotate each record with its saved message count so the user can
        # see at a glance which analyses already have a conversation.
        def _label(r: Dict[str, Any]) -> str:
            count = _cached_chat_msg_count(str(r["file"]))
            badge = f"  💬{count}" if count else ""
            return f"{r['ticker']}  ·  {r['date']}  [{r['rating']}]{badge}"

        options_labels = [_label(r) for r in records]
        options_map    = dict(zip(options_labels, records))

        # If navigated here via "Open in Chat", find the matching analysis
        _prefill_ticker = st.session_state.get("chat_prefill_ticker")
        _prefill_date = st.session_state.get("chat_prefill_date")
        _prefill_index = 0  # default to first

        if _prefill_ticker and _prefill_date:
            _found = next(
                (i for i, r in enumerate(records)
                 if r["ticker"] == _prefill_ticker and r["date"] == _prefill_date),
                None,
            )
            if _found is not None:
                _prefill_index = _found
            else:
                st.info(f"Analysis for {_prefill_ticker} on {_prefill_date} not found. It may have been deleted.")

        selected_label  = st.selectbox(
            "Choose analysis",
            options_labels,
            index=_prefill_index,
            key="chat_select_analysis",
        )
        # Clear the prefill once consumed
        st.session_state.pop("chat_prefill_ticker", None)
        st.session_state.pop("chat_prefill_date",   None)
        selected_record = options_map[selected_label]
        analysis_key    = f"{selected_record['ticker']}|{selected_record['date']}"
        analysis_file: Path = selected_record["file"]

        # Auto-load when selection changes
        if st.session_state.get("chat_analysis_key") != analysis_key:
            data    = selected_record["data"]
            history = load_chat_history(analysis_file)
            st.session_state["chat_analysis_key"]  = analysis_key
            st.session_state["chat_analysis_file"] = analysis_file
            st.session_state["chat_analysis_data"] = data
            st.session_state["chat_context_str"]   = _build_context(data)
            st.session_state["chat_history"]       = history

        st.divider()

        # ── Model config ──────────────────────────────────────────────────────
        st.markdown("### Chat Model")
        provider = st.selectbox(
            "Provider",
            list(_PROVIDER_MODELS.keys()),
            index=list(_PROVIDER_MODELS.keys()).index(_DEFAULT_PROVIDER),
            key="chat_provider",
        )
        model = st.selectbox(
            "Model",
            _PROVIDER_MODELS[provider]["models"],
            index=_PROVIDER_MODELS[provider]["default"],
            key="chat_model",
        )

        st.divider()

        # ── Actions ───────────────────────────────────────────────────────────
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🗑 Clear Chat", use_container_width=True,
                         help="Wipe the conversation (also deletes saved history)"):
                st.session_state["chat_history"] = []
                save_chat_history(
                    st.session_state.get("chat_analysis_file", analysis_file), []
                )
                st.rerun()
        with col_b:
            if st.button("📥 Export", use_container_width=True,
                         help="Download the conversation as a text file"):
                hist = st.session_state.get("chat_history", [])
                if hist:
                    lines = []
                    for m in hist:
                        ts   = m.get("timestamp", "")
                        role = "You" if m["role"] == "user" else "Assistant"
                        lines.append(f"[{ts}] {role}:\n{m['content']}\n")
                    st.session_state["chat_export_text"] = "\n".join(lines)

        # Render download button if export was requested
        if st.session_state.get("chat_export_text"):
            ticker_slug = selected_record["ticker"]
            date_slug   = selected_record["date"]
            st.download_button(
                "⬇ Download .txt",
                data=st.session_state["chat_export_text"],
                file_name=f"chat_{ticker_slug}_{date_slug}.txt",
                mime="text/plain",
                use_container_width=True,
            )

        # Context size hint
        ctx = st.session_state.get("chat_context_str", "")
        if ctx:
            st.caption(f"📄 ~{len(ctx.split()):,} words of analysis loaded")

    # ── Guard: nothing loaded yet ─────────────────────────────────────────────
    if "chat_analysis_data" not in st.session_state:
        st.info("👈 Select an analysis from the sidebar to start chatting.")
        return

    data         = st.session_state["chat_analysis_data"]
    context      = st.session_state["chat_context_str"]
    analysis_file: Path = st.session_state.get("chat_analysis_file", analysis_file)
    history: List[Dict[str, str]] = st.session_state.get("chat_history", [])

    ticker = data.get("company_of_interest", "—")
    rating = selected_record["rating"]

    # ── Analysis card ─────────────────────────────────────────────────────────
    _analysis_card(data, rating, len(history))

    # ── Restore notice ────────────────────────────────────────────────────────
    if history:
        st.markdown(
            f'<div style="background:#14532d22;border:1px solid #16a34a;border-radius:6px;'
            f'padding:6px 14px;color:#86efac;font-size:13px;margin-bottom:8px">'
            f'✅ Restored {len(history)} saved message{"s" if len(history) != 1 else ""} '
            f'— conversation continues from where you left off'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Suggested questions (only when chat is empty) ─────────────────────────
    if not history:
        st.markdown("#### 💡 Suggested questions — click to ask")
        suggestions = _suggested_questions(ticker, rating)
        cols = st.columns(2)
        for i, q in enumerate(suggestions):
            if cols[i % 2].button(q, key=f"suggest_{i}", use_container_width=True):
                msg = {"role": "user", "content": q, "timestamp": _timestamp()}
                history.append(msg)
                st.session_state["chat_history"] = history

                with st.chat_message("user", avatar="🧑"):
                    st.markdown(q)
                    st.caption(msg["timestamp"])

                with st.chat_message("assistant", avatar="🤖"):
                    placeholder = st.empty()
                    streamed = ""
                    full_reply = ""
                    ts = _timestamp()
                    for chunk in _stream_llm(provider, model, context, history):
                        if isinstance(chunk, tuple) and chunk[0] == "__DONE__":
                            full_reply = chunk[1]
                            break
                        streamed += chunk
                        placeholder.markdown(streamed + "▌")
                    final = full_reply or streamed
                    placeholder.markdown(final)
                    st.caption(ts)

                reply_msg = {"role": "assistant", "content": final, "timestamp": ts}
                history.append(reply_msg)
                st.session_state["chat_history"] = history
                save_chat_history(analysis_file, history)
                st.rerun()
        st.divider()

    # ── Render conversation ───────────────────────────────────────────────────
    for msg in history:
        is_user = msg["role"] == "user"
        with st.chat_message(msg["role"], avatar="🧑" if is_user else "🤖"):
            st.markdown(msg["content"])
            ts = msg.get("timestamp")
            if ts:
                st.caption(ts)

    # ── Chat input ────────────────────────────────────────────────────────────
    user_input = st.chat_input(f"Ask anything about the {ticker} analysis…")

    if user_input:
        user_msg = {"role": "user", "content": user_input, "timestamp": _timestamp()}
        history.append(user_msg)
        st.session_state["chat_history"] = history

        with st.chat_message("user", avatar="🧑"):
            st.markdown(user_input)
            st.caption(user_msg["timestamp"])

        # Stream the reply token by token
        with st.chat_message("assistant", avatar="🤖"):
            placeholder = st.empty()
            streamed    = ""
            full_reply  = ""
            ts          = _timestamp()

            for chunk in _stream_llm(provider, model, context, history):
                if isinstance(chunk, tuple) and chunk[0] == "__DONE__":
                    full_reply = chunk[1]
                    break
                streamed += chunk
                placeholder.markdown(streamed + "▌")   # blinking cursor effect

            # Final render without cursor
            final = full_reply or streamed
            placeholder.markdown(final)
            st.caption(ts)

        reply_msg = {"role": "assistant", "content": final, "timestamp": ts}
        history.append(reply_msg)
        st.session_state["chat_history"] = history
        save_chat_history(analysis_file, history)
        st.rerun()
