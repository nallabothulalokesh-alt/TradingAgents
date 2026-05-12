"""Background thread runner for TradingAgentsGraph.

Supports two modes:
  Full Mode  — all agents run fresh (default)
  Fast Mode  — fundamentals + research plan reused from a prior run;
               only market analyst, news analyst, social analyst (if selected),
               trader, risk team, and portfolio manager run fresh.

Fast Mode works by:
  1. Pre-seeding the initial LangGraph state with the reused report fields
  2. Building a reduced graph that only includes the agents that need to run
     (skips Fundamentals Analyst, Bull/Bear Researchers, Research Manager)
  3. Injecting the reused investment_plan directly so the Trader has context

The graph streams state snapshots after every node. We diff each snapshot
against the previous one to detect which agent just completed and update
RunState accordingly — no LangChain callbacks needed.
"""

from __future__ import annotations

import threading
from datetime import datetime as _dt
from typing import Any, Dict, List, Optional

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.graph.setup import GraphSetup
from tradingagents.agents.utils.agent_states import InvestDebateState, RiskDebateState

from dashboard.utils import RunState, ANALYST_TO_AGENT


# ── Agent → report field mapping ──────────────────────────────────────────────
_FIELD_TO_AGENT = [
    ("market_report",          "Market Analyst"),
    ("sentiment_report",       "Social Analyst"),
    ("news_report",            "News Analyst"),
    ("fundamentals_report",    "Fundamentals Analyst"),
    ("investment_plan",        "Research Manager"),
    ("trader_investment_plan", "Trader"),
    ("final_trade_decision",   "Portfolio Manager"),
]

_REPORT_SECTIONS = [
    "market_report", "sentiment_report", "news_report", "fundamentals_report",
    "investment_plan", "trader_investment_plan", "final_trade_decision",
]

# Agents that Fast Mode skips (their output is reused from prior run)
_FAST_MODE_SKIPPED = {
    "Fundamentals Analyst", "Bull Researcher", "Bear Researcher", "Research Manager"
}

# Analysts Fast Mode still runs (market + news + social are time-sensitive)
_FAST_MODE_FRESH_ANALYSTS = ["market", "news", "social"]


# ── Agent status builder ──────────────────────────────────────────────────────

def build_agent_status(selected_analysts: List[str],
                       fast_mode: bool = False,
                       reused_agents: Optional[List[str]] = None) -> Dict[str, str]:
    """Build initial agent_status dict.

    Fast Mode marks skipped agents as 'reused' so the UI can show them differently.
    """
    status: Dict[str, str] = {}
    for a in selected_analysts:
        if a in ANALYST_TO_AGENT:
            status[ANALYST_TO_AGENT[a]] = "pending"
    for agent in [
        "Bull Researcher", "Bear Researcher", "Research Manager",
        "Trader",
        "Aggressive Analyst", "Conservative Analyst", "Neutral Analyst",
        "Portfolio Manager",
    ]:
        status[agent] = "pending"

    if fast_mode and reused_agents:
        for agent in reused_agents:
            if agent in status:
                status[agent] = "reused"

    return status


# ── State diff → RunState updates ─────────────────────────────────────────────

def _update_from_state(state: dict, run_state: RunState, prev: dict):
    """Diff current vs previous graph state snapshot, update RunState."""

    # Extract warnings
    warnings = state.get("warnings", [])
    prev_warnings = prev.get("warnings", [])
    if len(warnings) > len(prev_warnings):
        for warning in warnings[len(prev_warnings):]:
            run_state.append_log(f"⚠️ {warning}")

    # Report fields → agent done
    for field, agent in _FIELD_TO_AGENT:
        curr_val = state.get(field, "")
        prev_val = prev.get(field, "")
        if curr_val and curr_val != prev_val:
            run_state.set_report(field, curr_val)
            # Only mark done if not already reused
            if run_state.snapshot()["agent_status"].get(agent) != "reused":
                run_state.set_agent(agent, "done")
                run_state.append_log(f"✓ {agent} completed")

    # Research debate progress
    debate      = state.get("investment_debate_state") or {}
    prev_debate = prev.get("investment_debate_state") or {}
    debate_count = debate.get("count", 0) if isinstance(debate, dict) else 0
    prev_count   = prev_debate.get("count", 0) if isinstance(prev_debate, dict) else 0

    if debate_count > prev_count:
        bull_grew = len(debate.get("bull_history") or "") > len(prev_debate.get("bull_history") or "")
        bear_grew = len(debate.get("bear_history") or "") > len(prev_debate.get("bear_history") or "")
        if bull_grew:
            run_state.set_agent("Bull Researcher", "done")
            run_state.set_agent("Bear Researcher", "running")
            run_state.append_log("✓ Bull Researcher turn complete")
        elif bear_grew:
            run_state.set_agent("Bear Researcher", "done")
            run_state.set_agent("Bull Researcher", "running")
            run_state.append_log("✓ Bear Researcher turn complete")

    # Mark Bull running at debate start
    if debate_count == 0 and prev_count == 0:
        snap = run_state.snapshot()
        analysts_done = all(
            snap["agent_status"].get(a) in ("done", "reused")
            for a in ["Market Analyst", "Social Analyst", "News Analyst", "Fundamentals Analyst"]
            if a in snap["agent_status"]
        )
        if analysts_done and snap["agent_status"].get("Bull Researcher") == "pending":
            run_state.set_agent("Bull Researcher", "running")
            run_state.append_log("▶ Bull Researcher started")

    # Risk debate progress
    risk      = state.get("risk_debate_state") or {}
    prev_risk = prev.get("risk_debate_state") or {}
    risk_count      = risk.get("count", 0) if isinstance(risk, dict) else 0
    prev_risk_count = prev_risk.get("count", 0) if isinstance(prev_risk, dict) else 0

    if risk_count > prev_risk_count:
        if len(risk.get("aggressive_history") or "") > len(prev_risk.get("aggressive_history") or ""):
            run_state.set_agent("Aggressive Analyst", "done")
            run_state.append_log("✓ Aggressive Analyst turn complete")
        if len(risk.get("conservative_history") or "") > len(prev_risk.get("conservative_history") or ""):
            run_state.set_agent("Conservative Analyst", "done")
            run_state.append_log("✓ Conservative Analyst turn complete")
        if len(risk.get("neutral_history") or "") > len(prev_risk.get("neutral_history") or ""):
            run_state.set_agent("Neutral Analyst", "done")
            run_state.append_log("✓ Neutral Analyst turn complete")

    # Trader running signal
    if (state.get("investment_plan") and not prev.get("investment_plan")
            and not state.get("trader_investment_plan")):
        run_state.set_agent("Trader", "running")
        run_state.append_log("▶ Trader started")

    # Portfolio Manager running signal
    if (state.get("trader_investment_plan") and not prev.get("trader_investment_plan")
            and not state.get("final_trade_decision")):
        run_state.set_agent("Portfolio Manager", "running")
        run_state.append_log("▶ Portfolio Manager started")

    # First analyst running signal
    snap = run_state.snapshot()
    if all(s == "pending" for s in snap["agent_status"].values()) and state.get("messages"):
        # In parallel mode, all analysts start simultaneously
        analyst_agents = [a for a in snap["agent_status"] if "Analyst" in a and a not in (
            "Aggressive Analyst", "Conservative Analyst", "Neutral Analyst")]
        for agent in analyst_agents:
            if snap["agent_status"].get(agent) == "pending":
                run_state.set_agent(agent, "running")
                run_state.append_log(f"▶ {agent} started")


# ── Fast Mode: build reduced graph ────────────────────────────────────────────

def _build_fast_graph(graph_obj: TradingAgentsGraph,
                      selected_analysts: List[str],
                      prior_run: Dict[str, Any]) -> Any:
    """Build a reduced LangGraph that skips Fundamentals + Research team.

    The reduced graph runs:
      - Market Analyst (always — price-sensitive)
      - News Analyst (always — time-sensitive)
      - Social Analyst (if selected — time-sensitive)
      - Trader (reads fresh market/news + reused investment_plan)
      - Risk Team (Aggressive / Conservative / Neutral)
      - Portfolio Manager

    Supports parallel mode (subgraphs) and sequential mode based on config.
    """
    from langgraph.graph import END, START, StateGraph
    from tradingagents.agents import (
        create_market_analyst, create_news_analyst, create_social_media_analyst,
        create_trader, create_aggressive_debator, create_conservative_debator,
        create_neutral_debator, create_portfolio_manager, create_msg_delete,
        AgentState,
    )
    from tradingagents.graph.setup import _build_analyst_subgraph, _make_analyst_wrapper

    # Only keep time-sensitive analysts
    fast_analysts = [a for a in selected_analysts if a in _FAST_MODE_FRESH_ANALYSTS]
    if not fast_analysts:
        fast_analysts = ["market", "news"]

    parallel = graph_obj.config.get("parallel_analysts", True)

    # Create analyst nodes
    analyst_creators = {
        "market": create_market_analyst,
        "news": create_news_analyst,
        "social": create_social_media_analyst,
    }

    report_fields = {
        "market": "market_report",
        "news": "news_report",
        "social": "sentiment_report",
    }

    workflow = StateGraph(AgentState)

    if parallel and len(fast_analysts) > 1:
        # Parallel mode: subgraphs per analyst → barrier → Trader
        for analyst_type in fast_analysts:
            creator = analyst_creators[analyst_type]
            analyst_node = creator(graph_obj.quick_thinking_llm)
            tool_node = graph_obj.tool_nodes[analyst_type]
            conditional_fn = getattr(graph_obj.conditional_logic, f"should_continue_{analyst_type}")
            report_field = report_fields[analyst_type]

            subgraph = _build_analyst_subgraph(analyst_type, analyst_node, tool_node, conditional_fn)
            wrapper = _make_analyst_wrapper(subgraph, report_field, analyst_type)
            workflow.add_node(f"{analyst_type.capitalize()} Analyst", wrapper)

        workflow.add_node("Analyst Barrier", lambda state: state)

        for analyst_type in fast_analysts:
            workflow.add_edge(START, f"{analyst_type.capitalize()} Analyst")
            workflow.add_edge(f"{analyst_type.capitalize()} Analyst", "Analyst Barrier")

        # Barrier → Trader (skip research team)
        workflow.add_node("Trader", create_trader(graph_obj.quick_thinking_llm))
        workflow.add_edge("Analyst Barrier", "Trader")
    else:
        # Sequential mode: chain analysts → Trader
        for analyst_type in fast_analysts:
            creator = analyst_creators[analyst_type]
            workflow.add_node(f"{analyst_type.capitalize()} Analyst", creator(graph_obj.quick_thinking_llm))
            workflow.add_node(f"Msg Clear {analyst_type.capitalize()}", create_msg_delete())
            workflow.add_node(f"tools_{analyst_type}", graph_obj.tool_nodes[analyst_type])

        workflow.add_edge(START, f"{fast_analysts[0].capitalize()} Analyst")

        for i, analyst_type in enumerate(fast_analysts):
            current_analyst = f"{analyst_type.capitalize()} Analyst"
            current_tools = f"tools_{analyst_type}"
            current_clear = f"Msg Clear {analyst_type.capitalize()}"

            workflow.add_conditional_edges(
                current_analyst,
                getattr(graph_obj.conditional_logic, f"should_continue_{analyst_type}"),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)

            if i < len(fast_analysts) - 1:
                next_analyst = f"{fast_analysts[i + 1].capitalize()} Analyst"
                workflow.add_edge(current_clear, next_analyst)
            else:
                workflow.add_node("Trader", create_trader(graph_obj.quick_thinking_llm))
                workflow.add_edge(current_clear, "Trader")

    # Trader → Risk Team → Portfolio Manager (sequential — risk analysts share state)
    workflow.add_node("Aggressive Analyst", create_aggressive_debator(graph_obj.quick_thinking_llm))
    workflow.add_node("Conservative Analyst", create_conservative_debator(graph_obj.quick_thinking_llm))
    workflow.add_node("Neutral Analyst", create_neutral_debator(graph_obj.quick_thinking_llm))
    workflow.add_node("Portfolio Manager", create_portfolio_manager(graph_obj.deep_thinking_llm))

    workflow.add_edge("Trader", "Aggressive Analyst")
    workflow.add_conditional_edges(
        "Aggressive Analyst",
        graph_obj.conditional_logic.should_continue_risk_analysis,
        {"Conservative Analyst": "Conservative Analyst", "Portfolio Manager": "Portfolio Manager"},
    )
    workflow.add_conditional_edges(
        "Conservative Analyst",
        graph_obj.conditional_logic.should_continue_risk_analysis,
        {"Neutral Analyst": "Neutral Analyst", "Portfolio Manager": "Portfolio Manager"},
    )
    workflow.add_conditional_edges(
        "Neutral Analyst",
        graph_obj.conditional_logic.should_continue_risk_analysis,
        {"Aggressive Analyst": "Aggressive Analyst", "Portfolio Manager": "Portfolio Manager"},
    )
    workflow.add_edge("Portfolio Manager", END)

    return workflow.compile()


def _build_fast_initial_state(graph_obj: TradingAgentsGraph,
                               ticker: str,
                               trade_date: str,
                               prior_run: Dict[str, Any]) -> Dict[str, Any]:
    """Build initial state pre-seeded with reused data from prior run."""
    past_context = graph_obj.memory_log.get_past_context(ticker)
    state = graph_obj.propagator.create_initial_state(
        ticker, trade_date, past_context=past_context
    )

    # Inject reused fundamentals
    if prior_run.get("fundamentals_report"):
        prior_date = prior_run.get("_prior_date", prior_run.get("trade_date", "prior"))
        state["fundamentals_report"] = (
            f"[Reused from {prior_date} — fundamentals are quarterly, unchanged]\n\n"
            + prior_run["fundamentals_report"]
        )

    # Inject reused investment plan (Research Manager output)
    # This gives the Trader the prior research context alongside fresh market/news
    if prior_run.get("investment_plan"):
        prior_date = prior_run.get("_prior_date", prior_run.get("trade_date", "prior"))
        state["investment_plan"] = (
            f"[Reused from {prior_date} — based on prior fundamentals analysis]\n\n"
            + prior_run["investment_plan"]
        )

    return state


# ── Public API ────────────────────────────────────────────────────────────────

def run_analysis(
    run_state: RunState,
    ticker: str,
    trade_date: str,
    selected_analysts: List[str],
    config: Dict[str, Any],
    prior_run: Optional[Dict[str, Any]] = None,   # Fast Mode: prior run data
    portfolio_context: Optional[str] = None,       # Portfolio context to inject
):
    """Launch analysis in a background thread, streaming state into run_state.

    Args:
        prior_run: If provided, enables Fast Mode — fundamentals and research
                   plan are reused from this prior run. Only market/news/social
                   analysts + trader/risk/PM run fresh.
    """
    fast_mode = prior_run is not None

    # Determine which agents are reused vs fresh for status display
    reused_agents = []
    if fast_mode:
        reused_agents = ["Fundamentals Analyst", "Bull Researcher",
                         "Bear Researcher", "Research Manager"]

    # Set running=True BEFORE spawning the thread so the very next
    # st.rerun() in the UI sees running=True immediately (no race condition).
    run_state.start(ticker, trade_date, build_agent_status(
        selected_analysts, fast_mode=fast_mode, reused_agents=reused_agents
    ))
    run_state.append_log(f"Starting {'Fast' if fast_mode else 'Full'} Mode analysis: {ticker} on {trade_date}")

    def _worker():
        # THREAD SAFETY: This runs on a background thread.
        # Do NOT access st.session_state from here.
        try:
            mode_label = "Fast Mode" if fast_mode else "Full Mode"
            run_state.append_log(f"Starting {mode_label} analysis: {ticker} on {trade_date}")

            if fast_mode:
                prior_date = prior_run.get("_prior_date", "?")
                run_state.append_log(f"  Reusing fundamentals + research plan from {prior_date}")
                run_state.append_log(f"  Running fresh: market, news, trader, risk, PM")

            run_state.append_log("Initializing LLM clients…")
            graph_obj = TradingAgentsGraph(
                selected_analysts=selected_analysts,
                debug=False,
                config=config,
            )
            run_state.append_log("Graph ready — running pipeline…")

            # Resolve pending memory entries
            graph_obj.ticker = ticker
            graph_obj._resolve_pending_entries(ticker)

            # Build graph and initial state
            if fast_mode:
                graph   = _build_fast_graph(graph_obj, selected_analysts, prior_run)
                init_st = _build_fast_initial_state(graph_obj, ticker, trade_date, prior_run)

                # Pre-mark reused agents as done in RunState and log their reports
                for agent in reused_agents:
                    run_state.set_agent(agent, "reused")
                if prior_run.get("fundamentals_report"):
                    run_state.set_report("fundamentals_report", init_st["fundamentals_report"])
                    run_state.append_log("📦 Fundamentals Analyst — reused from prior run")
                if prior_run.get("investment_plan"):
                    run_state.set_report("investment_plan", init_st["investment_plan"])
                    run_state.append_log("📦 Research Manager — reused from prior run")
            else:
                graph   = graph_obj.graph
                past_context = graph_obj.memory_log.get_past_context(ticker)
                if portfolio_context:
                    past_context = f"{past_context}\n\nPortfolio Context:\n{portfolio_context}" if past_context else f"Portfolio Context:\n{portfolio_context}"
                init_st = graph_obj.propagator.create_initial_state(
                    ticker, trade_date, past_context=past_context
                )

            stream_args = {
                "stream_mode": "values",
                "config": {"recursion_limit": config.get("max_recur_limit", 100)},
            }

            prev_state: dict = {}
            final_state = None

            for snapshot in graph.stream(init_st, **stream_args):
                # ── Cancellation checkpoint ───────────────────────────────
                if run_state.cancelled:
                    run_state.append_log("⏹ Cancelled by user — stopping pipeline")
                    run_state.fail(Exception("Cancelled by user"))
                    return

                final_state = snapshot
                _update_from_state(snapshot, run_state, prev_state)
                prev_state = dict(snapshot)

            if final_state is None:
                raise RuntimeError("Graph produced no output")

            # Safety net: capture any reports not caught by streaming
            for section in _REPORT_SECTIONS:
                val = final_state.get(section)
                if val and section not in run_state.snapshot()["reports"]:
                    run_state.set_report(section, val)

            # In Fast Mode, also ensure reused sections are in final_state for saving
            if fast_mode:
                if not final_state.get("fundamentals_report") and init_st.get("fundamentals_report"):
                    final_state = dict(final_state)
                    final_state["fundamentals_report"] = init_st["fundamentals_report"]
                if not final_state.get("investment_plan") and init_st.get("investment_plan"):
                    final_state = dict(final_state)
                    final_state["investment_plan"] = init_st["investment_plan"]

            # Mark remaining pending/running agents as done
            for agent in list(run_state.agent_status.keys()):
                if run_state.agent_status[agent] in ("pending", "running"):
                    run_state.set_agent(agent, "done")

            # Save to disk and memory log
            graph_obj._log_state(trade_date, final_state)

            # Index into SQLite for fast dashboard queries
            try:
                from dashboard.db import index_analysis, is_db_available
                if is_db_available():
                    from pathlib import Path as _Path
                    from tradingagents.dataflows.utils import safe_ticker_component
                    safe_t = safe_ticker_component(ticker)
                    log_path = _Path(config.get("results_dir", "")) / safe_t / "TradingAgentsStrategy_logs" / f"full_states_log_{trade_date}.json"
                    index_analysis(log_path, graph_obj.log_states_dict.get(str(trade_date), final_state))
            except Exception as e:
                run_state.append_log(f"⚠️ SQLite indexing skipped: {e}")

            graph_obj.memory_log.store_decision(
                ticker=ticker,
                trade_date=trade_date,
                final_trade_decision=final_state["final_trade_decision"],
            )

            decision = graph_obj.process_signal(final_state["final_trade_decision"])
            run_state.finish(final_state, decision)
            run_state.append_log(f"✅ Complete — Decision: {decision}")

            # Bust the history cache so the new run appears immediately
            from dashboard.utils import invalidate_history_cache
            invalidate_history_cache()

        except Exception as exc:
            import traceback
            run_state.append_log(f"❌ Error: {exc}")
            run_state.append_log(traceback.format_exc())
            run_state.fail(exc)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t
