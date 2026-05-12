"""Tests for parallel analyst execution (Sprint 1A)."""

import pytest
from unittest.mock import MagicMock, patch
from tradingagents.graph.setup import (
    GraphSetup,
    _build_analyst_subgraph,
    _make_analyst_wrapper,
)
from tradingagents.graph.conditional_logic import ConditionalLogic


@pytest.fixture
def mock_llm():
    return MagicMock()


@pytest.fixture
def mock_tool_nodes():
    return {
        "market": MagicMock(),
        "social": MagicMock(),
        "news": MagicMock(),
        "fundamentals": MagicMock(),
    }


@pytest.fixture
def conditional_logic():
    return ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)


class TestParallelConfig:
    """Test that parallel_analysts config key is respected."""

    def test_default_config_has_parallel_analysts(self):
        from tradingagents.default_config import DEFAULT_CONFIG
        assert "parallel_analysts" in DEFAULT_CONFIG
        assert DEFAULT_CONFIG["parallel_analysts"] is True

    def test_dashboard_config_has_parallel_analysts(self):
        from dashboard.utils import DASHBOARD_CONFIG
        assert "parallel_analysts" in DASHBOARD_CONFIG
        assert DASHBOARD_CONFIG["parallel_analysts"] is True


class TestGraphSetupModes:
    """Test that setup_graph produces correct graph structure for both modes."""

    def test_parallel_mode_has_barrier_node(self, mock_llm, mock_tool_nodes, conditional_logic):
        setup = GraphSetup(mock_llm, mock_llm, mock_tool_nodes, conditional_logic,
                          config={"parallel_analysts": True})
        workflow = setup.setup_graph(["market", "news"])
        graph = workflow.compile()
        node_names = set(graph.nodes.keys())
        assert "Analyst Barrier" in node_names

    def test_parallel_mode_has_analyst_nodes(self, mock_llm, mock_tool_nodes, conditional_logic):
        setup = GraphSetup(mock_llm, mock_llm, mock_tool_nodes, conditional_logic,
                          config={"parallel_analysts": True})
        workflow = setup.setup_graph(["market", "news", "fundamentals"])
        graph = workflow.compile()
        node_names = set(graph.nodes.keys())
        assert "Market Analyst" in node_names
        assert "News Analyst" in node_names
        assert "Fundamentals Analyst" in node_names

    def test_parallel_mode_no_sequential_nodes(self, mock_llm, mock_tool_nodes, conditional_logic):
        """Parallel mode should NOT have tools_* or Msg Clear nodes in parent graph."""
        setup = GraphSetup(mock_llm, mock_llm, mock_tool_nodes, conditional_logic,
                          config={"parallel_analysts": True})
        workflow = setup.setup_graph(["market", "news"])
        graph = workflow.compile()
        node_names = set(graph.nodes.keys())
        assert "tools_market" not in node_names
        assert "Msg Clear Market" not in node_names

    def test_sequential_mode_no_barrier(self, mock_llm, mock_tool_nodes, conditional_logic):
        setup = GraphSetup(mock_llm, mock_llm, mock_tool_nodes, conditional_logic,
                          config={"parallel_analysts": False})
        workflow = setup.setup_graph(["market", "news"])
        graph = workflow.compile()
        node_names = set(graph.nodes.keys())
        assert "Analyst Barrier" not in node_names

    def test_sequential_mode_has_tools_and_clear(self, mock_llm, mock_tool_nodes, conditional_logic):
        setup = GraphSetup(mock_llm, mock_llm, mock_tool_nodes, conditional_logic,
                          config={"parallel_analysts": False})
        workflow = setup.setup_graph(["market", "news"])
        graph = workflow.compile()
        node_names = set(graph.nodes.keys())
        assert "tools_market" in node_names
        assert "Msg Clear Market" in node_names

    def test_both_modes_have_post_analyst_nodes(self, mock_llm, mock_tool_nodes, conditional_logic):
        """Both modes should have Bull/Bear Researchers, Trader, Risk team, PM."""
        for parallel in [True, False]:
            setup = GraphSetup(mock_llm, mock_llm, mock_tool_nodes, conditional_logic,
                              config={"parallel_analysts": parallel})
            workflow = setup.setup_graph(["market", "news"])
            graph = workflow.compile()
            node_names = set(graph.nodes.keys())
            for expected in ["Bull Researcher", "Bear Researcher", "Research Manager",
                           "Trader", "Aggressive Analyst", "Portfolio Manager"]:
                assert expected in node_names, f"{expected} missing in {'parallel' if parallel else 'sequential'} mode"

    def test_empty_analysts_raises(self, mock_llm, mock_tool_nodes, conditional_logic):
        setup = GraphSetup(mock_llm, mock_llm, mock_tool_nodes, conditional_logic,
                          config={"parallel_analysts": True})
        with pytest.raises(ValueError, match="no analysts selected"):
            setup.setup_graph([])


class TestAnalystWrapper:
    """Test the subgraph wrapper error handling."""

    def test_wrapper_catches_exception_returns_empty_report(self):
        """If subgraph raises, wrapper returns empty report + warning."""
        mock_subgraph = MagicMock()
        mock_subgraph.invoke.side_effect = RuntimeError("LLM timeout")

        wrapper = _make_analyst_wrapper(mock_subgraph, "market_report", "market")
        state = {"company_of_interest": "NVDA", "trade_date": "2026-05-01", "warnings": []}
        result = wrapper(state)

        assert result["market_report"] == ""
        assert len(result["warnings"]) == 1
        assert "Market Analyst failed" in result["warnings"][0]

    def test_wrapper_returns_report_on_success(self):
        """On success, wrapper returns the report field."""
        mock_subgraph = MagicMock()
        mock_subgraph.invoke.return_value = {"market_report": "NVDA is bullish"}

        wrapper = _make_analyst_wrapper(mock_subgraph, "market_report", "market")
        state = {"company_of_interest": "NVDA", "trade_date": "2026-05-01", "warnings": []}
        result = wrapper(state)

        assert result["market_report"] == "NVDA is bullish"
        assert "warnings" not in result  # no warnings on success


class TestFastGraphParallel:
    """Test _build_fast_graph parallel mode."""

    def test_fast_graph_parallel_has_barrier(self, mock_llm, mock_tool_nodes, conditional_logic):
        from dashboard.runner import _build_fast_graph

        graph_obj = MagicMock()
        graph_obj.quick_thinking_llm = mock_llm
        graph_obj.deep_thinking_llm = mock_llm
        graph_obj.tool_nodes = mock_tool_nodes
        graph_obj.conditional_logic = conditional_logic
        graph_obj.config = {"parallel_analysts": True}

        graph = _build_fast_graph(graph_obj, ["market", "news", "social"], {})
        node_names = set(graph.nodes.keys())
        assert "Analyst Barrier" in node_names
        assert "Trader" in node_names
        # Fast mode should NOT have Bull/Bear Researchers
        assert "Bull Researcher" not in node_names
        assert "Research Manager" not in node_names

    def test_fast_graph_sequential_no_barrier(self, mock_llm, mock_tool_nodes, conditional_logic):
        from dashboard.runner import _build_fast_graph

        graph_obj = MagicMock()
        graph_obj.quick_thinking_llm = mock_llm
        graph_obj.deep_thinking_llm = mock_llm
        graph_obj.tool_nodes = mock_tool_nodes
        graph_obj.conditional_logic = conditional_logic
        graph_obj.config = {"parallel_analysts": False}

        graph = _build_fast_graph(graph_obj, ["market", "news"], {})
        node_names = set(graph.nodes.keys())
        assert "Analyst Barrier" not in node_names
        assert "Trader" in node_names
