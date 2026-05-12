# Design Document — Sprint 1A: Parallel Analyst Execution

## Overview

Transform the analyst phase from sequential (60-120s) to parallel (20-40s) by running all selected analysts as isolated LangGraph subgraphs that execute concurrently.

## Problem

Currently in `tradingagents/graph/setup.py`, analysts are wired sequentially:
```
START → Market → Msg Clear → News → Msg Clear → Fundamentals → Msg Clear → Social → Msg Clear → Bull Researcher
```
Each analyst takes 15-30s (tool calls + LLM generation). Total: 60-120s for 4 analysts.

## Solution: Subgraph Isolation Pattern

### Why Subgraphs (Not Naive Fan-Out)

`create_msg_delete()` in `agent_utils.py` clears ALL messages from state:
```python
removal_operations = [RemoveMessage(id=m.id) for m in messages]
```
If analysts share a `messages` list and run in parallel, one analyst's `Msg Clear` would delete another's in-flight tool-call messages. **Subgraphs give each analyst its own isolated `messages` state.**

### Architecture

```
Parent Graph (AgentState):
┌─────────────────────────────────────────────────────────────────┐
│ START ──┬── run_market_analyst() ──────┐                        │
│         ├── run_news_analyst() ─────────┤                       │
│         ├── run_fundamentals_analyst() ──┼── Analyst Barrier ──→│
│         └── run_social_analyst() ───────┘         │             │
│                                                    │             │
│         Bull Researcher ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘             │
│         ... (rest of pipeline unchanged)                        │
└─────────────────────────────────────────────────────────────────┘

Each run_{type}_analyst() is a wrapper that:
1. Builds a mini-subgraph: Analyst → tools (loop) → Msg Clear → END
2. Invokes it with {company_of_interest, trade_date, messages: []}
3. Returns {"{type}_report": subgraph_final_state["{type}_report"]}
```

### Subgraph Structure (per analyst)

```python
def _build_analyst_subgraph(analyst_type, analyst_node, tool_node, conditional_fn):
    """Build an isolated subgraph for one analyst."""
    sub = StateGraph(AgentState)
    sub.add_node("Analyst", analyst_node)
    sub.add_node("Tools", tool_node)
    sub.add_node("Clear", create_msg_delete())
    sub.add_edge(START, "Analyst")
    sub.add_conditional_edges("Analyst", conditional_fn, ["Tools", "Clear"])
    sub.add_edge("Tools", "Analyst")
    sub.add_edge("Clear", END)
    return sub.compile()
```

### Parent Graph Wrapper Nodes

```python
def _make_analyst_wrapper(subgraph, report_field, analyst_type):
    """Create a parent-graph node that invokes an analyst subgraph."""
    def wrapper(state):
        init = {
            "messages": [("human", state["company_of_interest"])],
            "company_of_interest": state["company_of_interest"],
            "trade_date": state["trade_date"],
            report_field: "",
        }
        result = subgraph.invoke(init, {"recursion_limit": 50})
        return {report_field: result.get(report_field, "")}
    return wrapper
```

### Error Handling

Each wrapper catches exceptions and returns an empty report + warning:
```python
def wrapper(state):
    try:
        ...
        return {report_field: result.get(report_field, "")}
    except Exception as e:
        return {
            report_field: "",
            "warnings": state.get("warnings", []) + [f"{analyst_type} failed: {e}"]
        }
```

### Sequential Fallback

When `config["parallel_analysts"] = False`, `setup_graph()` uses the original sequential chain (current code, unchanged).

### Fast Mode Integration

`_build_fast_graph()` in `runner.py` uses the same subgraph pattern but:
- Only builds subgraphs for time-sensitive analysts (market, news, social)
- Barrier connects to Trader (not Bull Researcher)
- Pre-seeded `fundamentals_report` and `investment_plan` pass through unchanged

### Progress Tracking Changes

`_update_from_state()` in `runner.py` already handles multiple report fields appearing in a single snapshot (it loops through all fields). The only change needed:
- At graph start, mark ALL selected analysts as "running" simultaneously (not just the first one)

## Alternatives Considered

| Approach | Why Rejected |
|----------|-------------|
| Naive fan-out (shared messages) | `create_msg_delete()` clears all messages — breaks parallel branches |
| `Send()` API | More complex, designed for dynamic fan-out (unknown N). Our N is static (4 analysts) |
| Message tagging | Requires modifying every analyst + tool node to tag/filter messages — too invasive |
| Async execution | LangGraph's sync executor handles threading internally — no benefit from async |

## Files Modified

| File | Change |
|------|--------|
| `tradingagents/graph/setup.py` | Rewrite `setup_graph()` to use subgraph fan-out pattern |
| `tradingagents/default_config.py` | Add `"parallel_analysts": True` |
| `dashboard/runner.py` | Update `_build_fast_graph()` for parallel; fix "first analyst running" signal |
| `tradingagents/agents/utils/agent_utils.py` | No change (create_msg_delete unchanged) |

## Risks

1. **Subgraph state merging** — LangGraph merges subgraph output into parent state. Must ensure only the report field is returned (not messages or other fields that would conflict).
2. **Recursion limit** — Each subgraph has its own recursion limit (50). If an analyst makes many tool calls, it could hit this. Monitor and adjust.
3. **Error propagation** — A subgraph exception must not crash the parent graph. The wrapper's try/except handles this.
