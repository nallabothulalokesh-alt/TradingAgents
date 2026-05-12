# TradingAgents/graph/setup.py

import logging
from typing import Any, Callable, Dict
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.agents.utils.agent_states import AgentState

from .conditional_logic import ConditionalLogic

logger = logging.getLogger(__name__)


# ── Subgraph helpers for parallel analyst execution ───────────────────────────

def _build_analyst_subgraph(
    analyst_type: str,
    analyst_node: Callable,
    tool_node: ToolNode,
    conditional_fn: Callable,
) -> Any:
    """Build an isolated subgraph for one analyst.

    Each subgraph has its own messages state so create_msg_delete()
    only clears THIS analyst's messages (not other parallel branches).

    Graph structure: START → Analyst → (Tools loop) → Clear → END
    """
    sub = StateGraph(AgentState)
    sub.add_node("Analyst", analyst_node)
    sub.add_node("Tools", tool_node)
    sub.add_node("Clear", create_msg_delete())

    sub.add_edge(START, "Analyst")

    # Remap conditional output: original returns "tools_{type}" or "Msg Clear {Type}"
    # Subgraph uses "Tools" and "Clear"
    tools_name = f"tools_{analyst_type}"
    clear_name = f"Msg Clear {analyst_type.capitalize()}"

    def _route(state):
        result = conditional_fn(state)
        if result == tools_name:
            return "Tools"
        return "Clear"

    sub.add_conditional_edges("Analyst", _route, ["Tools", "Clear"])
    sub.add_edge("Tools", "Analyst")
    sub.add_edge("Clear", END)

    return sub.compile()


def _make_analyst_wrapper(
    subgraph: Any,
    report_field: str,
    analyst_type: str,
) -> Callable:
    """Create a parent-graph node that invokes an analyst subgraph.

    The wrapper:
    1. Builds minimal initial state for the subgraph
    2. Invokes the compiled subgraph (isolated messages)
    3. Returns only the report field to merge into parent state
    4. Catches exceptions → returns empty report + warning
    """
    def wrapper(state: Dict[str, Any]) -> Dict[str, Any]:
        try:
            init = {
                "messages": [("human", state["company_of_interest"])],
                "company_of_interest": state["company_of_interest"],
                "trade_date": state["trade_date"],
                report_field: "",
                "warnings": [],
            }
            result = subgraph.invoke(init, {"recursion_limit": 50})
            return {report_field: result.get(report_field, "")}
        except Exception as e:
            logger.warning("Analyst %s failed: %s", analyst_type, e)
            return {
                report_field: "",
                "warnings": [f"{analyst_type.capitalize()} Analyst failed: {e}"],
            }

    wrapper.__name__ = f"run_{analyst_type}_analyst"
    return wrapper


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    # Analyst type → report field mapping
    _REPORT_FIELDS = {
        "market": "market_report",
        "social": "sentiment_report",
        "news": "news_report",
        "fundamentals": "fundamentals_report",
    }

    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        tool_nodes: Dict[str, ToolNode],
        conditional_logic: ConditionalLogic,
        config: Dict[str, Any] = None,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.conditional_logic = conditional_logic
        self.config = config or {}

    def setup_graph(
        self, selected_analysts=["market", "social", "news", "fundamentals"]
    ):
        """Set up and compile the agent workflow graph.

        When parallel_analysts is True (default), analysts run as isolated
        subgraphs concurrently. When False, they run sequentially (original behavior).
        """
        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        parallel = self.config.get("parallel_analysts", True)

        if parallel:
            return self._build_parallel_graph(selected_analysts)
        else:
            return self._build_sequential_graph(selected_analysts)

    def _build_parallel_graph(self, selected_analysts):
        """Build graph with parallel analyst subgraphs."""
        workflow = StateGraph(AgentState)

        # Build and add analyst subgraph wrappers
        for analyst_type in selected_analysts:
            analyst_node = self._create_analyst_node(analyst_type)
            tool_node = self.tool_nodes[analyst_type]
            conditional_fn = getattr(self.conditional_logic, f"should_continue_{analyst_type}")
            report_field = self._REPORT_FIELDS[analyst_type]

            subgraph = _build_analyst_subgraph(analyst_type, analyst_node, tool_node, conditional_fn)
            wrapper = _make_analyst_wrapper(subgraph, report_field, analyst_type)
            workflow.add_node(f"{analyst_type.capitalize()} Analyst", wrapper)

        # Barrier node — waits for all parallel branches
        workflow.add_node("Analyst Barrier", lambda state: state)

        # Fan-out: START → all analysts in parallel
        for analyst_type in selected_analysts:
            workflow.add_edge(START, f"{analyst_type.capitalize()} Analyst")

        # Fan-in: all analysts → barrier
        for analyst_type in selected_analysts:
            workflow.add_edge(f"{analyst_type.capitalize()} Analyst", "Analyst Barrier")

        # Add post-analyst pipeline (unchanged)
        self._add_post_analyst_nodes(workflow)
        workflow.add_edge("Analyst Barrier", "Bull Researcher")
        self._add_post_analyst_edges(workflow)

        return workflow

    def _build_sequential_graph(self, selected_analysts):
        """Build graph with sequential analyst chain (original behavior)."""
        workflow = StateGraph(AgentState)

        # Add analyst nodes sequentially
        for analyst_type in selected_analysts:
            analyst_node = self._create_analyst_node(analyst_type)
            workflow.add_node(f"{analyst_type.capitalize()} Analyst", analyst_node)
            workflow.add_node(f"Msg Clear {analyst_type.capitalize()}", create_msg_delete())
            workflow.add_node(f"tools_{analyst_type}", self.tool_nodes[analyst_type])

        # Add post-analyst pipeline
        self._add_post_analyst_nodes(workflow)

        # Wire analysts in sequence
        workflow.add_edge(START, f"{selected_analysts[0].capitalize()} Analyst")
        for i, analyst_type in enumerate(selected_analysts):
            current_analyst = f"{analyst_type.capitalize()} Analyst"
            current_tools = f"tools_{analyst_type}"
            current_clear = f"Msg Clear {analyst_type.capitalize()}"

            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{analyst_type}"),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)

            if i < len(selected_analysts) - 1:
                next_analyst = f"{selected_analysts[i + 1].capitalize()} Analyst"
                workflow.add_edge(current_clear, next_analyst)
            else:
                workflow.add_edge(current_clear, "Bull Researcher")

        self._add_post_analyst_edges(workflow)
        return workflow

    def _create_analyst_node(self, analyst_type: str):
        """Create the analyst callable for a given type."""
        creators = {
            "market": create_market_analyst,
            "social": create_social_media_analyst,
            "news": create_news_analyst,
            "fundamentals": create_fundamentals_analyst,
        }
        return creators[analyst_type](self.quick_thinking_llm)

    def _add_post_analyst_nodes(self, workflow):
        """Add all nodes after the analyst phase."""
        workflow.add_node("Bull Researcher", create_bull_researcher(self.quick_thinking_llm))
        workflow.add_node("Bear Researcher", create_bear_researcher(self.quick_thinking_llm))
        workflow.add_node("Research Manager", create_research_manager(self.deep_thinking_llm))
        workflow.add_node("Trader", create_trader(self.quick_thinking_llm))
        workflow.add_node("Aggressive Analyst", create_aggressive_debator(self.quick_thinking_llm))
        workflow.add_node("Neutral Analyst", create_neutral_debator(self.quick_thinking_llm))
        workflow.add_node("Conservative Analyst", create_conservative_debator(self.quick_thinking_llm))
        workflow.add_node("Portfolio Manager", create_portfolio_manager(self.deep_thinking_llm))

    def _add_post_analyst_edges(self, workflow):
        """Add all edges after the analyst phase (research debate → trader → risk → PM)."""
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {"Bear Researcher": "Bear Researcher", "Research Manager": "Research Manager"},
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {"Bull Researcher": "Bull Researcher", "Research Manager": "Research Manager"},
        )
        workflow.add_edge("Research Manager", "Trader")

        # Risk phase — always sequential (risk analysts share risk_debate_state,
        # parallel execution would cause state corruption)
        workflow.add_edge("Trader", "Aggressive Analyst")
        workflow.add_conditional_edges(
            "Aggressive Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {"Conservative Analyst": "Conservative Analyst", "Portfolio Manager": "Portfolio Manager"},
        )
        workflow.add_conditional_edges(
            "Conservative Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {"Neutral Analyst": "Neutral Analyst", "Portfolio Manager": "Portfolio Manager"},
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {"Aggressive Analyst": "Aggressive Analyst", "Portfolio Manager": "Portfolio Manager"},
        )
        workflow.add_edge("Portfolio Manager", END)
